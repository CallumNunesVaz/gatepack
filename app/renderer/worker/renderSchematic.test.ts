import { describe, expect, it } from 'vitest';
import { renderSchematic } from './renderSchematic';

// A small captured Yosys `write_json` netlist: a two-input NAND.
const fixture = {
  creator: 'Yosys 0.23',
  modules: {
    top: {
      attributes: {},
      ports: {
        a: { direction: 'input', bits: [0] },
        b: { direction: 'input', bits: [1] },
        y: { direction: 'output', bits: [2] },
      },
      netnames: {
        a: { bits: [0] },
        b: { bits: [1] },
        y: { bits: [2] },
      },
      cells: {
        $nand: {
          hide_name: 1,
          type: 'NAND2',
          parameters: {},
          attributes: {},
          port_directions: { A: 'input', B: 'input', Y: 'output' },
          connections: { A: [0], B: [1], Y: [2] },
        },
      },
    },
  },
};

describe('renderSchematic (netlistsvg + elkjs)', () => {
  it('renders an SVG from a small write_json fixture', async () => {
    const svg = await renderSchematic(fixture);
    expect(typeof svg).toBe('string');
    expect(svg).toContain('<svg');
    // Gate symbols (s:type cell groups) and orthogonal routing lines are present.
    expect(svg).toMatch(/s:type=/);
    expect(svg).toContain('<line');
    expect(svg).toMatch(/class="net_/);
    // The port labels are preserved.
    expect(svg).toContain('>a</text>');
    expect(svg).toContain('>y</text>');
  });

  it('renders a multi-gate netlist without throwing', async () => {
    const multi = {
      modules: {
        top: {
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
            c1: { hide_name: 1, type: 'NAND2', port_directions: { A: 'input', B: 'input', Y: 'output' }, connections: { A: [3], B: [4], Y: [5] } },
            c2: { hide_name: 1, type: 'NAND2', port_directions: { A: 'input', B: 'input', Y: 'output' }, connections: { A: [0], B: [2], Y: [3] } },
            c3: { hide_name: 1, type: 'NAND2', port_directions: { A: 'input', B: 'input', Y: 'output' }, connections: { A: [1], B: [2], Y: [4] } },
            c4: { hide_name: 1, type: 'NAND2', port_directions: { A: 'input', B: 'input', Y: 'output' }, connections: { A: [0], B: [1], Y: [2] } },
          },
        },
      },
    };
    const svg = await renderSchematic(multi);
    expect(svg).toContain('<svg');
  });
});
