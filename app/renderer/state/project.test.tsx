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

import { describe, expect, it } from 'vitest';
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
