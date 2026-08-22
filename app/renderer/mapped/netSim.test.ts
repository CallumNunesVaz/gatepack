import { describe, expect, it } from 'vitest';
import { parseWriteJson } from './sim';
import { prepareNetlist } from '../worker/prepareNetlist';
import {
  clockNets,
  evaluateNets,
  flopCells,
  initialFlopState,
  isSequential,
  settleAsync,
  stepClock,
} from './netSim';
import type { Bit } from '../design/expr';

/**
 * A §9.3 reset chain in miniature: two synchroniser flops off the **raw** reset
 * pin feeding one state flop off the **synchronised** reset, plus an inverter so
 * the combinational cone is not trivial. This is the topology that makes the
 * async behaviour worth modelling — asserting the pin clears the synchronisers
 * with no edge, and that clears the state flop, also with no edge.
 */
const CHAIN = {
  modules: {
    top: {
      ports: {
        clk: { direction: 'input', bits: [0] },
        rst_n: { direction: 'input', bits: [1] },
        d: { direction: 'input', bits: [2] },
        q: { direction: 'output', bits: [5] },
      },
      netnames: {
        clk: { bits: [0] },
        rst_n: { bits: [1] },
        d: { bits: [2] },
        s1: { bits: [3] },
        s2: { bits: [4] },
        q: { bits: [5] },
        dn: { bits: [6] },
      },
      cells: {
        sync1: { type: 'DFF_R', attributes: {}, connections: { CK: [0], D: ['1'], Q: [3], RST_N: [1] } },
        sync2: { type: 'DFF_R', attributes: {}, connections: { CK: [0], D: [3], Q: [4], RST_N: [1] } },
        inv: { type: 'INV', attributes: {}, connections: { A: [2], Y: [6] } },
        state: { type: 'DFF_R', attributes: {}, connections: { CK: [0], D: [6], Q: [5], RST_N: [4] } },
      },
    },
  },
};

function parsed() {
  return parseWriteJson(prepareNetlist(CHAIN, null).netlist);
}

const RUNNING: Record<string, Bit> = { clk: '0', rst_n: '1', d: '0' };
const ASSERTED: Record<string, Bit> = { clk: '0', rst_n: '0', d: '0' };

describe('netSim — structure', () => {
  it('finds the flops, the clock nets and the sequential verdict', () => {
    const n = parsed();
    expect(flopCells(n).map((c) => c.name).sort()).toEqual(['state', 'sync1', 'sync2']);
    expect(isSequential(n)).toBe(true);
    expect([...clockNets(n)]).toEqual(['clk']);
    expect(initialFlopState(n)).toEqual({ sync1: 'x', sync2: 'x', state: 'x' });
  });

  it('reports a purely combinational netlist as not sequential', () => {
    const combinational = {
      modules: {
        top: {
          ports: { a: { direction: 'input', bits: [0] }, y: { direction: 'output', bits: [1] } },
          netnames: { a: { bits: [0] }, y: { bits: [1] } },
          cells: { i: { type: 'INV', attributes: {}, connections: { A: [0], Y: [1] } } },
        },
      },
    };
    expect(isSequential(parseWriteJson(prepareNetlist(combinational, null).netlist))).toBe(false);
  });
});

describe('netSim — values on every net', () => {
  it('evaluates internal nets, not just the output ports', () => {
    const n = parsed();
    const { values } = evaluateNets(n, { ...RUNNING, d: '1' }, { sync1: '1', sync2: '1', state: '0' });
    // `dn` is an internal net with no port of its own; the old evaluator
    // reported output ports only and could not colour a wire like this.
    expect(values.dn).toBe('0');
    expect(values.s2).toBe('1');
    expect(values.q).toBe('0');
  });

  it('leaves an unmodelled cell output unknown rather than guessing', () => {
    const withMacro = {
      modules: {
        top: {
          ports: { a: { direction: 'input', bits: [0] }, y: { direction: 'output', bits: [1] } },
          netnames: { a: { bits: [0] }, y: { bits: [1] } },
          cells: {
            u: {
              type: 'CNT4',
              attributes: {},
              port_directions: { A: 'input', Y: 'output' },
              connections: { A: [0], Y: [1] },
            },
          },
        },
      },
    };
    const n = parseWriteJson(prepareNetlist(withMacro, null).netlist);
    expect(evaluateNets(n, { a: '1' }, {}).values.y).toBe('x');
  });
});

