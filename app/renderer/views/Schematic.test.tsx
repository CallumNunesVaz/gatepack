import { describe, expect, it } from 'vitest';
import { act, fireEvent, render, waitFor, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ApiProvider } from '../bridge/context';
import { ProjectProvider } from '../state/project';
import { SelectionProvider, useSelection } from '../selection/bus';
import { setApi } from '../api';
import { FakeGatepack } from '../bridge/fake';
import { Schematic } from './Schematic';
import { UNOBSERVABLE } from '../worker/schematicOverlay';
import type { AnalysisSummary, PackedView } from '../../shared/api';

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

// A two-gate mapped netlist whose instance names ($g1/$g2) the packed view's
// `instanceCells` reference, so the overlay can be hit-tested against the
// netlistsvg layout.
const TWO_GATE_NETLIST = {
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
        $g1: {
          hide_name: 1,
          type: 'NAND2',
          port_directions: { A: 'input', B: 'input', Y: 'output' },
          connections: { A: [0], B: [1], Y: [2] },
        },
        $g2: {
          hide_name: 1,
          type: 'NAND2',
          port_directions: { A: 'input', B: 'input', Y: 'output' },
          connections: { A: [2], B: [1], Y: [4] },
        },
      },
    },
  },
};

const PACKED: PackedView = {
  packages: [
    {
      refdes: 'U1',
      partNumber: '74AUP2G00',
      cells: ['NAND2__aaaa'],
      instanceCells: ['$g1'],
      capacity: 2,
      spare: 1,
      rationale: 'function group: NAND2 holds 1 gate(s), 1 spare gate(s)',
    },
    {
      refdes: 'U2',
      partNumber: '74AUP1G00',
      cells: ['NAND2__bbbb'],
      instanceCells: ['$g2'],
      capacity: 1,
      spare: 0,
      rationale: 'function group: NAND2 holds 1 gate(s)',
    },
  ],
};

