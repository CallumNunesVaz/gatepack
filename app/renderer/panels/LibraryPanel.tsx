import { useCallback, useEffect, useMemo, useState } from 'react';
import { useApi } from '../bridge/context';
import { useProject } from '../state/project';
import { usePanelTask } from './usePanelTask';
import type { LibraryCheckResult, LibraryPart } from '../../shared/api';
import './panels.css';

function citationBadge(part: LibraryPart): { cls: string; label: string } {
  if (part.citation === null) return { cls: 'uncited', label: 'uncited' };
  if (part.unverified) return { cls: 'unverified', label: 'unverified' };
  return { cls: 'verified', label: 'verified' };
}

/**
 * `inspect.library` — validate the loaded part library (§C2 `lib check`).
 *
 * Shows the validation result the core computed: how many parts loaded, how
 * many are Liberty-eligible vs dropped and why, and the citation status of
 * every part (verified / unverified / uncited). It checks the library the
 * project actually loaded (`ProjectInfo.libraryPath`); nothing here re-derives
 * the eligibility rules.
 */
export function LibraryPanel() {
  const api = useApi();
  const { project } = useProject();
  const libraryPath = project?.libraryPath ?? null;

  const start = useCallback(
    () => api.checkLibrary(libraryPath as string),
    [api, libraryPath],
  );
  const { state, run } = usePanelTask<LibraryCheckResult>(start, false);

  useEffect(() => {
    if (libraryPath !== null) run();
  }, [libraryPath, run]);

  const [query, setQuery] = useState('');

  const parts = useMemo(() => {
    const data = state.data;
    if (!data) return [];
    const q = query.trim().toLowerCase();
    if (!q) return data.parts;
    return data.parts.filter(
      (p) =>
        p.cell.toLowerCase().includes(q) ||
        p.partNumber.toLowerCase().includes(q) ||
        (p.function ?? '').toLowerCase().includes(q),
    );
  }, [state.data, query]);

  return (
    <section className="gp-panel" data-testid="library-view">
      <header className="gp-panel__header">
        <h2 className="gp-panel__title">Part library</h2>
        <div className="gp-panel__actions">
          {libraryPath !== null ? (
            <button onClick={run} disabled={state.status === 'loading'}>
              {state.status === 'loading' ? 'Checking…' : 'Re-check'}
            </button>
          ) : null}
        </div>
      </header>

      {libraryPath === null ? (
        <p className="gp-empty" data-testid="library-empty">
          No part library is loaded for the current project.
        </p>
      ) : null}

      {libraryPath !== null && state.status === 'idle' ? (
        <p className="gp-loading">Validating the part library…</p>
      ) : null}

      {libraryPath !== null && state.status === 'loading' ? (
        <p className="gp-loading">Validating {libraryPath}…</p>
      ) : null}

      {libraryPath !== null && state.status === 'error' ? (
        <div className="gp-error" data-testid="library-error">
          <strong>{state.error?.code ?? 'error'}:</strong> {state.error?.message}
        </div>
      ) : null}

      {state.status === 'success' && state.data ? (
        <>
          <div className="gp-stat-row" data-testid="library-summary">
            <span>{state.data.cellCount} part(s)</span>
            <span>·</span>
            <span>
              <strong className="gp-stat__value">{state.data.includedCount}</strong> included
            </span>
            <span>
              <strong className="gp-stat__value">{state.data.excludedCount}</strong> excluded
            </span>
            <span>·</span>
            <span>
              refs file{' '}
              {state.data.refsPresent ? 'present' : 'MISSING'}
            </span>
          </div>

          {state.data.missingCitations.length > 0 ? (
            <div className="gp-error" data-testid="library-missing-citations">
              <strong>{state.data.missingCitations.length} cell(s) missing a citation:</strong>{' '}
              {state.data.missingCitations.join(', ')}
            </div>
          ) : null}

          <div className="gp-search">
            <input
              type="search"
              placeholder="Filter by cell or part number"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              data-testid="library-search"
            />
          </div>

          <table className="gp-table" data-testid="library-parts">
            <thead>
              <tr>
                <th>cell</th>
                <th>part</th>
                <th>function</th>
                <th>gates/pkg</th>
                <th>package</th>
                <th>sources</th>
                <th>citation</th>
                <th>status</th>
              </tr>
            </thead>
            <tbody>
              {parts.map((part) => {
                const badge = citationBadge(part);
                return (
                  <tr
                    key={part.cell}
                    className={part.excluded ? 'row--excluded' : ''}
                    data-testid={`library-part-${part.cell}`}
                    data-excluded={part.excluded || undefined}
                  >
                    <td className="gp-mono">{part.cell}</td>
                    <td className="gp-mono">{part.partNumber || '—'}</td>
                    <td className="gp-mono">{part.function ?? '—'}</td>
                    <td>{part.gatesPerPackage}</td>
                    <td>{part.package}</td>
                    <td>{part.secondSourceCount}</td>
                    <td>
                      <span className={`gp-badge gp-badge--${badge.cls}`} data-citation={badge.cls}>
                        {badge.label}
                      </span>
                    </td>
                    <td>
                      {part.excluded ? (
                        <span title={part.exclusionReason ?? ''}>
                          excluded: {part.exclusionReason}
                        </span>
                      ) : (
                        'included'
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </>
      ) : null}
    </section>
  );
}
