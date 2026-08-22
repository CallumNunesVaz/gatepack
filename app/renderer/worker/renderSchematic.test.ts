import { describe, expect, it } from 'vitest';
import { renderSchematic } from './renderSchematic';
import { prepareNetlist } from './prepareNetlist';

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

/**
 * The same design as Yosys actually writes it after `abc`: no
 * `port_directions`, and an instance name carrying Yosys's own `blifparse.cc`.
 * This is the shape that produced a schematic of nothing but type names.
 */
const POST_ABC = {
  modules: {
    top: {
      ports: {
        a: { direction: 'input', bits: [0] },
        b: { direction: 'input', bits: [1] },
        y: { direction: 'output', bits: [2] },
      },
      netnames: { a: { bits: [0] }, b: { bits: [1] }, y: { bits: [2] } },
      cells: {
        '$abc$1$auto$blifparse.cc:386:parse_blif$10': {
          hide_name: 1,
          type: 'NAND2',
          parameters: {},
          attributes: {},
          connections: { A: [0], B: [1], Y: [2] },
        },
      },
    },
  },
};

describe('renderSchematic (netlistsvg + elkjs)', () => {
  it('renders an SVG from a small write_json fixture', async () => {
    const { svg } = await renderSchematic(fixture);
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

  it('draws a library cell as a gate symbol with routed wires', async () => {
    // The regression this whole path exists for: netlistsvg's stock skin knows
    // `$_NAND_` and not `NAND2`, so every gatepack cell fell through to the
    // `generic` template — which, with no `port_directions`, classified no pins
    // and routed no wires. The result rendered as a column of type names.
    const { svg } = await renderSchematic(prepareNetlist(POST_ABC, null).netlist);
    expect(svg).toContain('s:type="nand2"');
    expect(svg).not.toContain('s:type="generic"');
    // Three nets — two inputs and the output — each with at least one wire.
    for (const cls of ['net_0', 'net_1', 'net_2']) {
      expect(svg).toMatch(new RegExp(`class="${cls}"`));
    }
  });

  it('never mutates the netlist it was given', async () => {
    // netlistsvg rewrites `connections` in place: a `D: ["1"]` tie-high becomes
    // a synthesised bit index. The schematic view hands the same object to the
    // evaluator, so rendering used to corrupt every value downstream of a
    // constant.
    const tied = {
      modules: {
        top: {
          ports: {
            clk: { direction: 'input', bits: [0] },
            q: { direction: 'output', bits: [1] },
          },
          netnames: { clk: { bits: [0] }, q: { bits: [1] } },
          cells: {
            f: {
              type: 'DFF',
              attributes: {},
              port_directions: { CK: 'input', D: 'input', Q: 'output' },
              connections: { CK: [0], D: ['1'], Q: [1] },
            },
          },
        },
      },
    };
    const before = JSON.stringify(tied);
    await renderSchematic(tied);
    expect(JSON.stringify(tied)).toBe(before);
  });

  it('reports the wire netlistsvg put each materialised constant on', async () => {
    const tied = {
      modules: {
        top: {
          ports: {
            clk: { direction: 'input', bits: [0] },
            q: { direction: 'output', bits: [1] },
          },
          netnames: { clk: { bits: [0] }, q: { bits: [1] } },
          cells: {
            f: {
              type: 'DFF',
              attributes: {},
              port_directions: { CK: 'input', D: 'input', Q: 'output' },
              connections: { CK: [0], D: ['1'], Q: [1] },
            },
          },
        },
      },
    };
    const { constants } = await renderSchematic(tied);
    // A tie-high is a *known* value on a real wire. Without this map it would
    // render as unknown, which is a lie about a net tied to a rail.
    expect([...constants.values()]).toEqual(['1']);
    const cls = [...constants.keys()][0];
    expect(cls).toMatch(/^net_\d+$/);
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
    const { svg } = await renderSchematic(multi);
    expect(svg).toContain('<svg');
  });

  it('draws every cell type the library defines as its own symbol', async () => {
    // A skin that silently loses a symbol degrades to `generic`, which still
    // "renders" — so the absence has to be asserted, not eyeballed.
    const types = [
      'INV', 'BUF', 'AND2', 'AND3', 'NAND2', 'NAND3',
      'OR2', 'OR3', 'NOR2', 'NOR3', 'XOR2', 'XNOR2', 'MUX2',
      'DFF', 'DFF_R', 'DFF_S', 'DFF_SR',
    ];
    const cells: Record<string, unknown> = {};
    const netnames: Record<string, unknown> = { clk: { bits: [0] } };
    types.forEach((type, i) => {
      const out = 100 + i;
      netnames[`n${i}`] = { bits: [out] };
      cells[`c${i}`] = {
        type,
        attributes: {},
        connections: type.startsWith('DFF')
          ? { CK: [0], D: [0], Q: [out] }
          : { A: [0], B: [0], C: [0], Y: [out] },
      };
    });
    // Trim the pins each type does not have, so `prepareNetlist` resolves them.
    for (const [key, cell] of Object.entries(cells)) {
      const c = cell as { type: string; connections: Record<string, unknown> };
      const keep = c.type === 'INV' || c.type === 'BUF' ? ['A', 'Y']
        : c.type.endsWith('3') || c.type === 'MUX2' ? ['A', 'B', 'C', 'Y']
        : c.type.startsWith('DFF') ? Object.keys(c.connections)
        : ['A', 'B', 'Y'];
      c.connections = Object.fromEntries(
        Object.entries(c.connections).filter(([pin]) => keep.includes(pin)),
      );
      if (c.type === 'DFF_R' || c.type === 'DFF_SR') c.connections.RST_N = [0];
      if (c.type === 'DFF_S' || c.type === 'DFF_SR') c.connections.SET_N = [0];
      cells[key] = c;
    }

    const netlist = {
      modules: {
        top: {
          ports: { clk: { direction: 'input', bits: [0] } },
          netnames,
          cells,
        },
      },
    };
    const prepared = prepareNetlist(netlist, null);
    expect(prepared.unresolvedTypes).toEqual([]);
    const { svg } = await renderSchematic(prepared.netlist);
    expect(svg).not.toContain('s:type="generic"');
  });
});
