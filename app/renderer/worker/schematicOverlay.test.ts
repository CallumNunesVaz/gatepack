import { describe, expect, it } from 'vitest';
import {
  UNOBSERVABLE,
  computePackageLayouts,
  netBitIndices,
  readCellPositions,
  unobservableNets,
} from './schematicOverlay';
import type { AnalysisSummary, PackedView } from '../../shared/api';

const NS = 'http://www.w3.org/2000/svg';

function makeSvg(): SVGSVGElement {
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('width', '400');
  svg.setAttribute('height', '300');

  const cell = (instance: string, x: number, y: number) => {
    const g = document.createElementNS(NS, 'g');
    g.setAttribute('id', `cell_${instance}`);
    g.setAttribute('transform', `translate(${x},${y})`);
    svg.appendChild(g);
  };
  cell('$abc$1$inst$100', 50, 60);
  cell('$abc$1$inst$101', 120, 60);
  cell('$abc$1$inst$102', 50, 140);

  const net = (cls: string, x1: number, y1: number, x2: number, y2: number) => {
    const line = document.createElementNS(NS, 'line');
    line.setAttribute('class', cls);
    line.setAttribute('x1', String(x1));
    line.setAttribute('y1', String(y1));
    line.setAttribute('x2', String(x2));
    line.setAttribute('y2', String(y2));
    svg.appendChild(line);
  };
  net('net_4', 50, 60, 120, 60);
  net('net_6', 50, 140, 50, 200);
  return svg;
}

function scoap(entries: Array<[string, number]>): AnalysisSummary {
  return {
    metrics: [],
    scoap: entries.map(([net, observability]) => ({
      net,
      controllability0: 1,
      controllability1: 1,
      observability,
    })),
    faults: { detected: 0, undetected: 0, redundant: 0, untestable: 0 },
    cpldBlockers: [],
  };
}

describe('unobservableNets', () => {
  it('marks only nets at or above the sentinel, never the observable ones', () => {
    const analysis = scoap([
      ['y', UNOBSERVABLE],
      ['n1', UNOBSERVABLE],
      ['a', 5],
      ['b', 3],
    ]);
    expect(unobservableNets(analysis)).toEqual(['y', 'n1']);
  });

  it('is empty when every net is observable', () => {
    expect(unobservableNets(scoap([['a', 2]]))).toEqual([]);
  });
});

describe('readCellPositions', () => {
  it('reads instance-name positions from netlistsvg cell groups', () => {
    const positions = readCellPositions(makeSvg());
    expect(positions.get('$abc$1$inst$100')).toEqual({ x: 50, y: 60 });
    expect(positions.get('$abc$1$inst$101')).toEqual({ x: 120, y: 60 });
    expect(positions.has('$abc$1$inst$999')).toBe(false);
  });
});

describe('computePackageLayouts', () => {
  it('returns one container per package, grouped around its cells', () => {
    const packages: PackedView['packages'] = [
      {
        refdes: 'U1',
        partNumber: '74AUP2G00',
        cells: ['NAND2__aaaa', 'NAND2__bbbb'],
        instanceCells: ['$abc$1$inst$100', '$abc$1$inst$101'],
        capacity: 2,
        spare: 0,
        rationale: 'function group: NAND2 holds 2 gate(s)',
      },
      {
        refdes: 'U2',
        partNumber: '74AUP1G00',
        cells: ['NAND2__cccc'],
        instanceCells: ['$abc$1$inst$102'],
        capacity: 1,
        spare: 0,
        rationale: 'function group: NAND2 holds 1 gate(s)',
      },
    ];
    const positions = readCellPositions(makeSvg());
    const layouts = computePackageLayouts(packages, positions);
    expect(layouts).toHaveLength(2);
    expect(layouts.map((l) => l.refdes)).toEqual(['U1', 'U2']);
    // U1 spans its two cells horizontally; U2 is a single cell.
    expect(layouts[0].x).toBeLessThan(layouts[0].width);
    expect(layouts[1].capacity).toBe(1);
  });
});

describe('netBitIndices', () => {
  it('maps net names to their write_json bit indices, ports winning', () => {
    const netlist = {
      modules: {
        top: {
          ports: { y: { direction: 'output', bits: [6] } },
          netnames: {
            y: { bits: [6] },
            y_int: { bits: [6] },
            n1: { bits: [4] },
          },
        },
      },
    };
    const bits = netBitIndices(netlist);
    expect(bits.get('y')).toEqual([6]);
    expect(bits.get('n1')).toEqual([4]);
  });
});
