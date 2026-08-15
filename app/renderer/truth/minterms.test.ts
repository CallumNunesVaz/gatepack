import { describe, expect, it } from 'vitest';
import { allMinterms, computeLiveOutputs, isCombinational, reachableStates } from './minterms';
import type { DesignModel } from '../design/model';

function model(partial: Partial<DesignModel>): DesignModel {
  return {
    name: 't',
    timingModel: 'synchronous',
    clock: null,
    reset: { signal: 'rst_n', active: 'low', asyncAssert: true, syncDeassert: true, source: '' },
    encoding: 'one_hot',
    inputs: [],
    outputs: [],
    expressions: {},
    states: [],
    initial: '',
    transitions: [],
    outputLogic: {},
    properties: [],
    safeState: {},
    testPoints: [],
    macros: [],
    fundamentalMode: null,
    constraints: { vcc: 3.3 },
    ...partial,
  };
}

describe('minterm helpers', () => {
  it('enumerates 2^n input minterms, MSB first', () => {
    const minterms = allMinterms(['a', 'b']);
    expect(minterms).toHaveLength(4);
    expect(minterms[0]).toEqual({ a: '0', b: '0' });
    expect(minterms[1]).toEqual({ a: '0', b: '1' });
    expect(minterms[2]).toEqual({ a: '1', b: '0' });
    expect(minterms[3]).toEqual({ a: '1', b: '1' });
  });

  it('computes live outputs with named-expression expansion', () => {
    const m = model({
      inputs: [{ name: 'a', sync: false }, { name: 'b', sync: false }],
      outputs: [{ name: 'y' }],
      expressions: { f: 'a | b' },
      outputLogic: { y: 'f & a' },
    });
    expect(computeLiveOutputs(m, { a: '1', b: '0' }).y).toBe('1');
    expect(computeLiveOutputs(m, { a: '0', b: '1' }).y).toBe('0');
  });

  it('evaluates Moore output_logic against a state context', () => {
    const m = model({
      states: ['IDLE', 'RUN'],
      initial: 'IDLE',
      outputs: [{ name: 'enable' }],
      outputLogic: { enable: 'state == RUN' },
    });
    expect(computeLiveOutputs(m, {}, 'RUN').enable).toBe('1');
    expect(computeLiveOutputs(m, {}, 'IDLE').enable).toBe('0');
    expect(computeLiveOutputs(m, {}).enable).toBe('x');
  });

  it('flags unreachable states (unreachable minterms)', () => {
    const m = model({
      states: ['A', 'B', 'DEAD'],
      initial: 'A',
      transitions: [
        { from: 'A', to: 'B', when: '1' },
        { from: 'B', to: 'A', when: '1' },
      ],
    });
    const reachable = reachableStates(m);
    expect([...reachable].sort()).toEqual(['A', 'B']);
    expect(m.states.filter((s) => !reachable.has(s))).toEqual(['DEAD']);
  });

  it('detects purely combinational designs', () => {
    expect(isCombinational(model({ outputLogic: { y: 'a ^ b' } }))).toBe(true);
    expect(isCombinational(model({ outputLogic: { y: 'state == S0' } }))).toBe(false);
  });
});