function analysis(entries: Array<[string, number]>): AnalysisSummary {
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

function renderSchematic(fake: FakeGatepack) {
  setApi(fake);
  return render(
    <ApiProvider>
      <ProjectProvider>
        <SelectionProvider>
          <Schematic />
        </SelectionProvider>
      </ProjectProvider>
    </ApiProvider>,
  );
}

async function renderWithNetlist(fake: FakeGatepack) {
  const view = renderSchematic(fake);
  // wait for the mapped layer to actually lay out (cell groups present)
  await waitFor(() => {
    expect(view.container.querySelector('svg')).toBeTruthy();
  });
  return view;
}

describe('Schematic — honest failure reporting', () => {
  it('reports a mappedNetlist() failure instead of an endless spinner', async () => {
    const fake = new FakeGatepack({ specText: XOR2_SPEC });
    fake.setError('mappedNetlist', {
      severity: 'error',
      code: 'GP9999',
      message: 'core emitted no parseable JSON envelope',
    });

    const { container } = renderSchematic(fake);

    await waitFor(() => {
      expect(container.textContent).toContain('schematic unavailable');
    });
    expect(container.textContent).not.toContain('laying out the netlist');
  });

  it('reports an analyse() failure in the overlay instead of "(none reported)"', async () => {
    const fake = new FakeGatepack({ specText: XOR2_SPEC });
    fake.setError('analyse', {
      severity: 'error',
      code: 'GP9999',
      message: 'invalid choice: analyse',
    });

    const { container } = renderSchematic(fake);
    await userEvent.click(screen.getByLabelText('test points / unobservable nets'));

    await waitFor(() => {
      expect(container.textContent).toContain('analysis unavailable');
    });
    expect(container.textContent).not.toContain('(none reported)');
  });
});

describe('Schematic — packed layer', () => {
  it('renders one container per package with its refdes; spare slots distinct', async () => {
    const fake = new FakeGatepack({ specText: XOR2_SPEC });
    fake.setOk('mappedNetlist', TWO_GATE_NETLIST);
    fake.setOk('packedNetlist', PACKED);
    fake.setOk('analyse', analysis([['y', UNOBSERVABLE]]));
    const { container } = await renderWithNetlist(fake);

    await userEvent.click(screen.getByLabelText('packed netlist'));

    await waitFor(() => {
      expect(container.querySelectorAll('[data-testid="packed-package"]')).toHaveLength(2);
    });

    const refdes = Array.from(
      container.querySelectorAll('[data-testid="packed-package"]'),
    ).map((p) => p.getAttribute('data-refdes'));
    expect(refdes).toEqual(['U1', 'U2']);

    // U1 (capacity 2, spare 1) has one used and one spare slot; U2 (capacity 1,
    // spare 0) has one used slot. A spare slot is distinct from a used one.
    expect(container.querySelectorAll('[data-testid="packed-spare-slot"]')).toHaveLength(1);
    expect(container.querySelectorAll('[data-testid="packed-slot"]')).toHaveLength(2);
  });

  it('removes the packed containers when the layer is toggled off', async () => {
    const fake = new FakeGatepack({ specText: XOR2_SPEC });
    fake.setOk('mappedNetlist', TWO_GATE_NETLIST);
    fake.setOk('packedNetlist', PACKED);
    fake.setOk('analyse', analysis([]));
    const { container } = await renderWithNetlist(fake);

    await userEvent.click(screen.getByLabelText('packed netlist'));
    await waitFor(() => {
      expect(container.querySelectorAll('[data-testid="packed-package"]')).toHaveLength(2);
    });

    await userEvent.click(screen.getByLabelText('packed netlist'));
    await waitFor(() => {
      expect(container.querySelectorAll('[data-testid="packed-package"]')).toHaveLength(0);
    });
  });
});

function SelectorHarness() {
  const { setSelection } = useSelection();
  return (
    <button type="button" onClick={() => setSelection({ kind: 'cell', name: '$g1' })}>
      select g1
    </button>
  );
}

function renderWithSelector(fake: FakeGatepack) {
  setApi(fake);
  return render(
    <ApiProvider>
      <ProjectProvider>
        <SelectionProvider>
          <SelectorHarness />
          <Schematic />
        </SelectionProvider>
      </ProjectProvider>
    </ApiProvider>,
  );
}

describe('Schematic — §15.2 selection highlighting', () => {
  it('marks the selected cell in the SVG with the selection class', async () => {
    const fake = new FakeGatepack({ specText: XOR2_SPEC });
    fake.setOk('mappedNetlist', TWO_GATE_NETLIST);
    fake.setOk('packedNetlist', { packages: [] });
    fake.setOk('analyse', analysis([]));

    const { container } = renderWithSelector(fake);
    await waitFor(() => expect(container.querySelector('g[id^="cell_"]')).toBeTruthy());

    const cell = container.querySelector('g[id="cell_$g1"]');
    expect(cell).toBeTruthy();
    expect(cell).not.toHaveClass('gp-sel');

    fireEvent.click(screen.getByText('select g1'));

    await waitFor(() => expect(cell).toHaveClass('gp-sel'));
  });
});

describe('Schematic — zoom controls', () => {
  it('zooms in and out around the readout, clamped to the allowed range', async () => {
    const fake = new FakeGatepack({ specText: XOR2_SPEC });
    fake.setOk('mappedNetlist', TWO_GATE_NETLIST);
    fake.setOk('packedNetlist', { packages: [] });
    fake.setOk('analyse', analysis([]));

    renderSchematic(fake);
    await waitFor(() => expect(screen.getByTestId('schematic-zoom')).toBeTruthy());
    expect(screen.getByTestId('schematic-zoom').textContent).toBe('100%');

    fireEvent.click(screen.getByLabelText('Zoom in'));
    await waitFor(() => expect(screen.getByTestId('schematic-zoom').textContent).toBe('125%'));

    fireEvent.click(screen.getByLabelText('Zoom out'));
    await waitFor(() => expect(screen.getByTestId('schematic-zoom').textContent).toBe('100%'));
  });
});

describe('Schematic — overlay layer', () => {
  it('marks exactly the unobservable nets and no others', async () => {
    const spec = `${XOR2_SPEC}test_points:\n  - {net: tp1}\n`;
    const fake = new FakeGatepack({ specText: spec });
    fake.setOk('mappedNetlist', TWO_GATE_NETLIST);
    fake.setOk('packedNetlist', { packages: [] });
    fake.setOk(
      'analyse',
      analysis([
        ['y', UNOBSERVABLE],
        ['n1', UNOBSERVABLE],
        ['a', 5],
        ['b', 3],
      ]),
    );
    const { container } = await renderWithNetlist(fake);

    await userEvent.click(screen.getByLabelText('test points / unobservable nets'));

    await waitFor(() => {
      expect(container.querySelectorAll('[data-testid="unobservable-net"]')).toHaveLength(2);
    });

    const unobservable = Array.from(
      container.querySelectorAll('[data-testid="unobservable-net"]'),
    ).map((m) => m.getAttribute('data-net'));
    expect(unobservable.sort()).toEqual(['n1', 'y']);

    const testPoints = Array.from(container.querySelectorAll('[data-testid="test-point"]')).map(
      (m) => m.getAttribute('data-net'),
    );
    expect(testPoints).toEqual(['tp1']);
  });

  it('removes the overlay markers when the layer is toggled off', async () => {
    const fake = new FakeGatepack({ specText: XOR2_SPEC });
    fake.setOk('mappedNetlist', TWO_GATE_NETLIST);
    fake.setOk('packedNetlist', { packages: [] });
    fake.setOk('analyse', analysis([['y', UNOBSERVABLE]]));
    const { container } = await renderWithNetlist(fake);

    await userEvent.click(screen.getByLabelText('test points / unobservable nets'));
    await waitFor(() => {
      expect(container.querySelectorAll('[data-testid="unobservable-net"]')).toHaveLength(1);
    });

    await userEvent.click(screen.getByLabelText('test points / unobservable nets'));
    await waitFor(() => {
      expect(container.querySelectorAll('[data-testid="unobservable-net"]')).toHaveLength(0);
    });
  });
});


/**
 * A sequential design with the §9.3 reset chain, shaped as Yosys writes it
 * after `abc`: no `port_directions` on any cell. The view has to supply them
 * before netlistsvg sees the netlist, or nothing routes.
 */
const SEQ_SPEC = `name: seq
timing_model: synchronous
clock: {signal: clk, freq_hz: 1000, source: OSC}
reset: {signal: rst_n, active: low, source: SUPERVISOR}
encoding: one_hot
inputs:
  - {name: d, sync: false}
outputs:
  - {name: q}
states: [S0]
initial: S0
transitions:
  - {from: S0, to: S0, when: "1"}
output_logic:
  q: "d"
`;

const SEQ_NETLIST = {
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
      },
      cells: {
        sync1: { type: 'DFF_R', attributes: {}, connections: { CK: [0], D: ['1'], Q: [3], RST_N: [1] } },
        sync2: { type: 'DFF_R', attributes: {}, connections: { CK: [0], D: [3], Q: [4], RST_N: [1] } },
        state: { type: 'DFF_R', attributes: {}, connections: { CK: [0], D: [2], Q: [5], RST_N: [4] } },
      },
    },
  },
};

