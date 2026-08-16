import { describe, expect, it } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import { ApiProvider } from '../bridge/context';
import { ProjectProvider } from '../state/project';
import { SelectionProvider } from '../selection/bus';
import { setApi } from '../api';
import { FakeGatepack } from '../bridge/fake';
import { TruthTable } from './TruthTable';
import type { EstimateResult, SimulationTable } from '../../shared/api';

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

// The core's divergence table for a netlist that (wrongly) computes y = a & b,
// against the spec y = a ^ b: three of four minterms disagree.
function divergingTable(): SimulationTable {
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

function agreeingTable(): SimulationTable {
  return {
    inputNames: ['a', 'b'],
    outputNames: ['y'],
    rows: [
      { inputs: { a: '0', b: '0' }, expected: { y: '0' }, actual: { y: '0' }, diverges: false },
      { inputs: { a: '0', b: '1' }, expected: { y: '1' }, actual: { y: '1' }, diverges: false },
      { inputs: { a: '1', b: '0' }, expected: { y: '1' }, actual: { y: '1' }, diverges: false },
      { inputs: { a: '1', b: '1' }, expected: { y: '0' }, actual: { y: '0' }, diverges: false },
    ],
    dontCareCount: 0,
    unreachableCount: 0,
    exhaustive: true,
  };
}

function estimateResult(): EstimateResult {
  return { verdict: 'green', reasons: [], packageCount: 1, flopCount: 0, cellCounts: { AND2: 1 }, alternative: null };
}

function renderTable(fake: FakeGatepack) {
  setApi(fake);
  return render(
    <ApiProvider>
      <ProjectProvider>
        <SelectionProvider>
          <TruthTable />
        </SelectionProvider>
      </ProjectProvider>
    </ApiProvider>,
  );
}

describe('TruthTable — core divergence column', () => {
  it('highlights exactly the rows the core flags as diverging', async () => {
    const fake = new FakeGatepack({ specText: XOR2_SPEC });
    fake.setOk('simulate', divergingTable());
    fake.setOk('estimate', estimateResult());

    const { container } = renderTable(fake);

    await waitFor(() => {
      const divergentRows = container.querySelectorAll('tr[data-divergent="true"]');
      expect(divergentRows.length).toBe(3);
    });

    const divergentRows = Array.from(container.querySelectorAll('tr[data-divergent="true"]'));
    const rowNumbers = divergentRows.map((r) => r.querySelector('td')?.textContent ?? '');
    expect(rowNumbers).toEqual(['1', '2', '3']);
  });

  it('shows no divergence when the core table agrees', async () => {
    const fake = new FakeGatepack({ specText: XOR2_SPEC });
    fake.setOk('simulate', agreeingTable());
    fake.setOk('estimate', estimateResult());

    const { container } = renderTable(fake);

    await waitFor(() => {
      expect(container.querySelectorAll('tr[data-divergent="true"]').length).toBe(0);
    });
    expect(container.querySelectorAll('tbody tr').length).toBe(4);
  });

  it('renders the "no simulation table" state when synthesis has not run', async () => {
    const fake = new FakeGatepack({ specText: XOR2_SPEC });
    fake.setOk('estimate', estimateResult());

    const { container } = renderTable(fake);

    await waitFor(() => {
      expect(container.textContent).toContain('no simulation table');
    });
    expect(container.querySelectorAll('tbody tr').length).toBe(0);
  });
});
