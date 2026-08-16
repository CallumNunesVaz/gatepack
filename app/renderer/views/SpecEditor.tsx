import { useState } from 'react';
import { useProject } from '../state/project';
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
  const [tab, setTab] = useState<Tab>('yaml');

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
            <MonacoEditor value={specText} onChange={setSpecText} />
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