function stamps(container: HTMLElement, cls: string): string[] {
  return Array.from(container.querySelectorAll(`.${cls}`)).map(
    (el) => el.getAttribute('data-gp-value') ?? '',
  );
}

describe('Schematic — the netlist actually routes', () => {
  it('draws wires for a post-abc netlist that carries no port_directions', async () => {
    // The defect that made this view useless: with no directions netlistsvg
    // classified no ports, drew no wires, and rendered a column of type names.
    const fake = new FakeGatepack({ specText: XOR2_SPEC });
    fake.setOk('mappedNetlist', {
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
    });
    fake.setOk('packedNetlist', { packages: [] });
    fake.setOk('analyse', analysis([]));
    const { container } = await renderWithNetlist(fake);

    await waitFor(() => {
      expect(container.querySelectorAll('[class*="net_"]').length).toBeGreaterThan(0);
    });
    expect(container.querySelector('svg')?.innerHTML).not.toContain('s:type="generic"');
    expect(container.querySelector('[data-testid="schematic-unresolved"]')).toBeNull();
  });

  it('names a cell by its package refdes and library type', async () => {
    const fake = new FakeGatepack({ specText: XOR2_SPEC });
    fake.setOk('mappedNetlist', TWO_GATE_NETLIST);
    fake.setOk('packedNetlist', PACKED);
    fake.setOk('analyse', analysis([]));
    const { container } = await renderWithNetlist(fake);

    await waitFor(() => {
      const labels = Array.from(container.querySelectorAll('text[s\\:attribute="gp_refdes"]')).map(
        (t) => t.textContent,
      );
      expect(labels.sort()).toEqual(['U1', 'U2']);
    });
    const types = Array.from(container.querySelectorAll('text[s\\:attribute="gp_type"]')).map(
      (t) => t.textContent,
    );
    expect(types).toEqual(['NAND2', 'NAND2']);
  });

  it('says which cell types it has no pin table for, rather than drawing them bare', async () => {
    const fake = new FakeGatepack({ specText: XOR2_SPEC });
    fake.setOk('mappedNetlist', {
      modules: {
        top: {
          ports: { a: { direction: 'input', bits: [0] } },
          netnames: { a: { bits: [0] } },
          cells: { u1: { type: 'CNT4', attributes: {}, connections: { CP: [0] } } },
        },
      },
    });
    fake.setOk('packedNetlist', { packages: [] });
    fake.setOk('analyse', analysis([]));
    const { container } = await renderWithNetlist(fake);

    await waitFor(() => {
      expect(container.querySelector('[data-testid="schematic-unresolved"]')?.textContent).toContain(
        'CNT4',
      );
    });
  });
});

