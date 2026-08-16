import { useMemo, useState } from 'react';
import { useApi } from '../bridge/context';
import { usePanelTask } from './usePanelTask';
import type { ProvenanceMap } from '../../shared/api';
import './panels.css';

/**
 * `inspect.provenance` — the §15.1 map: which specification construct produced
 * which net. Coverage is measured by the core; this panel reports it and does
 * not recompute it. Each entry links a pointer token to its nets and cells,
 * with the confidence (`exact` from a surviving attribute, `inferred` from a
 * structural match) shown explicitly.
 */
export function ProvenancePanel() {
  const api = useApi();
  const { state, run } = usePanelTask<ProvenanceMap>(() => api.provenance(), true);
  const [query, setQuery] = useState('');

  const entries = useMemo(() => {
    const data = state.data;
    if (!data) return [];
    const q = query.trim().toLowerCase();
    if (!q) return data.entries;
    return data.entries.filter(
      (e) =>
        e.pointer.toLowerCase().includes(q) ||
        e.nets.some((n) => n.toLowerCase().includes(q)) ||
        e.cells.some((c) => c.toLowerCase().includes(q)),
    );
  }, [state.data, query]);

  return (
    <section className="gp-panel" data-testid="provenance-view">
      <header className="gp-panel__header">
        <h2 className="gp-panel__title">Provenance map</h2>
        <div className="gp-panel__actions">
          <button
            onClick={run}
            disabled={state.status === 'loading'}
            data-testid="provenance-refresh"
          >
            {state.status === 'loading' ? 'Loading…' : 'Refresh'}
          </button>
        </div>
      </header>

      {state.status === 'idle' ? (
        <p className="gp-empty">Provenance is not loaded.</p>
      ) : null}

      {state.status === 'loading' ? (
        <p className="gp-loading">Reading the provenance map…</p>
      ) : null}

      {state.status === 'error' ? (
        <div className="gp-error" data-testid="provenance-error">
          <strong>{state.error?.code ?? 'error'}:</strong> {state.error?.message}
        </div>
      ) : null}

      {state.status === 'success' && state.data ? (
        <>
          <div className="gp-stat-row" data-testid="provenance-coverage">
            <span>coverage</span>
            <strong className="gp-stat__value">
              {(state.data.coverage * 100).toFixed(1)}%
            </strong>
            <span>of spec constructs linked</span>
            <span>·</span>
            <span>{state.data.entries.length} linked construct(s)</span>
          </div>

          <div className="gp-search">
            <input
              type="search"
              placeholder="Filter by pointer, net or cell"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              data-testid="provenance-search"
            />
          </div>

          {entries.length === 0 ? (
            <p className="gp-empty">No provenance entries match “{query}”.</p>
          ) : (
            <ul className="gp-entry-list" data-testid="provenance-entries">
              {entries.map((entry) => (
                <li key={entry.pointer} className="gp-entry" data-testid="provenance-entry">
                  <div className="gp-entry__head">
                    <span className="gp-entry__pointer">{entry.pointer}</span>
                    <span
                      className={`gp-badge gp-badge--${entry.confidence}`}
                      data-confidence={entry.confidence}
                    >
                      {entry.confidence}
                    </span>
                  </div>
                  <div className="gp-entry__links">
                    nets:{' '}
                    {entry.nets.length ? (
                      <span className="gp-mono">{entry.nets.join(', ')}</span>
                    ) : (
                      '(none)'
                    )}{' '}
                    · cells:{' '}
                    {entry.cells.length ? (
                      <span className="gp-mono">{entry.cells.join(', ')}</span>
                    ) : (
                      '(none)'
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </>
      ) : null}
    </section>
  );
}
