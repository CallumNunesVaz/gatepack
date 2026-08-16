import { useState } from 'react';
import { useApi } from '../bridge/context';
import { usePanelTask } from './usePanelTask';
import type { Diagnostic, ExamplesList } from '../../shared/api';
import './panels.css';

/**
 * `project.examples` — browse the bundled examples (§18.1) and open one into a
 * new project. Discovery and ordering come from the core (`examples list`); the
 * showcase is marked. Opening goes through `openExample`, which opens a scratch
 * copy as the active project — the bundled copy is never modified in place.
 */
export function ExamplesPanel() {
  const api = useApi();
  const { state, run } = usePanelTask<ExamplesList>(() => api.listExamples(), true);
  const [opening, setOpening] = useState<string | null>(null);
  const [openError, setOpenError] = useState<Diagnostic | null>(null);
  const [openedName, setOpenedName] = useState<string | null>(null);

  const open = async (name: string) => {
    setOpening(name);
    setOpenError(null);
    setOpenedName(null);
    const env = await api.openExample(name);
    setOpening(null);
    if (env.ok) setOpenedName(name);
    else setOpenError(env.error);
  };

  return (
    <section className="gp-panel" data-testid="examples-view">
      <header className="gp-panel__header">
        <h2 className="gp-panel__title">Bundled examples</h2>
        <div className="gp-panel__actions">
          <button onClick={run} disabled={state.status === 'loading'}>
            {state.status === 'loading' ? 'Loading…' : 'Refresh'}
          </button>
        </div>
      </header>

      {state.status === 'idle' ? <p className="gp-empty">Examples not loaded.</p> : null}

      {state.status === 'loading' ? (
        <p className="gp-loading">Listing bundled examples…</p>
      ) : null}

      {state.status === 'error' ? (
        <div className="gp-error" data-testid="examples-error">
          <strong>{state.error?.code ?? 'error'}:</strong> {state.error?.message}
        </div>
      ) : null}

      {openError ? (
        <div className="gp-error" data-testid="examples-open-error">
          <strong>{openError.code}:</strong> {openError.message}
        </div>
      ) : null}

      {openedName ? (
        <div className="gp-overall gp-overall--ok" data-testid="examples-opened">
          Opened {openedName} — it is now the active project.
        </div>
      ) : null}

      {state.status === 'success' && state.data ? (
        state.data.examples.length === 0 ? (
          <p className="gp-empty">No bundled examples found in this installation.</p>
        ) : (
          <ul className="gp-example-list" data-testid="examples-list">
            {state.data.examples.map((example) => (
              <li
                key={example.name}
                className="gp-example"
                data-testid={`example-${example.name}`}
                data-showcase={example.isShowcase || undefined}
              >
                <span className="gp-example__name">{example.name}</span>
                {example.isShowcase ? (
                  <span className="gp-badge gp-badge--showcase">showcase</span>
                ) : null}
                <span className="gp-example__summary">{example.summary}</span>
                <button
                  onClick={() => void open(example.name)}
                  disabled={opening === example.name}
                  data-testid={`example-open-${example.name}`}
                >
                  {opening === example.name ? 'Opening…' : 'Open'}
                </button>
              </li>
            ))}
          </ul>
        )
      ) : null}
    </section>
  );
}