describe('Schematic — signal value overlay (§24.2)', () => {
  it('stamps every wire with its evaluated value', async () => {
    const fake = new FakeGatepack({ specText: XOR2_SPEC });
    fake.setOk('mappedNetlist', TWO_GATE_NETLIST);
    fake.setOk('packedNetlist', { packages: [] });
    fake.setOk('analyse', analysis([]));
    const { container } = await renderWithNetlist(fake);

    // Probe defaults: both inputs low. NAND2(0,0) = 1 on n1; NAND2(1,0) = 1 on y.
    await waitFor(() => {
      expect(stamps(container, 'net_0').length).toBeGreaterThan(0);
    });
    expect(stamps(container, 'net_0').every((v) => v === '0')).toBe(true);
    expect(stamps(container, 'net_2').every((v) => v === '1')).toBe(true);
    expect(stamps(container, 'net_4').every((v) => v === '1')).toBe(true);
  });

  it('re-stamps the sheet when a probe pin is driven, without re-laying it out', async () => {
    const fake = new FakeGatepack({ specText: XOR2_SPEC });
    fake.setOk('mappedNetlist', TWO_GATE_NETLIST);
    fake.setOk('packedNetlist', { packages: [] });
    fake.setOk('analyse', analysis([]));
    const { container } = await renderWithNetlist(fake);
    await waitFor(() => expect(stamps(container, 'net_0').length).toBeGreaterThan(0));
    const layout = container.querySelector('svg')?.getAttribute('width');

    // a=1, b=1 -> n1 = NAND(1,1) = 0 -> y = NAND(0,1) = 1.
    await userEvent.click(screen.getByTestId('probe-pin-a'));
    await userEvent.click(screen.getByTestId('probe-pin-b'));

    await waitFor(() => {
      expect(stamps(container, 'net_0').every((v) => v === '1')).toBe(true);
    });
    expect(stamps(container, 'net_2').every((v) => v === '0')).toBe(true);
    expect(container.querySelector('svg')?.getAttribute('width')).toBe(layout);
  });

  it('clears the stamps when the layer is switched off', async () => {
    const fake = new FakeGatepack({ specText: XOR2_SPEC });
    fake.setOk('mappedNetlist', TWO_GATE_NETLIST);
    fake.setOk('packedNetlist', { packages: [] });
    fake.setOk('analyse', analysis([]));
    const { container } = await renderWithNetlist(fake);
    await waitFor(() => expect(stamps(container, 'net_0').length).toBeGreaterThan(0));

    await userEvent.click(screen.getByLabelText('signal values'));
    await waitFor(() => {
      expect(container.querySelectorAll('[data-gp-value]')).toHaveLength(0);
    });
    expect(screen.queryByTestId('schematic-probe')).toBeNull();
  });

  it('offers no clock controls for a combinational netlist', async () => {
    const fake = new FakeGatepack({ specText: XOR2_SPEC });
    fake.setOk('mappedNetlist', TWO_GATE_NETLIST);
    fake.setOk('packedNetlist', { packages: [] });
    fake.setOk('analyse', analysis([]));
    await renderWithNetlist(fake);
    await waitFor(() => expect(screen.getByTestId('schematic-probe')).toBeTruthy());
    expect(screen.queryByTestId('schematic-step')).toBeNull();
  });
});

