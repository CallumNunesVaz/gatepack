import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ApiProvider } from '../bridge/context';
import { ProjectProvider } from '../state/project';
import { SelectionProvider } from '../selection/bus';
import { setVerifyResult } from '../selection/linkData';
import { setApi } from '../api';
import { FakeGatepack } from '../bridge/fake';
import { VerificationPanel } from './VerificationPanel';
import type { VerifyResult } from '../../shared/api';

function verifyResult(): VerifyResult {
  return {
    checks: [
      {
        name: 'property p1',
        kind: 'property',
        status: 'failed',
        durationMs: 1,
        counterexample: {
          steps: [
            { clk: '1', state_A: '1' },
            { clk: '0', state_B: '1' },
          ],
          pointers: ['design.yaml:5:states', 'design.yaml:12:properties'],
        },
      },
      {
        name: 'property p2',
        kind: 'property',
        status: 'passed',
        durationMs: 1,
      },
    ],
    allPassed: false,
  };
}

function renderPanel(fake: FakeGatepack) {
  setVerifyResult(null);
  setApi(fake);
  return render(
    <ApiProvider>
      <ProjectProvider>
        <SelectionProvider>
          <VerificationPanel />
        </SelectionProvider>
      </ProjectProvider>
    </ApiProvider>,
  );
}

describe('VerificationPanel — property and counterexample selection', () => {
  it('clicking a failing property emits and reflects a property selection', async () => {
    const fake = new FakeGatepack();
    fake.setOk('verify', verifyResult());

    renderPanel(fake);
    fireEvent.click(screen.getByText('Run verification'));
    await waitFor(() => expect(screen.getByTestId('verification-result')).toBeTruthy());

    const row = screen.getByText('property p1').closest('li');
    expect(row).toBeTruthy();
    expect(row).not.toHaveAttribute('data-highlight', 'true');

    fireEvent.click(row as HTMLElement);
    await waitFor(() => expect(row).toHaveAttribute('data-highlight', 'true'));

    // The passed property is not selected and does not highlight.
    const p2 = screen.getByText('property p2').closest('li');
    expect(p2).not.toHaveAttribute('data-highlight', 'true');
  });

  it('clicking a counterexample step emits a step selection and reflects that cycle', async () => {
    const fake = new FakeGatepack();
    fake.setOk('verify', verifyResult());

    renderPanel(fake);
    fireEvent.click(screen.getByText('Run verification'));
    await waitFor(() => expect(screen.getByTestId('verification-result')).toBeTruthy());

    const step0 = screen.getAllByRole('row').find((r) => r.getAttribute('data-cycle') === '0');
    expect(step0).toBeTruthy();
    expect(step0).not.toHaveAttribute('data-highlight', 'true');

    fireEvent.click(step0 as HTMLElement);
    await waitFor(() => expect(step0).toHaveAttribute('data-highlight', 'true'));

    // Selecting a step must not also select the property (stopPropagation).
    const row = screen.getByText('property p1').closest('li');
    expect(row).not.toHaveAttribute('data-highlight', 'true');
  });

  it('shows the "no verification run" state before any run', async () => {
    const fake = new FakeGatepack();
    fake.setOk('verify', verifyResult());
    renderPanel(fake);
    await waitFor(() => expect(screen.getByText(/No verification has been run/)).toBeTruthy());
  });
});
