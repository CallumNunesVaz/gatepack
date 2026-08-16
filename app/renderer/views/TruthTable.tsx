import { useEffect, useRef, useState } from 'react';
import { useApi } from '../bridge/context';
import { useProject } from '../state/project';
import { useRevisionedTask } from '../hooks/useRevisionedTask';
import { useLinkContext } from '../selection/useLinkContext';
import { useHighlights, useSelection } from '../selection/bus';
import { Icon, Tooltip } from '../ui';
import { Spinner, EmptyState } from './kit';
import { computeRowWindow } from './virtualize';
import type { EstimateResult } from '../../shared/api';
import './views.css';

const COVER_DEBOUNCE_MS = 300;

/**
 * Fixed row height for windowed rendering. Must equal `--v-row-h` in views.css
 * (`calc(--gp-space-4 + --gp-space-3)` = 28px) — the spacer offsets are this
 * height times the row index, so a mismatch shows as rows that drift a pixel or
 * two per scroll.
 */
const ROW_HEIGHT_PX = 28;

/**
 * C11 truth table. The divergence column now comes from the *core*
 * (`simulate()`): `expected` is the specification evaluated by C4's own
 * exhaustive-check code, `actual` is the mapped netlist, and `diverges` is the
 * core's verdict. The renderer no longer compares the spec against itself.
 * Clicking a row emits a §15.2 selection; the gates in that row's cone highlight
 * in the schematic and the row itself reflects selections from other views.
 *
 * Rows are windowed: a 2^n table renders only the scroll window plus overscan,
 * with spacer rows reserving the height above and below. In an environment
 * without measurable layout (jsdom tests) the whole table is rendered.
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

  const table = ctx?.simulation ?? null;
  const inputs = table?.inputNames ?? model?.inputs.map((i) => i.name) ?? [];
  const outputs = table?.outputNames ?? model?.outputs.map((o) => o.name) ?? [];
  const multiState = (model?.states.length ?? 0) > 1;
  const rows = table?.rows ?? [];

  const dontCare = table?.dontCareCount ?? 0;
  const unreachable = table?.unreachableCount ?? 0;
  const specified = rows.length - dontCare - unreachable;

  // Windowed rendering: track the scroll container's geometry.
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const [scroll, setScroll] = useState({ top: 0, height: 0 });

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const measure = () => setScroll({ top: el.scrollTop, height: el.clientHeight });
    measure();
    el.addEventListener('scroll', measure);
    let ro: ResizeObserver | null = null;
    if (typeof ResizeObserver !== 'undefined') {
      ro = new ResizeObserver(measure);
      ro.observe(el);
    }
    return () => {
      el.removeEventListener('scroll', measure);
      ro?.disconnect();
    };
  }, [table]);

  const window = computeRowWindow({
    scrollTop: scroll.top,
    viewportHeight: scroll.height,
    rowHeight: ROW_HEIGHT_PX,
    totalRows: rows.length,
  });

  if (!model) {
    return (
      <section className="pane" data-testid="truth-table">
        <EmptyState
          icon="truthTable"
          title="The spec does not parse yet"
          hint="Fix the syntax in the spec editor and the truth table will appear here."
          testId="truth-table-empty"
        />
      </section>
    );
  }

  const spacerCols = 1 + (multiState ? 1 : 0) + inputs.length + outputs.length * 2;

  return (
    <section className="pane tt" data-testid="truth-table">
      <header className="pane__header">
        <h2>Truth table</h2>
        {table ? null : <span className="muted">no simulation table — divergence unavailable</span>}
      </header>

      <div className="tt__coverage" data-testid="coverage">
        <span className="cov">
          <span>specified</span>
          <strong>{specified}</strong>
        </span>
        <span className="cov">
          <span>don't-care</span>
          <strong>{dontCare}</strong>
        </span>
        <span className="cov">
          <span>unreachable</span>
          <strong>{unreachable}</strong>
        </span>
      </div>

      <div className="cover-preview" data-testid="cover-preview">
        <span className="muted">minimised cover</span>
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
          <Spinner label="computing cover" />
        ) : (
          <span className="muted">(none)</span>
        )}
        {cover.isStale ? <span className="stale-note">stale</span> : null}
      </div>

      {table && !table.exhaustive ? (
        <div className="error-note" role="alert">
          <Icon name="warning" decorative />
          <span>input space too large to enumerate — showing {rows.length} rows (not exhaustive).</span>
        </div>
      ) : null}

      <div className="tt__table-wrap" ref={wrapRef} data-testid="tt-scroll">
        <table className="tt__table" role="grid">
          <thead>
            <tr role="row">
              <th scope="col">
                <Tooltip content="Row index — the minterm number, 0-based">
                  <span className="th-info" tabIndex={0} role="img" aria-label="row index: the minterm number">
                    <Icon name="info" size={13} decorative />
                  </span>
                </Tooltip>
                #
              </th>
              {multiState ? (
                <th scope="col">state</th>
              ) : null}
              {inputs.map((name) => (
                <th key={name} scope="col">
                  {name}
                </th>
              ))}
              {outputs.map((name) => (
                <th key={`expected-${name}`} scope="col">
                  <span className="th-group">expected</span> {name}
                  <Tooltip content={`expected ${name} — what the specification says`}>
                    <span
                      className="th-info"
                      tabIndex={0}
                      role="img"
                      aria-label={`what expected ${name} means`}
                    >
                      <Icon name="info" size={13} decorative />
                    </span>
                  </Tooltip>
                </th>
              ))}
              {outputs.map((name) => (
                <th key={`actual-${name}`} scope="col">
                  <span className="th-group">actual</span> {name}
                  <Tooltip content={`actual ${name} — what the mapped netlist produces`}>
                    <span
                      className="th-info"
                      tabIndex={0}
                      role="img"
                      aria-label={`what actual ${name} means`}
                    >
                      <Icon name="info" size={13} decorative />
                    </span>
                  </Tooltip>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {window.topOffset > 0 ? (
              <tr aria-hidden="true">
                <td colSpan={spacerCols} style={{ height: window.topOffset, padding: 0, border: 0 }} />
              </tr>
            ) : null}
            {rows.slice(window.start, window.end).map((row, i) => {
              const index = window.start + i;
              const isHighlighted = highlights.minterms.includes(index);
              const cls = [
                row.diverges ? 'tt__row--divergent' : '',
                isHighlighted ? 'tt__row--highlight' : '',
              ].filter(Boolean).join(' ');
              return (
                <tr
                  key={index}
                  role="row"
                  tabIndex={0}
                  aria-selected={isHighlighted}
                  className={cls || undefined}
                  data-divergent={row.diverges || undefined}
                  data-highlight={isHighlighted || undefined}
                  onClick={() => setSelection({ kind: 'minterm', index })}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      setSelection({ kind: 'minterm', index });
                    }
                  }}
                >
                  <td>
                    {index}
                    {row.diverges ? (
                      <span role="img" aria-label="diverges" className="tt__diverge-flag">
                        <Icon name="error" size={13} decorative />
                      </span>
                    ) : null}
                  </td>
                  {multiState ? <td>{row.state ?? ''}</td> : null}
                  {inputs.map((name) => (
                    <td key={name}>{row.inputs[name] ?? 'x'}</td>
                  ))}
                  {outputs.map((name) => (
                    <td key={`expected-${name}`} data-testid={`expected-${index}-${name}`}>
                      {row.expected[name] ?? 'x'}
                    </td>
                  ))}
                  {outputs.map((name) => {
                    const value = row.actual?.[name];
                    const divergent = row.diverges && value !== undefined && value !== 'x' && value !== row.expected[name];
                    return (
                      <td key={`actual-${name}`} className={divergent ? 'tt__cell-divergent' : ''}>
                        {value === undefined ? '' : value === 'x' ? <span className="tt__cell-x">x</span> : value}
                        {divergent ? (
                          <span role="img" aria-label="diverges" className="tt__diverge-flag">
                            <Icon name="error" size={13} decorative />
                          </span>
                        ) : null}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
            {window.bottomOffset > 0 ? (
              <tr aria-hidden="true">
                <td colSpan={spacerCols} style={{ height: window.bottomOffset, padding: 0, border: 0 }} />
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}
