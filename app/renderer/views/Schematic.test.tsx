import { describe, expect, it } from 'vitest';
import { render, waitFor, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ApiProvider } from '../bridge/context';
import { ProjectProvider } from '../state/project';
import { SelectionProvider } from '../selection/bus';
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

