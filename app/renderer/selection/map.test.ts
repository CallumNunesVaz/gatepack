import { describe, expect, it } from 'vitest';
import type { ProvenanceMap, SimulationTable } from '../../shared/api';
import { parseDesignText } from '../design/model';
import type { ParsedNetlist } from '../mapped/sim';
import {
  coneCells,
  divergingOutputs,
  indexProvenance,
  linkConfidence,
  parsePointer,
  resolveSelection,
} from './map';
import type { LinkContext } from './types';

const FSM_SPEC = `name: fsm
timing_model: synchronous
clock: {signal: clk, freq_hz: 1000, source: OSC}
reset: {signal: rst_n, active: low, source: SUPERVISOR}
encoding: one_hot
inputs:
  - {name: go, sync: false}
outputs:
  - {name: out}
states: [A, B]
initial: A
transitions:
  - {from: A, to: B, when: "go"}
  - {from: A, to: A, when: "!go"}
  - {from: B, to: A, when: "1"}
output_logic:
  out: "state == B"
`;

const XOR2_SPEC = `name: xor2
timing_model: synchronous
clock: {signal: clk, freq_hz: 1000, source: OSC}
reset: {signal: rst_n, active: low, source: SUPERVISOR}
encoding: one_hot
inputs:
  - {name: a, sync: false}
  - {name: b, sync: false}
outputs:
  - {name: y}
states: [S0]
initial: S0
transitions:
  - {from: S0, to: S0, when: "1"}
output_logic:
  y: "a ^ b"
`;

function model(spec: string) {
  const outcome = parseDesignText(spec);
  if (!outcome.model) throw new Error('fixture does not parse');
  return outcome.model;
}

function ctx(overrides: Partial<LinkContext> = {}): LinkContext {
  return {
    model: model(FSM_SPEC),
    provenance: { entries: [], coverage: 0 },
    netlist: null,
    simulation: null,
    ...overrides,
  };
}

const AND_NETLIST: ParsedNetlist = {
  top: 'xor2',
  inputs: ['a', 'b'],
  outputs: ['y'],
  cells: [
    {
      name: '$and',
      type: 'AND2',
      connections: { A: 'a', B: 'b', Y: 'y' },
      directions: { A: 'input', B: 'input', Y: 'output' },
    },
  ],
};

function divergingSimulation(): SimulationTable {
  return {
    inputNames: ['a', 'b'],
    outputNames: ['y'],
    rows: [
      { inputs: { a: '0', b: '0' }, expected: { y: '0' }, actual: { y: '0' }, diverges: false },
      { inputs: { a: '0', b: '1' }, expected: { y: '1' }, actual: { y: '0' }, diverges: true },
      { inputs: { a: '1', b: '0' }, expected: { y: '1' }, actual: { y: '0' }, diverges: true },
      { inputs: { a: '1', b: '1' }, expected: { y: '0' }, actual: { y: '1' }, diverges: true },
    ],
    dontCareCount: 0,
    unreachableCount: 0,
    exhaustive: true,
  };
}

function transitionEntry(pointer: string, confidence: 'exact' | 'inferred', nets: string[] = [], cells: string[] = []): ProvenanceMap {
  return { entries: [{ pointer, nets, cells, confidence }], coverage: 0 };
}

describe('parsePointer', () => {
  it('splits a §15.1 token into filename, line and path', () => {
    expect(parsePointer('design.yaml:42:transitions[2]')).toEqual({ filename: 'design.yaml', line: 42, path: 'transitions[2]' });
    expect(parsePointer('design.yaml:transitions[2]')).toEqual({ filename: 'design.yaml', line: null, path: 'transitions[2]' });
  });
});

describe('coneCells', () => {
  it('finds the combinational cone of an output net', () => {
    expect(coneCells(AND_NETLIST, ['y'])).toEqual(['$and']);
  });

  it('returns nothing for an undriven seed', () => {
    expect(coneCells(AND_NETLIST, ['nope'])).toEqual([]);
  });
});

