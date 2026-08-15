import { useEffect } from 'react';
import { useApi } from '../bridge/context';
import { useProject } from '../state/project';
import { useRevisionedTask } from '../hooks/useRevisionedTask';
import { useLinkContext } from '../selection/useLinkContext';
import { useHighlights, useSelection } from '../selection/bus';
import type { EstimateResult } from '../../shared/api';

const COVER_DEBOUNCE_MS = 300;

/**
 * C11 truth table. The divergence column now comes from the *core*
 * (`simulate()`): `expected` is the specification evaluated by C4's own
 * exhaustive-check code, `actual` is the mapped netlist, and `diverges` is the
 * core's verdict. The renderer no longer compares the spec against itself.
 * Clicking a row emits a §15.2 selection; the gates in that row's cone highlight
 * in the schematic and the row itself reflects selections from other views.
 */
export function TruthTable() {
  const { model, revision } = useProject();
  const api = useApi();
  const ctx = useLinkContext();
  const { setSelection } = useSelection();
  const highlights = useHighlights(ctx);

  const cover = useRevisionedTask<EstimateResult>(revision, (t) => api.estimate(t));

  // Debounced live cover preview (§16.1: < 1 s synthesis preview).
  useEffect(() => {
    const id = setTimeout(() => cover.run(), COVER_DEBOUNCE_MS);
    return () => clearTimeout(id);
  }, [revision]);

  if (!model) {
    return <section className="pane"><p className="pane__empty">The spec does not parse yet.</p></section>;
  }

  const table = ctx?.simulation ?? null;
  const inputs = table?.inputNames ?? model.inputs.map((i) => i.name);
  const outputs = table?.outputNames ?? model.outputs.map((o) => o.name);
  const multiState = model.states.length > 1;
  const rows = table?.rows ?? [];

  const dontCare = table?.dontCareCount ?? 0;
  const unreachable = table?.unreachableCount ?? 0;
  const specified = rows.length - dontCare - unreachable;

  return (
    <section className="pane tt" data-testid="truth-table">
      <header className="pane__header">
        <h2>Truth table</h2>
        {table ? null : <span className="muted">no simulation table — divergence unavailable</span>}
      </header>

      <div className="tt__coverage" data-testid="coverage">
        <span className="cov">specified <strong>{specified}</strong></span>
        <span className="cov">don't-care <strong>{dontCare}</strong></span>
        <span className="cov">unreachable <strong>{unreachable}</strong></span>
      </div>

      <div className="cover-preview" data-testid="cover-preview">
        <span>minimised cover</span>
        {cover.state.status === 'success' && cover.state.data ? (
          <>
            <span className="cover-cells">
              {Object.entries(cover.state.data.cellCounts)
                .sort(([a], [b]) => a.localeCompare(b))
                .map(([cell, n]) => `${cell}×${n}`)
                .join('  ')}
            </span>
            <strong>{cover.state.data.packageCount} packages</strong>
          </>
        ) : cover.state.status === 'running' ? (
          <span className="muted">computing…</span>
        ) : (
          <span className="muted">(none)</span>
        )}
        {cover.isStale ? <span className="stale-note">stale</span> : null}
      </div>

      {table && !table.exhaustive ? (
        <div className="error-note">
          input space too large to enumerate — showing {rows.length} rows (not exhaustive).
        </div>
      ) : null}

      <div className="tt__table-wrap">
        <table className="tt__table">
          <thead>
            <tr>
              <th>#</th>
              {multiState ? <th>state</th> : null}
              {inputs.map((name) => (
                <th key={name}>{name}</th>
              ))}
              {outputs.map((name) => (
                <th key={`expected-${name}`}>expected {name}</th>
              ))}
              {outputs.map((name) => (
                <th key={`actual-${name}`}>actual {name}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => {
              const isHighlighted = highlights.minterms.includes(i);
              const cls = [
                row.diverges ? 'tt__row--divergent' : '',
                isHighlighted ? 'tt__row--highlight' : '',
              ].filter(Boolean).join(' ');
              return (
                <tr
                  key={i}
                  className={cls || undefined}
                  data-divergent={row.diverges || undefined}
                  data-highlight={isHighlighted || undefined}
                  onClick={() => setSelection({ kind: 'minterm', index: i })}
                >
                  <td>{i}</td>
                  {multiState ? <td>{row.state ?? ''}</td> : null}
                  {inputs.map((name) => (
                    <td key={name}>{row.inputs[name] ?? 'x'}</td>
                  ))}
                  {outputs.map((name) => (
                    <td key={`expected-${name}`} data-testid={`expected-${i}-${name}`}>
                      {row.expected[name] ?? 'x'}
                    </td>
                  ))}
                  {outputs.map((name) => {
                    const value = row.actual?.[name];
                    const divergent = row.diverges && value !== undefined && value !== 'x' && value !== row.expected[name];
                    return (
                      <td key={`actual-${name}`} className={divergent ? 'tt__cell-divergent' : ''}>
                        {value === undefined ? '' : value === 'x' ? <span className="tt__cell-x">x</span> : value}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
