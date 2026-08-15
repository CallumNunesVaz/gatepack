import { describe, expect, it } from 'vitest';
import { parseWriteJson, simulateCombinational } from './sim';

function xorNandFixture() {
  return {
    modules: {
      xor2: {
        ports: {
          a: { direction: 'input', bits: [0] },
          b: { direction: 'input', bits: [1] },
          y: { direction: 'output', bits: [5] },
        },
        netnames: {
          a: { bits: [0] },
          b: { bits: [1] },
          n1: { bits: [2] },
          n2: { bits: [3] },
          n3: { bits: [4] },
          y: { bits: [5] },
        },
        cells: {
          $xor$y: {
            hide_name: 1,
            type: 'NAND2',
            port_directions: { A: 'input', B: 'input', Y: 'output' },
            connections: { A: [3], B: [4], Y: [5] },
          },
          $xor$n2: {
            hide_name: 1,
            type: 'NAND2',
            port_directions: { A: 'input', B: 'input', Y: 'output' },
            connections: { A: [0], B: [2], Y: [3] },
          },
          $xor$n3: {
            hide_name: 1,
            type: 'NAND2',
            port_directions: { A: 'input', B: 'input', Y: 'output' },
            connections: { A: [1], B: [2], Y: [4] },
          },
          $xor$n1: {
            hide_name: 1,
            type: 'NAND2',
            port_directions: { A: 'input', B: 'input', Y: 'output' },
            connections: { A: [0], B: [1], Y: [2] },
          },
        },
      },
    },
  };
}

function constTieFixture() {
  return {
    modules: {
      tie: {
        ports: {
          a: { direction: 'input', bits: [0] },
          y: { direction: 'output', bits: [2] },
        },
        netnames: {
          a: { bits: [0] },
          y: { bits: [2] },
        },
        cells: {
          $and: {
            hide_name: 1,
            type: 'AND2',
            port_directions: { A: 'input', B: 'input', Y: 'output' },
            connections: { A: [0], B: ['1'], Y: [2] },
          },
        },
      },
    },
  };
}

function flopFixture() {
  return {
    modules: {
      fsm: {
        ports: {
          d: { direction: 'input', bits: [0] },
          q: { direction: 'output', bits: [2] },
        },
        netnames: {
          d: { bits: [0] },
          q: { bits: [2] },
        },
        cells: {
          $dff: {
            hide_name: 1,
            type: 'DFF_R',
            port_directions: { D: 'input', Q: 'output', CK: 'input', RST_N: 'input' },
            connections: { D: [0], Q: [2], CK: ['1'], RST_N: ['1'] },
          },
        },
      },
    },
  };
}

describe('parseWriteJson', () => {
  it('resolves inputs, outputs and cells from a write_json document', () => {
    const net = parseWriteJson(xorNandFixture());
    expect(net.top).toBe('xor2');
    expect(net.inputs).toEqual(['a', 'b']);
    expect(net.outputs).toEqual(['y']);
    expect(net.cells).toHaveLength(4);
    expect(net.cells.every((c) => c.type === 'NAND2')).toBe(true);
  });

  it('resolves constant ties and unknown bits', () => {
    const net = parseWriteJson(constTieFixture());
    const cell = net.cells[0];
    expect(cell.connections['A']).toBe('a');
    expect(cell.connections['B']).toBe('1');
  });
});

describe('simulateCombinational', () => {
  it('computes a 4-NAND xor over the whole input space', () => {
    const net = parseWriteJson(xorNandFixture());
    const cases: Array<[string, string, string]> = [
      ['0', '0', '0'],
      ['0', '1', '1'],
      ['1', '0', '1'],
      ['1', '1', '0'],
    ];
    for (const [a, b, y] of cases) {
      expect(simulateCombinational(net, { a: a as '0' | '1', b: b as '0' | '1' }).y).toBe(y);
    }
  });

  it('propagates a constant tie', () => {
    const net = parseWriteJson(constTieFixture());
    expect(simulateCombinational(net, { a: '1' }).y).toBe('1');
    expect(simulateCombinational(net, { a: '0' }).y).toBe('0');
  });

  it('returns x for sequential cell outputs (not clocked)', () => {
    const net = parseWriteJson(flopFixture());
    expect(simulateCombinational(net, { d: '1' }).q).toBe('x');
  });

  it('returns x for unknown inputs', () => {
    const net = parseWriteJson(constTieFixture());
    expect(simulateCombinational(net, {}).y).toBe('x');
  });
});
