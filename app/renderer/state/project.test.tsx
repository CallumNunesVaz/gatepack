/**
 * The project state — spec reading across project changes and external file
 * changes. These pin the two defects the e2e agent found:
 *
 *   1. opening a second project mid-session must re-read its spec, so the
 *      design name follows the project instead of going stale;
 *   2. an external edit must reach the editor, except when the user has
 *      unsaved local edits — those are kept and the document is marked stale
 *      rather than silently overwritten.
 */

import { describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ApiProvider } from '../bridge/context';
import { setApi } from '../api';
import { FakeGatepack } from '../bridge/fake';
import { ProjectProvider, useProject } from './project';
import type { ProjectInfo } from '../../shared/api';

function design(name: string): string {
  return `name: ${name}
timing_model: synchronous
clock: {signal: clk, freq_hz: 1000, source: OSC}
reset: {signal: rst_n, active: low, source: SUPERVISOR}
encoding: one_hot
inputs:
  - {name: a, sync: false}
outputs:
  - {name: y}
states: [S0]
initial: S0
transitions:
  - {from: S0, to: S0, when: "1"}
output_logic:
  y: "a"
`;
}

function projectInfo(name: string): ProjectInfo {
  return {
    path: `/tmp/${name}`,
    form: 'directory',
    designPath: `/tmp/${name}/design.yaml`,
    libraryPath: null,
    dirty: false,
    git: null,
  };
}

function Probe() {
  const { model, specStale, setSpecText } = useProject();
  return (
    <div>
      <span data-testid="name">{model?.name ?? ''}</span>
      <span data-testid="stale">{String(specStale)}</span>
      <button data-testid="edit" onClick={() => setSpecText(design('alpha-edited'))}>
        edit
      </button>
    </div>
  );
}

function renderProject(fake: FakeGatepack) {
  setApi(fake);
  return render(
    <ApiProvider>
      <ProjectProvider>
        <Probe />
      </ProjectProvider>
    </ApiProvider>,
  );
}

describe('ProjectProvider — spec follows the project and the disk', () => {
  it('re-reads the spec when the project changes mid-session', async () => {
    const fake = new FakeGatepack({ specText: design('alpha') });
    renderProject(fake);
    await waitFor(() => expect(screen.getByTestId('name')).toHaveTextContent('alpha'));

    fake.specText = design('beta');
    act(() => fake.emitProjectChanged(projectInfo('beta')));

    await waitFor(() => expect(screen.getByTestId('name')).toHaveTextContent('beta'));
  });

  it('re-reads the spec on an external file change with no unsaved edits', async () => {
    const fake = new FakeGatepack({ specText: design('alpha') });
    renderProject(fake);
    await waitFor(() => expect(screen.getByTestId('name')).toHaveTextContent('alpha'));

    fake.specText = design('beta');
    act(() => fake.emitFileChanged(['design.yaml']));

    await waitFor(() => expect(screen.getByTestId('name')).toHaveTextContent('beta'));
    expect(screen.getByTestId('stale')).toHaveTextContent('false');
  });

  it('keeps unsaved local edits and marks the spec stale on a file change', async () => {
    const fake = new FakeGatepack({ specText: design('alpha') });
    renderProject(fake);
    await waitFor(() => expect(screen.getByTestId('name')).toHaveTextContent('alpha'));

    // The user types: a debounced write is now pending (unsaved).
    fireEvent.click(screen.getByTestId('edit'));
    expect(screen.getByTestId('name')).toHaveTextContent('alpha-edited');

    // The file changes on disk while the local edit is still unsaved.
    fake.specText = design('beta');
    act(() => fake.emitFileChanged(['design.yaml']));

    // The local edit is kept, and the document is marked stale — never
    // silently overwritten.
    expect(screen.getByTestId('name')).toHaveTextContent('alpha-edited');
    expect(screen.getByTestId('stale')).toHaveTextContent('true');
  });
});

