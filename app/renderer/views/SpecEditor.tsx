import { useEffect, useRef, useState } from 'react';
import { useProject } from '../state/project';
import { useSelection } from '../selection/bus';
import { useLinkContext } from '../selection/useLinkContext';
import { resolveSpecAnchor } from '../selection/specAnchor';
import { Icon } from '../ui';
import { MonacoEditor } from './spec/MonacoEditor';
import { StructuredForm } from './spec/StructuredForm';
import { FsmGraph } from './spec/FsmGraph';
import './views.css';

type Tab = 'yaml' | 'form' | 'graph';

const TABS: Array<{ id: Tab; label: string; icon: 'spec' | 'settings' | 'schematic' }> = [
  { id: 'yaml', label: 'YAML', icon: 'spec' },
  { id: 'form', label: 'Form', icon: 'settings' },
  { id: 'graph', label: 'FSM graph', icon: 'schematic' },
];

/**
 * C10 spec editor: three synchronised representations of the same document.
 * Text is authoritative — the form and the graph both mutate the text, and the
 * text is what is saved. The dirty indicator reads the project's own
 * `dirty` flag; the editor never computes a second opinion about whether the
 * document is saved.
 */
export function SpecEditor() {
  const { specText, setSpecText, diagnostics, project } = useProject();
  const { selection } = useSelection();
  const ctx = useLinkContext();
  const [tab, setTab] = useState<Tab>('yaml');

  // Reflect the shared §15.2 selection spine: when the selection names a spec
  // construct, reveal its line in the YAML editor without stealing focus. The
  // reveal is driven by the *selection* only — a ref keeps the latest spec
  // text/link context, so typing in the editor (which changes `specText` and
  // re-parses the model) never re-triggers a scroll while the user is typing.
  const ctxRef = useRef(ctx);
  ctxRef.current = ctx;
  const specTextRef = useRef(specText);
  specTextRef.current = specText;
  const tabRef = useRef(tab);
  tabRef.current = tab;
  const tokenRef = useRef(0);
  const [reveal, setReveal] = useState<{ line: number; token: number } | null>(null);

  useEffect(() => {
    if (!selection) {
      setReveal(null);
      return;
    }
    const link = ctxRef.current;
    const anchor = link
      ? resolveSpecAnchor(selection, link.provenance, specTextRef.current)
      : null;
    if (anchor) {
      // A reveal is only ever shown as a Monaco line, so the YAML tab can
      // always satisfy it; the graph tab can also satisfy a state/transition
      // reveal (it already selects the node/edge). The form tab never can. So
      // the tab moves only when the current tab cannot show what was revealed —
      // a `null` anchor must not move anything, and selecting a node inside the
      // graph must not yank the user away from it.
      const shownByCurrentTab =
        tabRef.current === 'yaml' ||
        (tabRef.current === 'graph' &&
          (selection.kind === 'state' || selection.kind === 'transition'));
      if (!shownByCurrentTab) setTab('yaml');
      setReveal({ line: anchor.line, token: ++tokenRef.current });
    } else {
      setReveal(null);
    }
  }, [selection]);

  return (
    <section className="pane spec-editor" data-testid="spec-editor">
      <div className="spec-editor__tabs" role="group" aria-label="Spec editor view">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={tab === t.id ? 'nav-btn nav-btn--active' : 'nav-btn'}
            onClick={() => setTab(t.id)}
          >
            <Icon name={t.icon} size={15} decorative />
            {t.label}
          </button>
        ))}
        <span className="spec-editor__save-state" data-testid="spec-dirty" aria-live="polite">
          {project?.dirty ? (
            <span className="spec-editor__dirty">
              <Icon name="warning" size={13} decorative />
              unsaved changes
            </span>
          ) : (
            <span className="spec-editor__clean">
              <Icon name="check" size={13} decorative />
              saved
            </span>
          )}
        </span>
      </div>

      {diagnostics.length > 0 ? (
        <ul className="diag-list" data-testid="spec-diagnostics">
          {diagnostics.map((d, i) => (
            <li key={i} className={`diag--${d.severity}`}>
              <Icon name={d.severity === 'error' ? 'error' : d.severity === 'warning' ? 'warning' : 'info'} size={13} decorative />
              {d.line ? `line ${d.line}: ` : ''}
              {d.message}
            </li>
          ))}
        </ul>
      ) : null}

      <div className="spec-editor__body">
        {tab === 'yaml' ? (
          <div className="spec-editor__monaco">
            <MonacoEditor value={specText} onChange={setSpecText} reveal={reveal} />
          </div>
        ) : tab === 'form' ? (
          <StructuredForm />
        ) : (
          <FsmGraph />
        )}
      </div>
    </section>
  );
}
