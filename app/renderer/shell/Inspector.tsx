/**
 * The right-hand inspector — shows what is currently selected, where in the
 * spec it came from, and (for the constructs that are editable) lets the user
 * edit it in place.
 *
 * It reads the §15.2 selection bus directly and resolves it against the link
 * context (`useLinkContext`), then renders the provenance-confidence badge and
 * the spec anchor (`resolveSpecAnchor`). For `input`/`state`/`transition`/
 * `property` selections it renders the editable spec field and writes through
 * `setSpecText` — the Inspector holds no model of its own between edits. For
 * `cell`/`net`/`package`/`minterm`/`cexStep` it does NOT invent an editable
 * field; it shows the provenance link and a control that takes the user to the
 * responsible line.
 */

import { useEffect, useState } from 'react';
import {
  applyTopLevelEdit,
  setPropertyExpr,
  setTransitionWhen,
  renameInput,
  renameState,
  setField,
  setInputSync,
  type DesignModel,
  type EditOutcome,
  type PropertySpec,
} from '../design/model';
import type { YValue } from '../design/yaml';
import { parse as parseExpr } from '../design/expr';
import { useProject } from '../state/project';
import { useCommandBus } from './commands';
import { useLinkContext } from '../selection/useLinkContext';
import { useHighlights, useSelection } from '../selection/bus';
import { resolveSpecAnchor } from '../selection/specAnchor';
import { SelectionBadge } from '../selection/SelectionBadge';
import type { Selection } from '../selection/types';
import { Button, EmptyState, Icon, IconButton, Panel } from '../ui';

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

/* ------------------------------------------------------------------ */
/* Edit decisions — produce a candidate text, and refuse it (leaving   */
/* the document untouched) when it would not re-parse cleanly.         */
/* ------------------------------------------------------------------ */

interface EditDecision {
  refused: boolean;
  /** Candidate text when not refused; the untouched original when refused. */
  text: string;
  /** The refusal reasons, empty when the edit is accepted. */
  reasons: string[];
}