describe('editSpec — the several-editing-surfaces case', () => {
  function harness() {
    let ctx: ReturnType<typeof useProject> | null = null;
    function Probe() {
      ctx = useProject();
      return null;
    }
    return { get: () => ctx!, Probe };
  }

  const SPEC = [
    'name: probe',
    'timing_model: synchronous',
    'encoding: one_hot',
    'initial: S0',
    '',
  ].join('\n');

  it('setSpecText from one snapshot loses the earlier edit — editSpec does not', async () => {
    const fake = new FakeGatepack({ specText: SPEC });
    setApi(fake);
    const h = harness();
    render(
      <ApiProvider>
        <ProjectProvider>
          <h.Probe />
        </ProjectProvider>
      </ApiProvider>,
    );
    await waitFor(() => expect(h.get().specText.length).toBeGreaterThan(0));

    // The defect, kept as the control: two views computing from the same
    // render's `specText` and writing in one tick. The first edit is lost.
    const snapshot = h.get().specText;
    await act(async () => {
      h.get().setSpecText(snapshot.replace('encoding: one_hot', 'encoding: binary'));
      h.get().setSpecText(snapshot.replace('timing_model: synchronous', 'timing_model: asynchronous'));
    });
    expect(h.get().specText).not.toContain('encoding: binary');
    expect(h.get().specText).toContain('timing_model: asynchronous');
  });

  it('two editSpec calls in one tick both survive', async () => {
    const fake = new FakeGatepack({ specText: SPEC });
    setApi(fake);
    const h = harness();
    render(
      <ApiProvider>
        <ProjectProvider>
          <h.Probe />
        </ProjectProvider>
      </ApiProvider>,
    );
    await waitFor(() => expect(h.get().specText.length).toBeGreaterThan(0));

    await act(async () => {
      h.get().editSpec((t) => t.replace('encoding: one_hot', 'encoding: binary'));
      h.get().editSpec((t) => t.replace('timing_model: synchronous', 'timing_model: asynchronous'));
    });

    expect(h.get().specText).toContain('encoding: binary');
    expect(h.get().specText).toContain('timing_model: asynchronous');
  });

  it('a refusal (null) changes nothing and does not bump the revision', async () => {
    const fake = new FakeGatepack({ specText: SPEC });
    setApi(fake);
    const h = harness();
    render(
      <ApiProvider>
        <ProjectProvider>
          <h.Probe />
        </ProjectProvider>
      </ApiProvider>,
    );
    await waitFor(() => expect(h.get().specText.length).toBeGreaterThan(0));
    const before = h.get().specText;
    const rev = h.get().revision;

    await act(async () => {
      h.get().editSpec(() => null);
      h.get().editSpec((t) => t); // an unchanged string is a no-op too
    });

    // A revision bump flags every other view's result stale. An edit that did
    // not happen must not do that.
    expect(h.get().specText).toBe(before);
    expect(h.get().revision).toBe(rev);
  });

  it('two rapid editSpec calls coalesce into ONE write of the final text', async () => {
    // State surviving is not the same as reaching disk. The write is debounced,
    // so this pins the other half: no intermediate document is ever persisted,
    // and the single write carries both edits.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fake = new FakeGatepack({ specText: SPEC });
    const writes: string[] = [];
    const original = fake.writeSpec.bind(fake);
    fake.writeSpec = (t: string) => {
      writes.push(t);
      return original(t);
    };
    setApi(fake);
    const h = harness();
    render(
      <ApiProvider>
        <ProjectProvider>
          <h.Probe />
        </ProjectProvider>
      </ApiProvider>,
    );
    await waitFor(() => expect(h.get().specText.length).toBeGreaterThan(0));
    writes.length = 0;

    await act(async () => {
      h.get().editSpec((t) => t.replace('encoding: one_hot', 'encoding: binary'));
      h.get().editSpec((t) => t.replace('timing_model: synchronous', 'timing_model: asynchronous'));
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(600);
    });
    vi.useRealTimers();

    expect(writes).toHaveLength(1);
    expect(writes[0]).toContain('encoding: binary');
    expect(writes[0]).toContain('timing_model: asynchronous');
  });
});
