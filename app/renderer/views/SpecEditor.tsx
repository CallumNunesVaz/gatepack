import { useState } from 'react';
import { useProject } from '../state/project';
import { MonacoEditor } from './spec/MonacoEditor';
import { StructuredForm } from './spec/StructuredForm';
import { FsmGraph } from './spec/FsmGraph';

type Tab = 'yaml' | 'form' | 'graph';

/**
 * C10 spec editor: three synchronised representations of the same document.
 * Text is authoritative — the form and the graph both mutate the text, and the
 * text is what is saved.
 */
export function SpecEditor() {
  const { specText, setSpecText, diagnostics } = useProject();
  const [tab, setTab] = useState<Tab>('yaml');

  return (
    <section className="pane spec-editor" data-testid="spec-editor">
      <div className="spec-editor__tabs">
        <button className={tab === 'yaml' ? 'nav-btn nav-btn--active' : 'nav-btn'} onClick={() => setTab('yaml')}>
          YAML
        </button>
        <button className={tab === 'form' ? 'nav-btn nav-btn--active' : 'nav-btn'} onClick={() => setTab('form')}>
          Form
        </button>
        <button className={tab === 'graph' ? 'nav-btn nav-btn--active' : 'nav-btn'} onClick={() => setTab('graph')}>
          FSM graph
        </button>
      </div>

      {diagnostics.length > 0 ? (
        <ul className="diag-list" data-testid="spec-diagnostics">
          {diagnostics.map((d, i) => (
            <li key={i} className={`diag--${d.severity}`}>
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
