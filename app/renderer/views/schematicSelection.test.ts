import { describe, expect, it } from 'vitest';
import { selectionSvgTargets } from './schematicSelection';
import { EMPTY_HIGHLIGHTS } from '../selection/types';

const NETLIST = {
  modules: {
    top: {
      ports: {
        a: { direction: 'input', bits: [0] },
        b: { direction: 'input', bits: [1] },
        y: { direction: 'output', bits: [4] },
      },
      netnames: {
        a: { bits: [0] },
        b: { bits: [1] },
        n1: { bits: [2] },
        y: { bits: [4] },
      },
      cells: {
        $g1: { type: 'NAND2', port_directions: {}, connections: {} },
        $g2: { type: 'NAND2', port_directions: {}, connections: {} },
      },
    },
  },
};

describe('selectionSvgTargets — §15.2 schematic highlighting', () => {
  it('maps instance cells to `cell_<instance>` ids', () => {
    const t = selectionSvgTargets(NETLIST, {
      ...EMPTY_HIGHLIGHTS,
      cells: ['$g1'],
    });
    expect(t.cellIds).toEqual(['cell_$g1']);
  });

  it('maps net names to `net_<bits>` classes via the netlist bits', () => {
    const t = selectionSvgTargets(NETLIST, {
      ...EMPTY_HIGHLIGHTS,
      nets: ['y'],
    });
    expect(t.netClasses).toEqual(['net_4']);
  });

  it('ignores nets with no bits in the netlist (never fabricates a selector)', () => {
    const t = selectionSvgTargets(NETLIST, {
      ...EMPTY_HIGHLIGHTS,
      nets: ['y', 'no_such_net'],
    });
    expect(t.netClasses).toEqual(['net_4']);
  });

  it('returns empty targets for an empty highlight set', () => {
    const t = selectionSvgTargets(NETLIST, EMPTY_HIGHLIGHTS);
    expect(t.cellIds).toEqual([]);
    expect(t.netClasses).toEqual([]);
  });
});