function messageOf(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

function decide(outcome: EditOutcome, original: string): EditDecision {
  const reasons = outcome.diagnostics
    .filter((d) => d.severity === 'error')
    .map((d) => d.message);
  if (reasons.length > 0) return { refused: true, text: original, reasons };
  return { refused: false, text: outcome.text, reasons: [] };
}

function editTransitionWhen(
  model: DesignModel,
  specText: string,
  from: string,
  to: string,
  when: string,
): EditDecision {
  const index = model.transitions.findIndex((t) => t.from === from && t.to === to);
  if (index === -1) {
    return { refused: true, text: specText, reasons: ['transition no longer resolves'] };
  }
  try {
    // Line-spliced, not re-serialised: rebuilding the whole `transitions` block
    // from the model deletes every comment in it, including comments on the
    // transitions this edit does not touch.
    return decide(setTransitionWhen(specText, index, when), specText);
  } catch (e) {
    return { refused: true, text: specText, reasons: [messageOf(e)] };
  }
}

function editPropertyExpr(
  model: DesignModel,
  specText: string,
  name: string,
  expr: string,
): EditDecision {
  const index = model.properties.findIndex((p) => p.name === name);
  if (index === -1) {
    return { refused: true, text: specText, reasons: ['property no longer resolves'] };
  }
  const trimmed = expr.trim();
  if (trimmed !== '') {
    try {
      parseExpr(trimmed);
    } catch (e) {
      return { refused: true, text: specText, reasons: [`property ${name}: ${messageOf(e)}`] };
    }
  }
  try {
    if (trimmed !== '') {
      // Line-spliced, for the same reason as the transition guard above.
      return decide(setPropertyExpr(specText, index, trimmed), specText);
    }
    // Clearing an expression *removes* the key, which the splice does not do —
    // so this one case still rebuilds the block and still loses the comments in
    // it. Narrower than before, and recorded rather than hidden.
    const properties: PropertySpec[] = model.properties.map((p, i) => {
      if (i !== index) return p;
      const next: PropertySpec = { ...p };
      delete next.expr;
      return next;
    });
    const outcome = applyTopLevelEdit(specText, 'properties', () =>
      properties.map((p) => {
        const m: Record<string, YValue> = { name: p.name, kind: p.kind };
        if (p.expr !== undefined) m.expr = p.expr;
        if (p.from !== undefined) m.from = p.from;
        if (p.to !== undefined) m.to = p.to;
        return m;
      }),
    );
    return decide(outcome, specText);
  } catch (e) {
    return { refused: true, text: specText, reasons: [messageOf(e)] };
  }
}

const NOT_EDITABLE = new Set<Selection['kind']>(['cell', 'net', 'package', 'minterm', 'cexStep']);

function UnresolvedNote() {
  return (
    <div className="inspector__edit" data-testid="inspector-unresolved">
      <span className="inspector__field-none">selection no longer resolves in the current spec</span>
    </div>
  );
}

export function Inspector() {
  const { selection, setSelection } = useSelection();
  const ctx = useLinkContext();
  const highlights = useHighlights(ctx);
  const { specText, model, editSpec } = useProject();
  const bus = useCommandBus();
  const [refusal, setRefusal] = useState<string | null>(null);

  // A refusal is about one specific edit; a new selection (or a changed spec)
  // makes it stale. Cleared here rather than left to accumulate.
  useEffect(() => {
    setRefusal(null);
  }, [selection, specText]);

  if (!selection) {
    return (
      <Panel title="Inspector" className="inspector-panel">
        <EmptyState
          icon="link"
          title="Nothing selected"
          description="Select a gate, net, state, transition or package in any view to see where it lives in the spec — and edit it there."
        />
      </Panel>
    );
  }

  const anchor = ctx ? resolveSpecAnchor(selection, ctx.provenance, specText) : null;

  const apply = (decision: EditDecision, onApplied?: () => void) => {
    if (decision.refused) {
      setRefusal(decision.reasons[0] ?? 'that edit is not valid');
      return;
    }
    setRefusal(null);
    // `decision.text` was computed from the render's `specText`. Land it through
    // `editSpec` so it is applied to the live document — the schematic edits the
    // same file from the next pane along.
    editSpec(() => decision.text);
    onApplied?.();
  };

  const reveal = () => {
    // Switch to the spec editor; SpecEditor reflects the shared selection and
    // reveals the anchored line without stealing focus.
    bus.dispatch('view.spec');
  };

  const stateDeclared =
    selection.kind === 'state' && model ? model.states.includes(selection.id) : false;
  const input =
    selection.kind === 'input' && model
      ? model.inputs.find((i) => i.name === selection.name)
      : undefined;
  const transition =
    selection.kind === 'transition' && model
      ? model.transitions.find((t) => t.from === selection.from && t.to === selection.to)
      : undefined;
  const property =
    selection.kind === 'property' && model
      ? model.properties.find((p) => p.name === selection.name)
      : undefined;

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

        {anchor ? (
          <div className="inspector__anchor" data-testid="inspector-anchor">
            <Icon name="link" size={13} decorative />
            <span className="inspector__anchor-line">
              design.yaml line <strong>{anchor.line}</strong>
            </span>
            <span
              className={`inspector__anchor-route inspector__anchor-route--${anchor.route}`}
              data-route={anchor.route}
            >
              {anchor.route}
            </span>
            <SelectionBadge confidence={anchor.confidence} />
            <Button
              size="sm"
              variant="ghost"
              onClick={reveal}
              data-testid="inspector-reveal"
            >
              Reveal in spec editor
            </Button>
          </div>
        ) : (
          <div className="inspector__anchor inspector__anchor--none" data-testid="inspector-no-link">
            <Icon name="link" size={13} decorative />
            <span className="inspector__field-none">no link</span>
          </div>
        )}

        {model === null ? (
          <div className="inspector__edit" data-testid="inspector-unparseable">
            <span className="inspector__field-none">the spec does not parse, so nothing is editable</span>
          </div>
        ) : selection.kind === 'input' ? (
          input ? (
            <div className="inspector__edit" data-testid="inspector-edit-input">
              <label className="inspector__edit-label" htmlFor="inspector-input-name">
                name
              </label>
              <input
                id="inspector-input-name"
                value={input.name}
                aria-label="input name"
                onChange={(e) =>
                  apply(
                    decide(renameInput(specText, input.name, e.target.value), specText),
                    () => setSelection({ kind: 'input', name: e.target.value }),
                  )
                }
              />
              <label className="inspector__edit-check">
                <input
                  type="checkbox"
                  checked={input.sync}
                  aria-label="input sync"
                  onChange={(e) =>
                    apply(
                      decide(setInputSync(specText, input.name, e.target.checked), specText),
                    )
                  }
                />
                sync
              </label>
            </div>
          ) : (
            <UnresolvedNote />
          )
        ) : selection.kind === 'state' ? (
          stateDeclared ? (
            <div className="inspector__edit" data-testid="inspector-edit-state">
              <label className="inspector__edit-label" htmlFor="inspector-state-name">
                name
              </label>
              <input
                id="inspector-state-name"
                value={selection.id}
                aria-label="state name"
                onChange={(e) =>
                  apply(decide(renameState(specText, selection.id, e.target.value), specText), () =>
                    setSelection({ kind: 'state', id: e.target.value }),
                  )
                }
              />
              {model.initial === selection.id ? (
                <span className="inspector__field-none">initial</span>
              ) : (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => apply(decide(setField(specText, 'initial', selection.id), specText))}
                >
                  Set as initial
                </Button>
              )}
            </div>
          ) : (
            <UnresolvedNote />
          )
        ) : selection.kind === 'transition' ? (
          transition ? (
            <div className="inspector__edit" data-testid="inspector-edit-transition">
              <label className="inspector__edit-label" htmlFor="inspector-transition-when">
                when
              </label>
              <input
                id="inspector-transition-when"
                value={transition.when}
                aria-label="transition guard"
                onChange={(e) =>
                  apply(
                    editTransitionWhen(model, specText, selection.from, selection.to, e.target.value),
                  )
                }
              />
            </div>
          ) : (
            <UnresolvedNote />
          )
        ) : selection.kind === 'property' ? (
          property ? (
            property.kind === 'invariant' || property.expr !== undefined ? (
              <div className="inspector__edit" data-testid="inspector-edit-property">
                <label className="inspector__edit-label" htmlFor="inspector-property-expr">
                  expression
                </label>
                <input
                  id="inspector-property-expr"
                  value={property.expr ?? ''}
                  aria-label="property expression"
                  onChange={(e) =>
                    apply(editPropertyExpr(model, specText, selection.name, e.target.value))
                  }
                />
              </div>
            ) : (
              <div className="inspector__edit" data-testid="inspector-edit-property">
                <span className="inspector__field-none">
                  {property.kind} property
                  {property.from ? `: ${property.from} → ${property.to ?? ''}` : ''} (no expression)
                </span>
              </div>
            )
          ) : (
            <UnresolvedNote />
          )
        ) : NOT_EDITABLE.has(selection.kind) ? (
          <div className="inspector__edit" data-testid="inspector-not-editable">
            <span className="inspector__field-none">
              {anchor
                ? 'Not directly editable — produced by the spec line above.'
                : 'Not directly editable, and no spec line produces it.'}
            </span>
          </div>
        ) : null}

        {refusal ? (
          <div className="error-note" data-testid="inspector-refusal" role="alert">
            <Icon name="error" size={13} decorative />
            {refusal}
          </div>
        ) : null}

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
