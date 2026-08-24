/**
 * The run-request bus: `request(id)` / `useRunRequest(id, fn)`.
 *
 * The one property that matters here is that *mounting a view is not a run*.
 * The shell switches to the owning view and then requests a run, and React
 * batches both into one render — so the request is already pending by the time
 * the view mounts. The hook must (a) never fire on a plain mount, (b) fire when
 * a request arrives after mount, and (c) drain a request that raced mount
 * without firing twice.
 */

import { describe, expect, it, vi } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import { RunRequestsProvider, useRunRequest, useRunRequests } from './runRequests';

function Probe({ id, onRun }: { id: string; onRun: () => void }) {
  useRunRequest(id, onRun);
  return <span data-testid="probe">probe</span>;
}

function Driver({ id }: { id: string }) {
  const { request } = useRunRequests();
  return (
    <button data-testid="driver" onClick={() => request(id)}>
      request
    </button>
  );
}

describe('useRunRequest — mounting is not a run', () => {
  it('does not fire on mount', () => {
    const onRun = vi.fn();
    render(
      <RunRequestsProvider>
        <Probe id="run.build" onRun={onRun} />
      </RunRequestsProvider>,
    );
    expect(onRun).not.toHaveBeenCalled();
  });

  it('fires once when a request arrives after mount', () => {
    const onRun = vi.fn();
    render(
      <RunRequestsProvider>
        <Probe id="run.build" onRun={onRun} />
        <Driver id="run.build" />
      </RunRequestsProvider>,
    );

    act(() => {
      screen.getByTestId('driver').click();
    });
    expect(onRun).toHaveBeenCalledTimes(1);

    act(() => {
      screen.getByTestId('driver').click();
    });
    expect(onRun).toHaveBeenCalledTimes(2);
  });

  it('does not fire when a different id is requested', () => {
    const onRun = vi.fn();
    render(
      <RunRequestsProvider>
        <Probe id="run.build" onRun={onRun} />
        <Driver id="run.verify" />
      </RunRequestsProvider>,
    );

    act(() => {
      screen.getByTestId('driver').click();
    });
    expect(onRun).not.toHaveBeenCalled();
  });

  it('drains a request that raced mount, exactly once', () => {
    // The shell's switch-then-request order: `request` is called before the
    // subscriber mounts, so the nonce is already bumped at mount time. The
    // hook must run the pending request once and stay subscribed afterwards.
    const onRun = vi.fn();
    let capturedRequest: ((id: string) => void) | null = null;
    function Requestor() {
      const { request } = useRunRequests();
      capturedRequest = request;
      return null;
    }

    const { rerender } = render(
      <RunRequestsProvider>
        <Requestor />
      </RunRequestsProvider>,
    );

    act(() => {
      capturedRequest?.('run.build');
    });

    rerender(
      <RunRequestsProvider>
        <Requestor />
        <Probe id="run.build" onRun={onRun} />
        <Driver id="run.build" />
      </RunRequestsProvider>,
    );
    expect(onRun).toHaveBeenCalledTimes(1);

    // A request after the drained mount still fires.
    act(() => {
      screen.getByTestId('driver').click();
    });
    expect(onRun).toHaveBeenCalledTimes(2);
  });

  it('does not fire for a mount with no pending request, even when another id is pending', () => {
    const buildOnRun = vi.fn();
    const verifyOnRun = vi.fn();
    let capturedRequest: ((id: string) => void) | null = null;
    function Requestor() {
      const { request } = useRunRequests();
      capturedRequest = request;
      return null;
    }

    const { rerender } = render(
      <RunRequestsProvider>
        <Requestor />
      </RunRequestsProvider>,
    );

    act(() => {
      capturedRequest?.('run.verify');
    });

    // Mount a subscriber for `run.build` while only `run.verify` is pending:
    // the build subscriber must not fire.
    rerender(
      <RunRequestsProvider>
        <Requestor />
        <Probe id="run.build" onRun={buildOnRun} />
      </RunRequestsProvider>,
    );
    expect(buildOnRun).not.toHaveBeenCalled();
    expect(verifyOnRun).not.toHaveBeenCalled();
  });
});