describe('Schematic — clocked probe on a sequential design', () => {
  async function seqView() {
    const fake = new FakeGatepack({ specText: SEQ_SPEC });
    fake.setOk('mappedNetlist', SEQ_NETLIST);
    fake.setOk('packedNetlist', { packages: [] });
    fake.setOk('analyse', analysis([]));
    const view = await renderWithNetlist(fake);
    await waitFor(() => expect(screen.getByTestId('schematic-step')).toBeTruthy());
    return view;
  }

  it('starts with the flops unknown — a board at power-on has no state', async () => {
    const { container } = await seqView();
    await waitFor(() => expect(stamps(container, 'net_5').length).toBeGreaterThan(0));
    // q is a flop output nobody has clocked yet. Unknown is the true reading;
    // showing it as low would be a value the view did not measure.
    expect(stamps(container, 'net_5').every((v) => v === 'x')).toBe(true);
  });

  it('a reset pulse leaves the design defined and the reset released', async () => {
    const { container } = await seqView();
    await waitFor(() => expect(stamps(container, 'net_5').length).toBeGreaterThan(0));

    await userEvent.click(screen.getByTestId('schematic-reset'));

    await waitFor(() => {
      expect(stamps(container, 'net_5').every((v) => v === '0')).toBe(true);
    });
    // Assert -> release -> three edges: the synchroniser has let go, so the
    // reset net is high again and the button now offers to re-assert it.
    expect(stamps(container, 'net_4').every((v) => v === '1')).toBe(true);
    expect(screen.getByTestId('schematic-reset').textContent).toContain('Reset');
  });

  it('holding reset clears the state flop with no clock edge at all', async () => {
    const { container } = await seqView();
    await userEvent.click(screen.getByTestId('schematic-reset'));
    await waitFor(() => expect(stamps(container, 'net_4').every((v) => v === '1')).toBe(true));

    // Drive d high and clock it in, so the flop is demonstrably holding a one.
    await userEvent.click(screen.getByTestId('probe-pin-d'));
    await userEvent.click(screen.getByTestId('schematic-step'));
    await waitFor(() => expect(stamps(container, 'net_5').every((v) => v === '1')).toBe(true));

    // Now assert reset by hand and take no edge. The §9.3 chain clears the
    // synchronisers, which clears the state flop — level-sensitive, no clock.
    await userEvent.click(screen.getByTestId('probe-pin-rst_n'));
    await waitFor(() => {
      expect(stamps(container, 'net_5').every((v) => v === '0')).toBe(true);
    });
    expect(screen.getByTestId('schematic-readout').textContent).toContain('async control holding 3 flops');
  });

  it('a step advances one edge and Clear state returns the flops to unknown', async () => {
    const { container } = await seqView();
    await userEvent.click(screen.getByTestId('schematic-reset'));
    await waitFor(() => expect(stamps(container, 'net_5').every((v) => v === '0')).toBe(true));

    await userEvent.click(screen.getByTestId('probe-pin-d'));
    await userEvent.click(screen.getByTestId('schematic-step'));
    await waitFor(() => expect(stamps(container, 'net_5').every((v) => v === '1')).toBe(true));

    await userEvent.click(screen.getByTestId('schematic-clear'));
    await waitFor(() => expect(stamps(container, 'net_5').every((v) => v === 'x')).toBe(true));
  });

  it('shows a materialised constant as the value it is tied to, not as unknown', async () => {
    const { container } = await seqView();
    // sync1's D is a literal 1. netlistsvg puts it on a synthesised net that
    // appears in no `netnames`, so without the constant map it renders unknown.
    await waitFor(() => expect(container.querySelectorAll('[data-gp-value]').length).toBeGreaterThan(0));
    const values = Array.from(container.querySelectorAll('[data-gp-value]')).map((el) => ({
      net: el.getAttribute('data-gp-net'),
      value: el.getAttribute('data-gp-value'),
    }));
    const tie = values.filter((v) => v.net === "1'b1");
    expect(tie.length).toBeGreaterThan(0);
    expect(tie.every((v) => v.value === '1')).toBe(true);
  });
});

