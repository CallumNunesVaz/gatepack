import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ApiProvider } from '../bridge/context';
import { ProjectProvider, useProject } from '../state/project';
import { SelectionProvider, useSelection } from '../selection/bus';
import { CommandBusProvider, createCommandBus } from './commands';
import { setApi } from '../api';
import { FakeGatepack } from '../bridge/fake';
import { Inspector } from './Inspector';
import type { Selection } from '../selection/types';

const FSM_SPEC = `name: fsm
# This comment explains the clock choice and must survive an edit.
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
  - {from: A, to: A, when: "!go"}
output_logic:
  out: "state == B"
`;

const PROPERTY_SPEC = `name: fsm
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
properties:
  - {name: p1, kind: invariant, expr: "go"}
output_logic:
  out: "state == B"
`;

// Two transitions with the SAME guard text but different from/to pairs: the
// anchored line must come from the from/to pair, not a search for the guard.
const TWIN_GUARD_SPEC = `name: twoguard
timing_model: synchronous
clock: {signal: clk, freq_hz: 1000, source: OSC}
reset: {signal: rst_n, active: low, source: SUPERVISOR}
encoding: one_hot
inputs:
  - {name: go, sync: false}
outputs:
  - {name: out}
states: [A, B, C]
initial: A
transitions:
  - {from: A, to: B, when: "go"}
  - {from: B, to: C, when: "go"}
  - {from: C, to: A, when: "go"}
output_logic:
  out: "state == C"
`;

function SpecProbe() {
  const { specText } = useProject();
  return <pre data-testid="spec-text">{specText}</pre>;
}

function SelectionProbe() {
  const { selection } = useSelection();
  return <span data-testid="selection">{JSON.stringify(selection)}</span>;
}

function Selector({ selection }: { selection: Selection }) {
  const { setSelection } = useSelection();
  return (
    <button type="button" onClick={() => setSelection(selection)}>
      select
    </button>
  );
}

function renderInspector(fake: FakeGatepack, selection: Selection) {
  setApi(fake);
  return render(
    <ApiProvider>
      <ProjectProvider>
        <SelectionProvider>
          <CommandBusProvider bus={createCommandBus()}>
            <Selector selection={selection} />
            <Inspector />
            <SpecProbe />
            <SelectionProbe />
          </CommandBusProvider>
        </SelectionProvider>
      </ProjectProvider>
    </ApiProvider>,
  );
}

async function selectAndWait(fake: FakeGatepack, selection: Selection) {
  renderInspector(fake, selection);
  fireEvent.click(screen.getByText('select'));
  await waitFor(() => expect(screen.getByTestId('inspector-selection')).toBeTruthy());
}

describe('Inspector — spec anchor (§15.2 -> line)', () => {
  it('shows the correct line for a transition, keyed on its from/to pair', async () => {
    const fake = new FakeGatepack({ specText: TWIN_GUARD_SPEC });
    await selectAndWait(fake, { kind: 'transition', from: 'B', to: 'C' });
    await waitFor(() => expect(screen.getByTestId('inspector-anchor')).toBeTruthy());
    expect(screen.getByTestId('inspector-anchor').textContent).toContain('line 14');
  });

  it('renders "no link" (not line 1) for a selection with no spec origin', async () => {
    const fake = new FakeGatepack({ specText: FSM_SPEC });
    await selectAndWait(fake, { kind: 'package', refdes: 'U1' });
    // Wait until the spec has parsed (the package edit note renders), then the
    // anchor must still be "no link", never line 1.
    await waitFor(() => expect(screen.getByTestId('inspector-not-editable')).toBeTruthy());
    expect(screen.getByTestId('inspector-no-link')).toBeTruthy();
    expect(screen.queryByTestId('inspector-anchor')).toBeNull();
  });
});