describe('divergingOutputs', () => {
  it('lists only outputs that disagree on both known sides', () => {
    const row = { inputs: { a: '0' }, expected: { y: '1', z: '0' }, actual: { y: '0', z: '0' }, diverges: true };
    expect(divergingOutputs(row)).toEqual(['y']);
  });

  it('ignores unknown (x) actual values', () => {
    const row = { inputs: { a: '0' }, expected: { y: '1' }, actual: { y: 'x' }, diverges: false };
    expect(divergingOutputs(row)).toEqual([]);
  });
});

describe('linkConfidence', () => {
  it('exact beats inferred', () => {
    const index = indexProvenance({
      entries: [
        { pointer: 'design.yaml:1:transitions[0]', nets: [], cells: [], confidence: 'inferred' },
        { pointer: 'design.yaml:2:transitions[0]', nets: [], cells: [], confidence: 'exact' },
      ],
      coverage: 0,
    });
    expect(linkConfidence(index, ['transitions[0]'])).toBe('exact');
  });

  it('inferred is reported when no exact link survives', () => {
    const index = indexProvenance(transitionEntry('design.yaml:1:transitions[0]', 'inferred'));
    expect(linkConfidence(index, ['transitions[0]'])).toBe('inferred');
  });

  it('none when there is no entry at all', () => {
    const index = indexProvenance({ entries: [], coverage: 0 });
    expect(linkConfidence(index, ['transitions[0]'])).toBe('none');
  });
});

describe('resolveSelection — transitions (both directions)', () => {
  it('maps a transition to its provenance nets/cells', () => {
    const c = ctx({
      provenance: transitionEntry('design.yaml:14:transitions[0]', 'exact', ['n1'], ['$and']),
    });
    const h = resolveSelection({ kind: 'transition', from: 'A', to: 'B' }, c);
    expect(h.pointers).toEqual(['design.yaml:14:transitions[0]']);
    expect(h.nets).toEqual(['n1']);
    expect(h.cells).toEqual(['$and']);
    expect(h.confidence).toBe('exact');
    expect(h.states).toEqual(['A', 'B']);
    expect(h.transitions).toEqual([0]);
  });

  it('maps a cell back to the transitions that produced it', () => {
    const c = ctx({
      provenance: transitionEntry('design.yaml:14:transitions[0]', 'exact', ['n1'], ['$and']),
    });
    const h = resolveSelection({ kind: 'cell', name: '$and' }, c);
    expect(h.transitions).toEqual([0]);
    expect(h.states).toEqual(['A', 'B']);
    expect(h.pointers).toEqual(['design.yaml:14:transitions[0]']);
  });

  it('reports "no exact link" (confidence none) for a transition with no surviving provenance', () => {
    const c = ctx({ provenance: { entries: [], coverage: 0 } });
    const h = resolveSelection({ kind: 'transition', from: 'A', to: 'A' }, c);
    expect(h.confidence).toBe('none');
    expect(h.nets).toEqual([]);
    expect(h.cells).toEqual([]);
  });

  it('renders inferred distinctly from exact at the data level', () => {
    const c = ctx({
      provenance: transitionEntry('design.yaml:14:transitions[0]', 'inferred', ['n1'], ['$and']),
    });
    const h = resolveSelection({ kind: 'transition', from: 'A', to: 'B' }, c);
    expect(h.confidence).toBe('inferred');
  });
});

describe('resolveSelection — divergence', () => {
  it('a diverging row selects the gates in its cone', () => {
    const c = ctx({
      model: model(XOR2_SPEC),
      netlist: AND_NETLIST,
      simulation: divergingSimulation(),
    });
    const h = resolveSelection({ kind: 'minterm', index: 1 }, c);
    expect(h.cells).toEqual(['$and']);
    expect(h.nets).toEqual(['y']);
    expect(h.minterms).toEqual([1]);
  });

  it('a gate selects every row its cone drives (the reverse direction)', () => {
    const c = ctx({
      model: model(XOR2_SPEC),
      netlist: AND_NETLIST,
      simulation: divergingSimulation(),
    });
    const h = resolveSelection({ kind: 'cell', name: '$and' }, c);
    expect(h.minterms).toEqual([0, 1, 2, 3]);
    expect(h.cells).toEqual(['$and']);
  });
});
