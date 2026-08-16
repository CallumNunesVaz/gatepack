/**
 * The right-hand inspector — shows what is currently selected.
 *
 * It reads the §15.2 selection bus directly and resolves it against the link
 * context (`useLinkContext`), then renders the resolved highlights with a
 * provenance-confidence badge. It emits nothing and owns nothing: it is a
 * view over state the other views set.
 */

import { useLinkContext } from '../selection/useLinkContext';
import { useHighlights, useSelection } from '../selection/bus';
import { SelectionBadge } from '../selection/SelectionBadge';
import type { Selection } from '../selection/types';
import { EmptyState, IconButton, Panel } from '../ui';

function describeSelection(selection: Selection): string {
  switch (selection.kind) {
    case 'state':
      return `State "${selection.id}"`;
    case 'minterm':
      return `Truth-table row ${selection.index}`;
    case 'input':
      return `Input "${selection.name}"`;
    case 'cell':
      return `Cell "${selection.name}"`;
    case 'net':
      return `Net "${selection.name}"`;
    case 'package':
      return `Package "${selection.refdes}"`;
    case 'transition':
      return `Transition ${selection.from} → ${selection.to}`;
    case 'property':
      return `Property "${selection.name}"`;
    case 'cexStep':
      return `Counterexample step ${selection.cycle} of "${selection.property}"`;
  }
}

function Field({ label, values }: { label: string; values: string[] }) {
  return (
    <div className="inspector__field">
      <dt className="inspector__field-label">{label}</dt>
      <dd className="inspector__field-value">
        {values.length > 0 ? (
          <span className="link-list">{values.join(', ')}</span>
        ) : (
          <span className="inspector__field-none">—</span>
        )}
      </dd>
    </div>
  );
}

export function Inspector() {
  const { selection, setSelection } = useSelection();
  const ctx = useLinkContext();
  const highlights = useHighlights(ctx);

  if (!selection) {
    return (
      <Panel title="Inspector" className="inspector-panel">
        <EmptyState
          icon="link"
          title="Nothing selected"
          description="Select a gate, net, state, transition or package in any view to see what it links to."
        />
      </Panel>
    );
  }

  return (
    <Panel
      title="Inspector"
      className="inspector-panel"
      actions={
        <IconButton
          name="close"
          label="Clear selection"
          tooltip="Clear selection"
          onClick={() => setSelection(null)}
        />
      }
    >
      <div className="inspector" data-testid="inspector-selection">
        <div className="inspector__heading">
          <span className="inspector__kind">{describeSelection(selection)}</span>
          <SelectionBadge confidence={highlights.confidence} />
        </div>
        <dl className="inspector__fields">
          <Field label="Nets" values={highlights.nets} />
          <Field label="Cells" values={highlights.cells} />
          <Field label="Packages" values={highlights.packages} />
          <Field label="States" values={highlights.states} />
          <Field label="Minterms" values={highlights.minterms.map(String)} />
          <Field label="Transitions" values={highlights.transitions.map(String)} />
        </dl>
        {highlights.pointers.length > 0 ? (
          <div className="inspector__pointers">
            <span className="inspector__pointers-label">Provenance</span>
            <ul className="link-list inspector__pointers-list">
              {highlights.pointers.map((pointer) => (
                <li key={pointer}>{pointer}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </Panel>
  );
}
