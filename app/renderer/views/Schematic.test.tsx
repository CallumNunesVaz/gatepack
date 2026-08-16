import { describe, expect, it } from 'vitest';
import { render, waitFor, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ApiProvider } from '../bridge/context';
import { ProjectProvider } from '../state/project';
import { SelectionProvider } from '../selection/bus';
import { setApi } from '../api';
import { FakeGatepack } from '../bridge/fake';
import { Schematic } from './Schematic';

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
