import { describe, expect, it } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import { ApiProvider, useApi } from '../bridge/context';
import { setApi } from '../api';
import { FakeGatepack } from '../bridge/fake';
import { useRevisionedTask } from './useRevisionedTask';
import type { EstimateResult } from '../../shared/api';

function estimateResult(): EstimateResult {
  return {
    verdict: 'green',
    reasons: [],
    packageCount: 3,
    flopCount: 2,
    cellCounts: { XOR2: 1 },
    alternative: null,
  };
}

function Harness({ revision, onRun }: { revision: number; onRun?: () => void }) {
  const api = useApi();
  const { state, run, isStale } = useRevisionedTask<EstimateResult>(revision, (t) => api.estimate(t));
  return (
    <div>
      <button onClick={() => { run(); onRun?.(); }}>run</button>
      <span data-testid="status">{state.status}</span>
      {isStale ? <span data-testid="stale">stale</span> : null}
      {state.data ? <span data-testid="packages">{state.data.packageCount}</span> : null}
    </div>
  );
}

function renderHarness(revision: number, fake: FakeGatepack, onRun?: () => void) {
  setApi(fake);
  return render(
    <ApiProvider>
      <Harness revision={revision} onRun={onRun} />
    </ApiProvider>,
  );
}

describe('useRevisionedTask — stale results are never shown as live', () => {
  it('cancels in-flight work when the revision changes', async () => {
    const fake = new FakeGatepack();
    fake.setOk('estimate', estimateResult());
    const { rerender } = renderHarness(0, fake);

    await act(async () => {
      screen.getByText('run').click();
    });
    expect(fake.calls.some((c) => c.command === 'estimate')).toBe(true);
    const firstToken = fake.calls.find((c) => c.command === 'estimate')?.token;
    expect(firstToken).toBeDefined();

    // The document changes.
    await act(async () => {
      rerender(
        <ApiProvider>
          <Harness revision={1} />
        </ApiProvider>,
      );
    });

    expect(fake.cancelled).toContain(firstToken);
  });

  it('marks an already-arrived result stale after an edit', async () => {
    const fake = new FakeGatepack();
    fake.setOk('estimate', estimateResult());
    const { rerender } = renderHarness(0, fake);

    await act(async () => {
      screen.getByText('run').click();
    });
    expect(screen.queryByTestId('packages')?.textContent).toBe('3');
    expect(screen.queryByTestId('stale')).toBeNull();

    await act(async () => {
      rerender(
        <ApiProvider>
          <Harness revision={1} />
        </ApiProvider>,
      );
    });

    expect(screen.getByTestId('stale')).toBeTruthy();
  });

  it('discards a result that arrives after it has been superseded', async () => {
    const fake = new FakeGatepack();
    let resolveLate: (() => void) | null = null;
    fake.setHook('estimate', () => new Promise<void>((res) => { resolveLate = () => res(); }));
    fake.setOk('estimate', estimateResult());

    const { rerender } = renderHarness(0, fake);
    await act(async () => {
      screen.getByText('run').click();
    });
    expect(screen.getByTestId('status').textContent).toBe('running');

    // Edit the document while the call is in flight.
    await act(async () => {
      rerender(
        <ApiProvider>
          <Harness revision={1} />
        </ApiProvider>,
      );
    });

    // The stale result resolves late — it must not become visible.
    await act(async () => {
      resolveLate?.();
    });
    expect(screen.queryByTestId('packages')).toBeNull();
  });
});