describe('netSim — async reset', () => {
  it('asserting reset clears the whole chain with no clock edge at all', () => {
    const n = parsed();
    const held = { sync1: '1' as Bit, sync2: '1' as Bit, state: '1' as Bit };
    const { values, asyncForced } = evaluateNets(n, ASSERTED, held);
    // The synchronisers take the raw pin, so they go first; their output is the
    // state flop's reset, so it follows in the same settle — one level-sensitive
    // cascade, zero edges.
    expect(values.s1).toBe('0');
    expect(values.s2).toBe('0');
    expect(values.q).toBe('0');
    expect(asyncForced).toEqual(['state', 'sync1', 'sync2']);
  });

  it('settleAsync writes the cascade back into the held state', () => {
    const n = parsed();
    const settled = settleAsync(n, ASSERTED, { sync1: '1', sync2: '1', state: '1' });
    expect(settled).toEqual({ sync1: '0', sync2: '0', state: '0' });
  });

  it('does not treat an unknown reset as an assertion', () => {
    const n = parsed();
    const { asyncForced } = evaluateNets(n, { clk: '0', rst_n: 'x', d: '0' }, initialFlopState(n));
    expect(asyncForced).toEqual([]);
  });

  it('takes three edges after release for the synchroniser to let go', () => {
    const n = parsed();
    let flops = settleAsync(n, ASSERTED, initialFlopState(n));
    expect(flops.s2).toBeUndefined();
    expect(flops).toEqual({ sync1: '0', sync2: '0', state: '0' });

    // Edge 1: sync1 takes the tie-high; sync2 still sees sync1's old 0, so the
    // state flop is still held in reset.
    flops = stepClock(n, RUNNING, flops);
    expect(flops).toEqual({ sync1: '1', sync2: '0', state: '0' });

    // Edge 2: sync2 follows. The state flop's reset is only now released — it
    // was still asserted *during* this edge, so it is held one more time.
    flops = stepClock(n, RUNNING, flops);
    expect(flops).toEqual({ sync1: '1', sync2: '1', state: '0' });

    // Edge 3: the state flop is finally free and takes its D (`!d` = 1).
    flops = stepClock(n, RUNNING, flops);
    expect(flops.state).toBe('1');
  });

  it('holds a flop at its forced value through a clock edge', () => {
    const n = parsed();
    const flops = stepClock(n, ASSERTED, { sync1: '1', sync2: '1', state: '1' });
    expect(flops).toEqual({ sync1: '0', sync2: '0', state: '0' });
  });
});

describe('netSim — SET_N', () => {
  it('an asserted set forces the flop to one, not to zero', () => {
    const withSet = {
      modules: {
        top: {
          ports: {
            clk: { direction: 'input', bits: [0] },
            set_n: { direction: 'input', bits: [1] },
            q: { direction: 'output', bits: [2] },
          },
          netnames: { clk: { bits: [0] }, set_n: { bits: [1] }, q: { bits: [2] } },
          cells: {
            f: { type: 'DFF_S', attributes: {}, connections: { CK: [0], D: ['0'], Q: [2], SET_N: [1] } },
          },
        },
      },
    };
    const n = parseWriteJson(prepareNetlist(withSet, null).netlist);
    expect(evaluateNets(n, { clk: '0', set_n: '0' }, { f: '0' }).values.q).toBe('1');
    expect(stepClock(n, { clk: '0', set_n: '0' }, { f: '0' })).toEqual({ f: '1' });
    // Released, the flop takes its tie-low D on the next edge.
    expect(stepClock(n, { clk: '0', set_n: '1' }, { f: '1' })).toEqual({ f: '0' });
  });
});
