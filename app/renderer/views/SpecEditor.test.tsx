import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ApiProvider } from '../bridge/context';
import { ProjectProvider, useProject } from '../state/project';
import { SelectionProvider, useSelection } from '../selection/bus';
import { setApi } from '../api';
import { FakeGatepack } from '../bridge/fake';
import { SpecEditor } from './SpecEditor';
import type { Selection } from '../selection/types';

// The three tab bodies are stubbed so the test asserts SpecEditor's own
// tab-selection logic rather than Monaco (which loads its editor from the
// bundle and does nothing useful in jsdom) or React Flow (which needs a
// ResizeObserver jsdom does not provide).
vi.mock('./spec/MonacoEditor', () => ({
  MonacoEditor: ({
    reveal,
  }: {
    value: string;
    onChange: (text: string) => void;
    reveal?: { line: number; token: number } | null;
  }) => (
    <div
      data-testid="monaco-stub"
      data-reveal-line={reveal?.line ?? ''}
      data-reveal-token={reveal?.token ?? ''}
    />
  ),
}));

vi.mock('./spec/StructuredForm', () => ({
  StructuredForm: () => <div data-testid="form-stub" />,
}));

vi.mock('./spec/FsmGraph', () => ({
  FsmGraph: () => <div data-testid="graph-stub" />,
}));

const SPEC = `name: fsm
timing_model: synchronous
clock: {signal: clk, freq_hz: 1000, source: OSC}
reset: {signal: rst_n, active: low, source: SUPERVISOR}
encoding: one_hot
inputs:
  - {name: go, sync: false}
outputs:
  - {name: out}
states: [A, B]
initial: A
transitions:
  - {from: A, to: B, when: "go"}
output_logic:
  out: "state == B"
`;

function Selector({ selection }: { selection: Selection }) {
  const { setSelection } = useSelection();
  return (
    <button type="button" onClick={() => setSelection(selection)}>
      select
    </button>
  );
}

function SpecProbe() {
  const { specText } = useProject();
  return <pre data-testid="spec-text">{specText}</pre>;
}

function renderEditor(fake: FakeGatepack) {
  setApi(fake);
  return render(
    <ApiProvider>
      <ProjectProvider>
        <SelectionProvider>
          <Selector selection={{ kind: 'transition', from: 'A', to: 'B' }} />
          <SpecEditor />
          <SpecProbe />
        </SelectionProvider>
      </ProjectProvider>
    </ApiProvider>,
  );
}

async function waitForSpec() {
  await waitFor(() => expect(screen.getByTestId('spec-text').textContent).toContain('transitions:'));
}

function tabButton(label: string) {
  return screen.getByRole('button', { name: label });
}

describe('SpecEditor — reveal switches to the tab that can show it', () => {
  it('selecting a transition while the form tab is active ends on the revealed line', async () => {
    const fake = new FakeGatepack({ specText: SPEC });
    renderEditor(fake);
    await waitForSpec();

    // Default tab is YAML; switch to the form tab.
    fireEvent.click(tabButton('Form'));
    await waitFor(() => expect(screen.getByTestId('form-stub')).toBeTruthy());

    // Now a transition is selected from elsewhere; the reveal must move to the
    // tab that can show the line (YAML), without touching focus.
    fireEvent.click(screen.getByText('select'));

    await waitFor(() => expect(screen.getByTestId('monaco-stub')).toBeTruthy());
    expect(screen.getByTestId('monaco-stub').getAttribute('data-reveal-line')).toBe('13');
    expect(screen.queryByTestId('form-stub')).toBeNull();
  });

  it('a null anchor moves nothing', async () => {
    const fake = new FakeGatepack({ specText: SPEC });
    setApi(fake);
    render(
      <ApiProvider>
        <ProjectProvider>
          <SelectionProvider>
            <Selector selection={{ kind: 'package', refdes: 'U1' }} />
            <SpecEditor />
            <SpecProbe />
          </SelectionProvider>
        </ProjectProvider>
      </ApiProvider>,
    );
    await waitForSpec();

    fireEvent.click(tabButton('Form'));
    await waitFor(() => expect(screen.getByTestId('form-stub')).toBeTruthy());

    fireEvent.click(screen.getByText('select'));

    // A package has no spec line, so the reveal is null and the tab must not
    // move: the form tab stays visible and no Monaco reveal is handed down.
    await waitFor(() => expect(screen.getByTestId('spec-text').textContent).toContain('transitions:'));
    expect(screen.getByTestId('form-stub')).toBeTruthy();
    expect(screen.queryByTestId('monaco-stub')).toBeNull();
  });

  it('a state selection on the graph tab stays on the graph (it already selects the node)', async () => {
    const fake = new FakeGatepack({ specText: SPEC });
    setApi(fake);
    render(
      <ApiProvider>
        <ProjectProvider>
          <SelectionProvider>
            <Selector selection={{ kind: 'state', id: 'B' }} />
            <SpecEditor />
            <SpecProbe />
          </SelectionProvider>
        </ProjectProvider>
      </ApiProvider>,
    );
    await waitForSpec();

    fireEvent.click(tabButton('FSM graph'));
    await waitFor(() => expect(screen.getByTestId('graph-stub')).toBeTruthy());

    fireEvent.click(screen.getByText('select'));

    // The graph already reflects a state selection by selecting the node, so the
    // reveal must not yank the user to YAML.
    await waitFor(() => expect(screen.getByTestId('spec-text').textContent).toContain('transitions:'));
    expect(screen.getByTestId('graph-stub')).toBeTruthy();
    expect(screen.queryByTestId('monaco-stub')).toBeNull();
  });
});
