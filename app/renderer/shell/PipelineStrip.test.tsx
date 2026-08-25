/**
 * The pipeline strip — the fork drawn above the content, and the states it
 * reports.
 *
 * Every assertion here is built to fail if the wiring is wrong, because a
 * check that cannot fail is worth nothing:
 *
 *   - Verify must be `ready` (not `done`) on a fresh mount with `mapped.json`
 *     present, so wiring Verify to disk state fails this suite;
 *   - a `blocked` stage renders as a non-interactive node (a `<div>`, not a
 *     `<button>`) and names its blocker;
 *   - the strip flips `ready -> done` when a build finishes, through the reload
 *     signal, so deleting the notify at a call site fails this suite;
 *   - every state is carried by `data-state` + text (never by animation), so
 *     the strip reads the same with `prefers-reduced-motion: reduce`.
 */

import { describe, expect, it, vi } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import { ApiProvider } from '../bridge/context';
import { ProjectProvider } from '../state/project';
import { CommandBusProvider, createCommandBus } from './commands';
import { PipelineStrip } from './PipelineStrip';
import { requestBuildStateReload } from '../state/buildState';
import { setApi } from '../api';
import { FakeGatepack } from '../bridge/fake';

function renderStrip(fake: FakeGatepack) {
  setApi(fake);
  const bus = createCommandBus();
  const utils = render(
    <ApiProvider>
      <ProjectProvider>
        <CommandBusProvider bus={bus}>
          <PipelineStrip />
        </CommandBusProvider>
      </ProjectProvider>
    </ApiProvider>,
  );
  return { ...utils, bus };
}

/** The stage node, queried fresh so a `div` -> `button` re-render is not missed. */
function getStage(id: string): HTMLElement {
  return screen.getByTestId(`pipeline-stage-${id}`);
}

async function expectState(id: string, state: string): Promise<HTMLElement> {
  await waitFor(() => expect(getStage(id)).toHaveAttribute('data-state', state));
  return getStage(id);
}

describe('PipelineStrip — honest evidence', () => {
  it('does not paint Verify as done from disk state', async () => {
    const fake = new FakeGatepack();
    fake.buildArtefacts = ['mapped.json'];

    renderStrip(fake);

    // Build is evidenced by mapped.json on disk -> done.
    await expectState('build', 'done');
    // Verify left no trace -> still ready, despite the build on disk.
    await expectState('verify', 'ready');
  });

  it('a blocked stage is not clickable and names its blocker', async () => {
    // A spec that is not a mapping yields one error diagnostic, so the spec —
    // and both branches that wait on it — are blocked.
    const fake = new FakeGatepack({ specText: 'just a scalar, not a mapping' });

    renderStrip(fake);

    const build = await expectState('build', 'blocked');
    // Blocked means it is not a button: a control that looks live and does
    // nothing is worse than no control.
    expect(build.tagName).toBe('DIV');
    expect(build.textContent).toContain('error');
    expect(build.textContent).toContain('in the spec');

    const verify = await expectState('verify', 'blocked');
    expect(verify.tagName).toBe('DIV');
  });

  it('flips Build from ready to done when a build finishes (reload signal)', async () => {
    const fake = new FakeGatepack();

    renderStrip(fake);

    await expectState('build', 'ready');

    // The build lands on disk; the call site must fire the reload signal.
    fake.buildArtefacts = ['mapped.json'];
    act(() => requestBuildStateReload());

    await expectState('build', 'done');
  });

  it('reports every state by attribute and text, never by animation alone', async () => {
    // With reduced motion the connector animation is off (see styles.css), so
    // the states must survive without it. jsdom does not apply CSS, so the
    // guarantee is: the state is carried on the node, not on the moving dot.
    const reduceMedia = window.matchMedia;
    window.matchMedia = ((query: string) => ({
      matches: query.includes('prefers-reduced-motion'),
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    })) as typeof window.matchMedia;

    try {
      const fake = new FakeGatepack();
      renderStrip(fake);

      const build = await expectState('build', 'ready');
      expect(build.textContent).toContain('Build');

      await expectState('spec', 'done');
      await expectState('verify', 'ready');
    } finally {
      window.matchMedia = reduceMedia;
    }
  });
});

describe('PipelineStrip — running stages through the command bus', () => {
  it('clicking the ready Build stage dispatches run.build', async () => {
    const fake = new FakeGatepack();
    const { bus } = renderStrip(fake);
    const runBuild = vi.fn();
    bus.register('run.build', runBuild);

    await expectState('build', 'ready');

    act(() => {
      (getStage('build') as HTMLButtonElement).click();
    });

    expect(runBuild).toHaveBeenCalledTimes(1);
  });

  it('clicking the ready Verify stage dispatches run.verify', async () => {
    const fake = new FakeGatepack();
    const { bus } = renderStrip(fake);
    const runVerify = vi.fn();
    bus.register('run.verify', runVerify);

    await expectState('verify', 'ready');

    act(() => {
      (getStage('verify') as HTMLButtonElement).click();
    });

    expect(runVerify).toHaveBeenCalledTimes(1);
  });
});
