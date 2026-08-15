import { describe, expect, it } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import { ApiProvider } from '../bridge/context';
import { ProjectProvider } from '../state/project';
import { setApi } from '../api';
import { FakeGatepack } from '../bridge/fake';
import { TruthTable } from './TruthTable';
import type { EstimateResult } from '../../shared/api';

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

// A mapped netlist that (wrongly) computes y = a & b, so it disagrees with the
// spec's y = a ^ b on exactly three minterms: (0,1), (1,0) and (1,1).
const AND_NETLIST = {
  modules: {
    xor2: {
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
        $and: {
          hide_name: 1,
          type: 'AND2',
          port_directions: { A: 'input', B: 'input', Y: 'output' },
          connections: { A: [0], B: [1], Y: [2] },
        },
      },
    },
  },
};

function estimateResult(): EstimateResult {
  return { verdict: 'green', reasons: [], packageCount: 1, flopCount: 0, cellCounts: { AND2: 1 }, alternative: null };
}

function renderTable(fake: FakeGatepack) {
  setApi(fake);
  return render(
    <ApiProvider>
      <ProjectProvider>
        <TruthTable />
      </ProjectProvider>
    </ApiProvider>,
  );
}

describe('TruthTable — divergence highlighting', () => {
  it('highlights exactly the minterms where live and simulated outputs disagree', async () => {
    const fake = new FakeGatepack({ specText: XOR2_SPEC });
    fake.setOk('mappedNetlist', AND_NETLIST);
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

  it('shows no divergence when the netlist agrees with the spec', async () => {
    // An XOR2 netlist that agrees with the spec (y = a ^ b).
    const xorNetlist = {
      modules: {
        xor2: {
          ports: {
            a: { direction: 'input', bits: [0] },
            b: { direction: 'input', bits: [1] },
            y: { direction: 'output', bits: [2] },
          },
          netnames: { a: { bits: [0] }, b: { bits: [1] }, y: { bits: [2] } },
          cells: {
            $xor: { hide_name: 1, type: 'XOR2', port_directions: { A: 'input', B: 'input', Y: 'output' }, connections: { A: [0], B: [1], Y: [2] } },
          },
        },
      },
    };
    const fake = new FakeGatepack({ specText: XOR2_SPEC });
    fake.setOk('mappedNetlist', xorNetlist);
    fake.setOk('estimate', estimateResult());

    const { container } = renderTable(fake);

    await waitFor(() => {
      expect(container.querySelectorAll('tr[data-divergent="true"]').length).toBe(0);
    });
    expect(container.querySelectorAll('tr').length).toBe(5); // header + 4 minterms
  });
});
