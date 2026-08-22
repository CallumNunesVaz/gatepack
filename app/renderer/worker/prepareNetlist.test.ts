import { describe, expect, it } from 'vitest';
import { prepareNetlist, refdesByInstance } from './prepareNetlist';
import type { PackedView } from '../../shared/api';

/**
 * Shaped exactly like real post-`abc` Yosys 0.23 output: `hide_name`, `type`,
 * `parameters`, `attributes`, `connections` — and **no** `port_directions`.
 * The unit test that "covered" the old evaluator fabricated a netlist *with*
 * directions, which real Yosys output never has, so it passed while the view
 * drew nothing. This fixture is deliberately the honest shape.
 */
const POST_ABC = {
  modules: {
    top: {
      ports: {
        a: { direction: 'input', bits: [0] },
        y: { direction: 'output', bits: [2] },
      },
      netnames: { a: { bits: [0] }, n1: { bits: [1] }, y: { bits: [2] } },
      cells: {
        '$abc$1$auto$blifparse.cc:386:parse_blif$10': {
          hide_name: 1,
          type: 'INV',
          parameters: {},
          attributes: {},
          connections: { A: [0], Y: [1] },
        },
        '$abc$1$auto$blifparse.cc:386:parse_blif$11': {
          hide_name: 1,
          type: 'BUF',
          parameters: {},
          attributes: {},
          connections: { A: [1], Y: [2] },
        },
      },
    },
  },
};

const PACKED: PackedView = {
  packages: [
    {
      refdes: 'U1',
      partNumber: '74AUP1G04',
      cells: ['INV__a'],
      instanceCells: ['$abc$1$auto$blifparse.cc:386:parse_blif$10'],
      capacity: 1,
      spare: 0,
      rationale: 'function group: INV holds 1 gate(s)',
    },
  ],
};

function cells(prepared: unknown): Record<string, any> {
  return (prepared as any).modules.top.cells;
}

describe('prepareNetlist', () => {
  it('supplies the port_directions post-abc write_json does not carry', () => {
    const result = prepareNetlist(POST_ABC, null);
    const inv = cells(result.netlist)['$abc$1$auto$blifparse.cc:386:parse_blif$10'];
    expect(inv.port_directions).toEqual({ A: 'input', Y: 'output' });
    expect(result.resolvedCells).toBe(2);
    expect(result.preResolvedCells).toBe(0);
    expect(result.unresolvedTypes).toEqual([]);
  });

  it('never mutates the netlist it was given', () => {
    const before = JSON.stringify(POST_ABC);
    prepareNetlist(POST_ABC, PACKED);
    expect(JSON.stringify(POST_ABC)).toBe(before);
  });

  it('leaves directions the netlist already carried alone', () => {
    const withDirections = {
      modules: {
        top: {
          ports: {},
          netnames: {},
          cells: {
            c: {
              type: 'AND2',
              // Deliberately wrong-looking, to prove it is not overwritten: a
              // netlist that states its own directions is authoritative.
              port_directions: { A: 'input', B: 'input', Y: 'output' },
              connections: { A: [0], B: [1], Y: [2] },
            },
          },
        },
      },
    };
    const result = prepareNetlist(withDirections, null);
    expect(result.preResolvedCells).toBe(1);
    expect(result.resolvedCells).toBe(0);
  });

  it('reports an unknown cell type rather than guessing its pins', () => {
    const withMacro = {
      modules: {
        top: {
          ports: {},
          netnames: {},
          cells: {
            u: { type: 'CNT4', attributes: {}, connections: { CP: [0], Q0: [1] } },
          },
        },
      },
    };
    const result = prepareNetlist(withMacro, null);
    expect(result.unresolvedTypes).toEqual(['CNT4']);
    expect(cells(result.netlist).u.port_directions).toBeUndefined();
  });

  it('reports a known type whose connected pin the table has no direction for', () => {
    // A pin the pin table does not name means the netlist and the table
    // disagree about the cell. Routing the pins that *do* match would drop
    // that wire silently, so the whole cell is reported instead.
    const oddPin = {
      modules: {
        top: {
          ports: {},
          netnames: {},
          cells: {
            g: { type: 'AND2', attributes: {}, connections: { A: [0], B: [1], Y: [2], OE: [3] } },
          },
        },
      },
    };
    const result = prepareNetlist(oddPin, null);
    expect(result.unresolvedTypes).toEqual(['AND2']);
    expect(cells(result.netlist).g.port_directions).toBeUndefined();
  });

  it('attaches the refdes for a packed cell and no refdes for an unpacked one', () => {
    const result = prepareNetlist(POST_ABC, PACKED);
    const packedCell = cells(result.netlist)['$abc$1$auto$blifparse.cc:386:parse_blif$10'];
    const loose = cells(result.netlist)['$abc$1$auto$blifparse.cc:386:parse_blif$11'];
    expect(packedCell.attributes.gp_refdes).toBe('U1');
    expect(packedCell.attributes.gp_type).toBe('INV');
    expect(loose.attributes.gp_refdes).toBeUndefined();
    expect(loose.attributes.gp_type).toBe('BUF');
  });

  it('handles a netlist with no modules without throwing', () => {
    expect(prepareNetlist({}, null).unresolvedTypes).toEqual([]);
    expect(prepareNetlist(null, null).netlist).toBeNull();
  });
});

describe('refdesByInstance', () => {
  it('maps every instance cell of every package', () => {
    expect(refdesByInstance(PACKED).get('$abc$1$auto$blifparse.cc:386:parse_blif$10')).toBe('U1');
    expect(refdesByInstance(null).size).toBe(0);
  });
});