describe('Inspector — in-place edits', () => {
  it('renames a state and keeps the selection pointing at the renamed state', async () => {
    const fake = new FakeGatepack({ specText: FSM_SPEC });
    await selectAndWait(fake, { kind: 'state', id: 'A' });
    await waitFor(() => expect(screen.getByTestId('inspector-edit-state')).toBeTruthy());

    fireEvent.change(screen.getByLabelText('state name'), { target: { value: 'A2' } });

    await waitFor(() => expect(screen.getByTestId('selection')).toHaveTextContent('"id":"A2"'));
    expect(screen.getByTestId('spec-text').textContent).toContain('states: [A2, B]');
  });

  it('sets the selected state as initial through setSpecText', async () => {
    const fake = new FakeGatepack({ specText: FSM_SPEC });
    await selectAndWait(fake, { kind: 'state', id: 'B' });
    await waitFor(() => expect(screen.getByTestId('inspector-edit-state')).toBeTruthy());

    fireEvent.click(screen.getByText('Set as initial'));

    await waitFor(() => expect(screen.getByTestId('spec-text').textContent).toContain('initial: B'));
  });

  it('refuses an input rename that would strand its references', async () => {
    // `go` is referenced by `when: "go"` and `when: "!go"`. There is no
    // `renameInput` that fixes up references the way `renameState` does, so the
    // rename alone leaves the guards pointing at an input that no longer
    // exists. Refusing is the correct answer; applying it and letting the
    // design go invalid is not.
    //
    // The delivered test asserted the rename *succeeded*, which the
    // implementation rightly would not do — the code was right and its own test
    // was wrong.
    const fake = new FakeGatepack({ specText: FSM_SPEC });
    await selectAndWait(fake, { kind: 'input', name: 'go' });
    await waitFor(() => expect(screen.getByTestId('inspector-edit-input')).toBeTruthy());
    const before = screen.getByTestId('spec-text').textContent;

    fireEvent.change(screen.getByLabelText('input name'), { target: { value: 'start' } });

    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    // The reason is shown, the document is untouched, and the selection still
    // names the input that actually exists.
    expect(screen.getByTestId('spec-text').textContent).toBe(before);
    expect(screen.getByTestId('spec-text').textContent).not.toContain('{name: start');
    expect(screen.getByTestId('selection')).toHaveTextContent('"name":"go"');
  });

  it('renames an input whose name nothing references', async () => {
    // The other half: with no dangling reference the rename lands and the
    // selection follows it. Without this, the refusal above would also pass on
    // an Inspector that refused *every* rename.
    const spec = FSM_SPEC.replace('  - {name: go, sync: false}', '  - {name: go, sync: false}\n  - {name: spare, sync: false}');
    const fake = new FakeGatepack({ specText: spec });
    await selectAndWait(fake, { kind: 'input', name: 'spare' });
    await waitFor(() => expect(screen.getByTestId('inspector-edit-input')).toBeTruthy());

    fireEvent.change(screen.getByLabelText('input name'), { target: { value: 'aux' } });

    await waitFor(() => expect(screen.getByTestId('selection')).toHaveTextContent('"name":"aux"'));
    expect(screen.getByTestId('spec-text').textContent).toContain('{name: aux');
  });

  it('toggles an input sync flag through setSpecText', async () => {
    const fake = new FakeGatepack({ specText: FSM_SPEC });
    await selectAndWait(fake, { kind: 'input', name: 'go' });
    await waitFor(() => expect(screen.getByTestId('inspector-edit-input')).toBeTruthy());

    fireEvent.click(screen.getByLabelText('input sync'));

    await waitFor(() => expect(screen.getByTestId('spec-text').textContent).toContain('sync: true'));
  });

  it('edits a property expression through setSpecText', async () => {
    const fake = new FakeGatepack({ specText: PROPERTY_SPEC });
    await selectAndWait(fake, { kind: 'property', name: 'p1' });
    await waitFor(() => expect(screen.getByTestId('inspector-edit-property')).toBeTruthy());

    fireEvent.change(screen.getByLabelText('property expression'), { target: { value: '!go' } });

    await waitFor(() => expect(screen.getByTestId('spec-text').textContent).toContain('expr: "!go"'));
  });
});

describe('Inspector — refusal and honesty', () => {
  it('refuses an invalid transition guard with a visible message, leaving the text byte-identical', async () => {
    const fake = new FakeGatepack({ specText: FSM_SPEC });
    await selectAndWait(fake, { kind: 'transition', from: 'A', to: 'B' });
    await waitFor(() => expect(screen.getByTestId('inspector-edit-transition')).toBeTruthy());

    fireEvent.change(screen.getByLabelText('transition guard'), { target: { value: 'go &' } });

    await waitFor(() => expect(screen.getByTestId('inspector-refusal')).toBeTruthy());
    expect(screen.getByTestId('inspector-refusal').textContent).toContain('go &');
    expect(screen.getByTestId('spec-text').textContent).toBe(FSM_SPEC);
  });

  it('refuses an invalid property expression, leaving the text byte-identical', async () => {
    const fake = new FakeGatepack({ specText: PROPERTY_SPEC });
    await selectAndWait(fake, { kind: 'property', name: 'p1' });
    await waitFor(() => expect(screen.getByTestId('inspector-edit-property')).toBeTruthy());

    fireEvent.change(screen.getByLabelText('property expression'), { target: { value: 'a &' } });

    await waitFor(() => expect(screen.getByTestId('inspector-refusal')).toBeTruthy());
    expect(screen.getByTestId('spec-text').textContent).toBe(PROPERTY_SPEC);
  });

  it('offers no fabricated editable field for a cell selection', async () => {
    const fake = new FakeGatepack({ specText: FSM_SPEC });
    fake.setOk('provenance', {
      entries: [
        { pointer: 'design.yaml:12:transitions[0]', nets: ['n1'], cells: ['$and'], confidence: 'exact' },
      ],
      coverage: 0,
    });
    await selectAndWait(fake, { kind: 'cell', name: '$and' });
    await waitFor(() => expect(screen.getByTestId('inspector-not-editable')).toBeTruthy());

    expect(screen.getByTestId('inspector-not-editable').querySelector('input')).toBeNull();
    expect(screen.getByTestId('inspector-not-editable').querySelector('select')).toBeNull();
    // The whole inspector holds no editable control for this selection.
    expect(screen.getByTestId('inspector-selection').querySelector('input')).toBeNull();
    // …but it does show the provenance link and a control to the responsible line.
    expect(screen.getByTestId('inspector-anchor').textContent).toContain('line 12');
    expect(screen.getByTestId('inspector-reveal')).toBeTruthy();
  });
});

describe('Inspector — surgical edits', () => {
  it('edits a guard without touching the comment or unrelated formatting', async () => {
    const fake = new FakeGatepack({ specText: FSM_SPEC });
    await selectAndWait(fake, { kind: 'transition', from: 'A', to: 'A' });
    await waitFor(() => expect(screen.getByTestId('inspector-edit-transition')).toBeTruthy());

    fireEvent.change(screen.getByLabelText('transition guard'), { target: { value: 'go & go' } });

    await waitFor(() => expect(screen.getByTestId('spec-text').textContent).toContain('"go & go"'));

    const text = screen.getByTestId('spec-text').textContent ?? '';
    const prefix = FSM_SPEC.slice(0, FSM_SPEC.indexOf('transitions:') + 'transitions:'.length);
    const suffix = FSM_SPEC.slice(FSM_SPEC.indexOf('output_logic:'));
    expect(text.startsWith(prefix)).toBe(true);
    expect(text.endsWith(suffix)).toBe(true);
    expect(text).toContain('# This comment explains the clock choice and must survive an edit.');
  });
});