describe('Schematic — spec editing (§C12)', () => {
  const COMMENTED_SPEC = `# the sequence detector
name: xor2
timing_model: synchronous
clock: {signal: clk, freq_hz: 1000, source: OSC}
# the reset chain (§9.3)
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

  const GENERATED_NETLIST = {
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
          $abc$133$new_n12_: { bits: [2] },
          y: { bits: [4] },
        },
        cells: {
          $g1: {
            hide_name: 1,
            type: 'NAND2',
            port_directions: { A: 'input', B: 'input', Y: 'output' },
            connections: { A: [0], B: [1], Y: [2] },
          },
          $g2: {
            hide_name: 1,
            type: 'NAND2',
            port_directions: { A: 'input', B: 'input', Y: 'output' },
            connections: { A: [2], B: [1], Y: [4] },
          },
        },
      },
    },
  };

  async function editView(fake: FakeGatepack) {
    const view = await renderWithNetlist(fake);
    await waitFor(() => expect(containerOf(view).querySelector('[data-gp-net]')).toBeTruthy());
    await userEvent.click(screen.getByTestId('schematic-edit-toggle'));
    return view;
  }

  function containerOf(view: ReturnType<typeof renderSchematic>) {
    return view.container;
  }

  it('toggles a test point and preserves the user comments and unrelated formatting', async () => {
    const fake = new FakeGatepack({ specText: COMMENTED_SPEC });
    fake.setOk('mappedNetlist', TWO_GATE_NETLIST);
    fake.setOk('packedNetlist', { packages: [] });
    fake.setOk('analyse', analysis([]));
    const { container } = await editView(fake);

    fireEvent.click(container.querySelector('[data-gp-net="a"]') as Element);

    await waitFor(() => {
      expect(fake.specText).toContain('test_points:');
    });
    expect(fake.specText).toContain('net: a');
    // Round-tripping through the model would have reformatted the file away —
    // the comments and unrelated lines survive because the edit is a splice.
    expect(fake.specText).toContain('# the sequence detector');
    expect(fake.specText).toContain('# the reset chain (§9.3)');
    expect(fake.specText.indexOf('name: xor2')).toBeLessThan(fake.specText.indexOf('test_points:'));
  });

  it('refuses a generated net name and leaves design.yaml untouched', async () => {
    const fake = new FakeGatepack({ specText: XOR2_SPEC });
    fake.setOk('mappedNetlist', GENERATED_NETLIST);
    fake.setOk('packedNetlist', { packages: [] });
    fake.setOk('analyse', analysis([]));
    const { container } = await editView(fake);

    const before = fake.specText;
    fireEvent.click(container.querySelector('[data-gp-net="$abc$133$new_n12_"]') as Element);

    await waitFor(() => {
      expect(screen.getByTestId('schematic-edit-refusal').textContent).toContain(
        'cannot be recorded',
      );
    });
    expect(fake.specText).toBe(before);
    expect(fake.specText).not.toContain('test_points');
  });

  it('does nothing when the edit toggle is off — clicking a net inspects, never rewrites', async () => {
    const fake = new FakeGatepack({ specText: XOR2_SPEC });
    fake.setOk('mappedNetlist', TWO_GATE_NETLIST);
    fake.setOk('packedNetlist', { packages: [] });
    fake.setOk('analyse', analysis([]));
    const { container } = await renderWithNetlist(fake);
    await waitFor(() => expect(container.querySelector('[data-gp-net]')).toBeTruthy());

    const before = fake.specText;
    fireEvent.click(container.querySelector('[data-gp-net="a"]') as Element);

    // Wait past the 400ms write debounce before concluding nothing happened.
    // Asserting synchronously proves nothing: the write path is debounced, so
    // an assertion taken immediately passes whether or not the click was
    // treated as an edit. Verified by forcing edit mode on — the synchronous
    // form still passed; this form fails.
    await new Promise((r) => setTimeout(r, 700));
    expect(fake.specText).toBe(before);
    expect(fake.writes).toHaveLength(0);
  });

  it('toggles an input synchroniser from its port symbol', async () => {
    const fake = new FakeGatepack({ specText: XOR2_SPEC });
    fake.setOk('mappedNetlist', TWO_GATE_NETLIST);
    fake.setOk('packedNetlist', { packages: [] });
    fake.setOk('analyse', analysis([]));
    const { container } = await editView(fake);

    fireEvent.click(container.querySelector('[id="cell_a"]') as Element);

    await waitFor(() => {
      expect(fake.specText).toContain('name: a, sync: true');
    });
    expect(fake.specText).toContain('name: b, sync: false');
  });

  it('regroups a gate into a package and writes stable names, not instance names', async () => {
    const fake = new FakeGatepack({ specText: XOR2_SPEC });
    fake.setOk('mappedNetlist', TWO_GATE_NETLIST);
    fake.setOk('packedNetlist', PACKED);
    fake.setOk('analyse', analysis([]));
    const { container } = await editView(fake);

    await userEvent.click(screen.getByLabelText('packed netlist'));
    await waitFor(() => {
      expect(container.querySelector('[data-refdes="U2"]')).toBeTruthy();
    });

    fireEvent.mouseDown(container.querySelector('[id="cell_$g1"]') as Element);
    fireEvent.mouseUp(container.querySelector('[data-refdes="U2"]') as Element);

    await waitFor(() => {
      expect(fake.specText).toContain('force_groups');
    });
    expect(fake.specText).toContain('NAND2__aaaa');
    expect(fake.specText).toContain('NAND2__bbbb');
    // The rendered SVG is keyed by ABC instance names; persisting one is the
    // defect this path exists to prevent.
    expect(fake.specText).not.toMatch(/force_groups[\s\S]*\$g1/);
    expect(fake.specText).not.toContain('position');
  });

  it('reaches the regroup refusal through a click when the packed view is empty', async () => {
    // An empty packed view has no `[data-refdes]` boundary, so a regroup drag
    // used to be silently swallowed and the "run a build" refusal was
    // unreachable. The empty drop target makes it reachable: dropping a gate on
    // it must show the refusal, not write anything.
    const fake = new FakeGatepack({ specText: XOR2_SPEC });
    fake.setOk('mappedNetlist', TWO_GATE_NETLIST);
    fake.setOk('packedNetlist', { packages: [] });
    fake.setOk('analyse', analysis([]));
    const { container } = await editView(fake);

    await userEvent.click(screen.getByLabelText('packed netlist'));
    const dropZone = container.querySelector('[data-testid="schematic-drop-zone"]') as Element;
    expect(dropZone).toBeTruthy();

    const before = fake.specText;
    fireEvent.mouseDown(container.querySelector('[id="cell_$g1"]') as Element);
    fireEvent.mouseUp(dropZone);

    await waitFor(() => {
      expect(screen.getByTestId('schematic-edit-refusal').textContent).toContain(
        'Run a build before regrouping',
      );
    });
    expect(fake.specText).toBe(before);
    expect(fake.specText).not.toContain('force_groups');
  });
});

describe('Schematic — flow and hover (Falstad cues)', () => {
  it('runs travelling dots on the high wires and stops when the layer is off', async () => {
    const fake = new FakeGatepack({ specText: XOR2_SPEC });
    fake.setOk('mappedNetlist', TWO_GATE_NETLIST);
    fake.setOk('packedNetlist', { packages: [] });
    fake.setOk('analyse', analysis([]));
    const { container } = await renderWithNetlist(fake);

    await waitFor(() => {
      expect(container.querySelectorAll('.gp-flow-layer > *').length).toBeGreaterThan(0);
    });
    expect(container.querySelector('[data-testid="schematic-svg"]')?.getAttribute('data-flow')).toBe('on');

    await userEvent.click(screen.getByLabelText('flow animation'));
    await waitFor(() => {
      expect(container.querySelectorAll('.gp-flow-layer')).toHaveLength(0);
    });
    // The values themselves survive: the animation was never what carried them.
    expect(stamps(container, 'net_2').every((v) => v === '1')).toBe(true);
  });

  it('reads out the net under the pointer and lights all of its segments', async () => {
    const fake = new FakeGatepack({ specText: XOR2_SPEC });
    fake.setOk('mappedNetlist', TWO_GATE_NETLIST);
    fake.setOk('packedNetlist', { packages: [] });
    fake.setOk('analyse', analysis([]));
    const { container } = await renderWithNetlist(fake);
    await waitFor(() => expect(stamps(container, 'net_0').length).toBeGreaterThan(0));

    const wire = container.querySelector('.net_2') as Element;
    fireEvent.mouseOver(wire, { bubbles: true });

    await waitFor(() => {
      expect(screen.getByTestId('schematic-readout').textContent).toContain('n1');
    });
    const lit = container.querySelectorAll('[data-gp-hover]');
    expect(lit.length).toBe(container.querySelectorAll('.net_2').length);
    expect(lit.length).toBeGreaterThan(0);
  });

  it('counts the sheet by value so the readout is a measurement, not a mood', async () => {
    const fake = new FakeGatepack({ specText: XOR2_SPEC });
    fake.setOk('mappedNetlist', TWO_GATE_NETLIST);
    fake.setOk('packedNetlist', { packages: [] });
    fake.setOk('analyse', analysis([]));
    await renderWithNetlist(fake);
    await waitFor(() => expect(screen.getByTestId('schematic-readout')).toBeTruthy());
    // a=0, b=0 -> n1=1, y=1: two high nets, two low inputs, nothing unknown.
    expect(screen.getByTestId('schematic-readout').textContent).toContain('2 high');
    expect(screen.getByTestId('schematic-readout').textContent).toContain('0 unknown');
  });
});

describe('Schematic — the sheet says when it no longer matches the spec', () => {
  it('flags stale after an edit, stops drawing values, and offers a rebuild', async () => {
    // The defect this pins: the view fetched `mappedNetlist()` once at mount and
    // never again, with no staleness signal. Measured before the fix —
    // mappedNetlist calls before=2 after=2 — so it kept drawing live 0/1 values
    // for a design that no longer existed.
    const fake = new FakeGatepack({ specText: XOR2_SPEC });
    fake.setOk('mappedNetlist', TWO_GATE_NETLIST);
    fake.setOk('packedNetlist', { packages: [] });
    fake.setOk('analyse', analysis([]));
    const { container } = await renderWithNetlist(fake);
    await waitFor(() => expect(stamps(container, 'net_0').length).toBeGreaterThan(0));
    expect(screen.queryByTestId('schematic-stale')).toBeNull();

    // Any edit, from any view: toggling an input's sync is enough.
    await act(async () => {
      await userEvent.click(screen.getByTestId('schematic-edit-toggle'));
    });
    fireEvent.click(container.querySelector('[id="cell_a"]') as Element);

    await waitFor(() => expect(screen.getByTestId('schematic-stale')).toBeTruthy());
    // Values are withdrawn rather than recoloured: the netlist they were
    // computed from no longer corresponds to the spec.
    await waitFor(() => {
      expect(container.querySelectorAll('[data-gp-value]')).toHaveLength(0);
    });
    expect(screen.getByTestId('schematic-rebuild')).toBeTruthy();
  });

  it('a rebuild refetches the netlist and clears the flag', async () => {
    const fake = new FakeGatepack({ specText: XOR2_SPEC });
    fake.setOk('mappedNetlist', TWO_GATE_NETLIST);
    fake.setOk('packedNetlist', { packages: [] });
    fake.setOk('analyse', analysis([]));
    const { container } = await renderWithNetlist(fake);
    await waitFor(() => expect(stamps(container, 'net_0').length).toBeGreaterThan(0));

    await act(async () => {
      await userEvent.click(screen.getByTestId('schematic-edit-toggle'));
    });
    fireEvent.click(container.querySelector('[id="cell_a"]') as Element);
    await waitFor(() => expect(screen.getByTestId('schematic-stale')).toBeTruthy());

    const before = fake.calls.filter((c) => c.command === 'mappedNetlist').length;
    await act(async () => {
      await userEvent.click(screen.getByTestId('schematic-rebuild'));
    });

    // The netlist is re-read only after the build, not instead of it: reading
    // the same stale file again would only look fresher.
    await waitFor(() => {
      expect(fake.calls.filter((c) => c.command === 'mappedNetlist').length).toBeGreaterThan(before);
    });
    await waitFor(() => expect(screen.queryByTestId('schematic-stale')).toBeNull());
  });
});
