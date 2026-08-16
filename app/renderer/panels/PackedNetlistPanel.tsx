import { useMemo, useState } from 'react';
import { useApi } from '../bridge/context';
import { usePanelTask } from './usePanelTask';
import { RawJson } from './RawJson';
import type { PackedView } from '../../shared/api';
import './panels.css';

/**
 * `inspect.packedNetlist` — the §C12 packed layer, as raw data.
 *
 * Every package carries two name spaces that must not be conflated: `cells`
 * (STABLE cone-hash names, what `packing.force_groups` records) and
 * `instanceCells` (the mapped-netlist instance names the rendered SVG is keyed
 * by). Both are shown side by side, labelled, so the renderer never has to
 * guess which space a name is in.
 */
export function PackedNetlistPanel() {
  const api = useApi();
  const { state, run } = usePanelTask<PackedView>(() => api.packedNetlist(), true);
  const [query, setQuery] = useState('');

  const packages = useMemo(() => {
    const data = state.data;
    if (!data) return [];
    const q = query.trim().toLowerCase();
    if (!q) return data.packages;
    return data.packages.filter(
      (p) =>
        p.refdes.toLowerCase().includes(q) ||
        p.partNumber.toLowerCase().includes(q) ||
        p.cells.some((c) => c.toLowerCase().includes(q)) ||
        p.instanceCells.some((c) => c.toLowerCase().includes(q)),
    );
  }, [state.data, query]);

  return (
    <section className="gp-panel" data-testid="packed-netlist-view">
      <header className="gp-panel__header">
        <h2 className="gp-panel__title">Packed netlist</h2>
        <div className="gp-panel__actions">
          <button
            onClick={run}
            disabled={state.status === 'loading'}
            data-testid="packed-netlist-refresh"
          >
            {state.status === 'loading' ? 'Loading…' : 'Refresh'}
          </button>
        </div>
      </header>

      {state.status === 'idle' ? <p className="gp-empty">No packed view loaded.</p> : null}

      {state.status === 'loading' ? (
        <p className="gp-loading">Reading the packed view…</p>
      ) : null}

      {state.status === 'error' ? (
        <div className="gp-error" data-testid="packed-netlist-error">
          <strong>{state.error?.code ?? 'error'}:</strong> {state.error?.message}
        </div>
      ) : null}

      {state.status === 'success' && state.data ? (
        <>
          <div className="gp-stat-row" data-testid="packed-netlist-summary">
            <span>packages</span>
            <strong className="gp-stat__value">{state.data.packages.length}</strong>
          </div>

          <div className="gp-search">
            <input
              type="search"
              placeholder="Filter by refdes, part or cell name"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              data-testid="packed-netlist-search"
            />
          </div>

          {packages.length === 0 ? (
            <p className="gp-empty">No packages match “{query}”.</p>
          ) : (
            <ul className="gp-package-list" data-testid="packed-netlist-packages">
              {packages.map((pkg) => (
                <li key={pkg.refdes} className="gp-package" data-refdes={pkg.refdes}>
                  <div className="gp-package__head">
                    <span className="gp-package__refdes">{pkg.refdes}</span>
                    <span className="gp-package__meta">{pkg.partNumber}</span>
                    <span className="gp-package__meta">
                      {pkg.capacity - pkg.spare}/{pkg.capacity} gates used
                    </span>
                  </div>
                  {pkg.rationale ? (
                    <div className="gp-package__rationale">{pkg.rationale}</div>
                  ) : null}
                  <div className="gp-name-spaces">
                    <div>
                      <div className="gp-name-space__label">stable cell names</div>
                      <div className="gp-name-space__cells">
                        {pkg.cells.length ? pkg.cells.join(', ') : '(none)'}
                      </div>
                    </div>
                    <div>
                      <div className="gp-name-space__label">instance cell names</div>
                      <div className="gp-name-space__cells">
                        {pkg.instanceCells.length ? pkg.instanceCells.join(', ') : '(none)'}
                      </div>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}

          <details>
            <summary>raw packed.json</summary>
            <RawJson data={state.data} query={query} />
          </details>
        </>
      ) : null}
    </section>
  );
}
