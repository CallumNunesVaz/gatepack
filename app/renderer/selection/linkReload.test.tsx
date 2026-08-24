/**
 * The linked-selection spine can be asked to re-read what the last build wrote.
 *
 * It could not, and that made `run.simulate` unimplementable. The truth table's
 * divergence column comes from `simulate()` through this spine, not from a
 * revisioned task, and the spine fetched it once on mount. The first attempt at
 * the command wired it to the truth table's *other* task — the `estimate`-backed
 * cover preview — so "Simulate truth table" ran estimate and reported success.
 *
 * A command that reports success having run something else is the exact failure
 * this project keeps finding, so the fix needs a test that fails without it:
 * assert `simulate()` is actually called a second time.
 */

import { describe, expect, it } from 'vitest';
import { act, render } from '@testing-library/react';
import { ApiProvider } from '../bridge/context';
import { setApi } from '../api';
import { FakeGatepack } from '../bridge/fake';
import { ProjectProvider } from '../state/project';
import { requestLinkReload } from './linkData';
import { useLinkContext } from './useLinkContext';

function Harness() {
  const ctx = useLinkContext();
  return <span data-testid="rows">{ctx?.simulation?.rows.length ?? -1}</span>;
}

/** Counts `simulate()` calls; everything else behaves as the plain fake. */
class CountingFake extends FakeGatepack {
  simulateCalls = 0;

  override async simulate(token?: string) {
    this.simulateCalls += 1;
    return super.simulate(token);
  }
}

describe('the link spine can be re-read', () => {
  it('re-fetches simulate() when a reload is requested', async () => {
    const fake = new CountingFake();
    setApi(fake);

    await act(async () => {
      render(
        <ApiProvider>
          <ProjectProvider>
            <Harness />
          </ProjectProvider>
        </ApiProvider>,
      );
    });
    expect(fake.simulateCalls, 'fetched once on mount').toBe(1);

    // Without the reload signal the effect depends only on `api`, so this is a
    // no-op and the count stays at 1 — which is exactly how the command came to
    // be wired to the wrong task.
    await act(async () => {
      requestLinkReload();
    });
    expect(fake.simulateCalls, 're-fetched on request').toBe(2);

    await act(async () => {
      requestLinkReload();
    });
    expect(fake.simulateCalls, 'each request is its own read').toBe(3);
  });
});
