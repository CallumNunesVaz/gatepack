import { useMemo, useState } from 'react';
import { useApi } from '../bridge/context';
import { usePanelTask } from './usePanelTask';
import { parseWriteJson } from '../mapped/sim';
import { RawJson } from './RawJson';
import './panels.css';

/**
 * `inspect.mappedNetlist` — the raw mapped view (Yosys `write_json`).
 *
 * The cell keys in this netlist are ABC's *instance* names (`$abc$…$…`), which
 * are renumbered by every synthesis. Confusing them with the stable cone-hash
 * names that `packing.force_groups` records has caused four defects here, so
 * this panel labels them explicitly and keeps the raw JSON next to a
 * structured listing of the same instance names.
 */
export function MappedNetlistPanel() {
  const api = useApi();
  const { state, run } = usePanelTask<unknown>(() => api.mappedNetlist(), true);
  const [query, setQuery] = useState('');

  const parsed = useMemo(() => {
    if (state.status !== 'success' || state.data === null) return null;
    return parseWriteJson(state.data);
  }, [state]);

  const cells = useMemo(() => {
    if (!parsed) return [];
    const q = query.trim().toLowerCase();
    const list = parsed.cells;
    if (!q) return list;
    return list.filter(
      (c) => c.name.toLowerCase().includes(q) || c.type.toLowerCase().includes(q),
    );
  }, [parsed, query]);

  return (
    <section className="gp-panel" data-testid="mapped-netlist-view">
      <header className="gp-panel__header">
        <h2 className="gp-panel__title">Mapped netlist</h2>
        <div className="gp-panel__actions">
          <button
            onClick={run}
            disabled={state.status === 'loading'}
            data-testid="mapped-netlist-refresh"
          >
            {state.status === 'loading' ? 'Loading…' : 'Refresh'}
          </button>
        </div>
      </header>

      <p className="gp-note">
        Cell keys below are <strong>instance names</strong> (ABC’s{' '}
        <span className="gp-mono">$abc$…</span>) — they are renumbered by every
        synthesis. Stable cone-hash names live in the packed view and in{' '}
        <span className="gp-mono">stableCellNames</span>; the two are not the
        same.
      </p>

      {state.status === 'idle' ? <p className="gp-empty">No mapped netlist loaded.</p> : null}

      {state.status === 'loading' ? (
        <p className="gp-loading">Reading the mapped netlist…</p>
      ) : null}

      {state.status === 'error' ? (
        <div className="gp-error" data-testid="mapped-netlist-error">
          <strong>{state.error?.code ?? 'error'}:</strong> {state.error?.message}
        </div>
      ) : null}

      {state.status === 'success' && state.data === null ? (
        <p className="gp-empty">No mapped netlist available.</p>
      ) : null}

      {state.status === 'success' && state.data !== null ? (
        <>
          {parsed && parsed.top !== '' ? (
            <>
              <div className="gp-stat-row">
                <span>top module</span>
                <strong className="gp-stat__value">{parsed.top}</strong>
                <span>·</span>
                <span>{parsed.inputs.length} input(s)</span>
                <span>·</span>
                <span>{parsed.outputs.length} output(s)</span>
                <span>·</span>
                <span>{parsed.cells.length} cell(s)</span>
              </div>

              <div className="gp-search">
                <input
                  type="search"
                  placeholder="Filter cells by instance name or type"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  data-testid="mapped-netlist-search"
                />
              </div>

              <table className="gp-table" data-testid="mapped-netlist-cells">
                <thead>
                  <tr>
                    <th>instance name</th>
                    <th>cell type</th>
                  </tr>
                </thead>
                <tbody>
                  {cells.map((cell) => (
                    <tr key={cell.name} data-instance={cell.name}>
                      <td className="gp-mono">{cell.name}</td>
                      <td className="gp-mono">{cell.type}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          ) : null}

          <details>
            <summary>raw write_json</summary>
            <RawJson data={state.data} query={query} />
          </details>
        </>
      ) : null}
    </section>
  );
}
