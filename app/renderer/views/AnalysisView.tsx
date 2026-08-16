import { useApi } from '../bridge/context';
import { useProject } from '../state/project';
import { useRevisionedTask } from '../hooks/useRevisionedTask';
import type { AnalysisSummary, EstimateResult } from '../../shared/api';

const FAULT_CLASSES = [
  { key: 'detected', label: 'Detected', note: 'caught by the vectors' },
  { key: 'undetected', label: 'Undetected', note: 'a gap in the vectors' },
  { key: 'redundant', label: 'Redundant', note: 'no test can exist — a design finding' },
  { key: 'untestable', label: 'Untestable', note: 'not observable at test' },
] as const;

type FaultKey = (typeof FAULT_CLASSES)[number]['key'];

const VERDICT_CLASS: Record<EstimateResult['verdict'], string> = {
  green: 'verdict verdict--green',
  amber: 'verdict verdict--amber',
  red: 'verdict verdict--red',
};

/**
 * C14 — analysis dashboard.
 *
 * Metrics are rendered against the constraints block *red on violation*, using
 * the core's `Metric.violated` — the renderer never recomputes the comparison,
 * because a second opinion that disagrees with the core is a bug, and the
 * core's is the one the report prints. The §6 verdict comes from `estimate()`;
 * the SCOAP delta table, the four-way stuck-at classification and the CPLD
 * blockers come from `analyse()`. The four fault classes are distinct
 * engineering findings and are never collapsed into a percentage.
 */
export function AnalysisView() {
  const { revision } = useProject();
  const api = useApi();
  const analysis = useRevisionedTask<AnalysisSummary>(revision, (t) => api.analyse(t));
  const estimate = useRevisionedTask<EstimateResult>(revision, (t) => api.estimate(t));

  const runAll = () => {
    analysis.run();
    estimate.run();
  };

  const summary = analysis.state.status === 'success' ? analysis.state.data : null;
  const verdict = estimate.state.status === 'success' ? estimate.state.data : null;

  return (
    <section className="pane" data-testid="analysis-view">
      <header className="pane__header">
        <h2>Analysis</h2>
        <button onClick={runAll} disabled={analysis.state.status === 'running'}>
          {analysis.state.status === 'running' ? 'Analysing…' : 'Run analysis'}
        </button>
      </header>
      {analysis.isStale || estimate.isStale ? (
        <div className="stale-note">Stale — the source has changed.</div>
      ) : null}

      {verdict ? (
        <div className="analysis__verdict">
          <span className={VERDICT_CLASS[verdict.verdict]} data-testid="verdict" data-verdict={verdict.verdict}>
            viability: {verdict.verdict}
          </span>
          {verdict.reasons.length ? (
            <ul className="verdict__reasons">
              {verdict.reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          ) : null}
          {verdict.alternative ? (
            <p className="verdict__alternative" data-testid="verdict-alternative">
              {verdict.alternative}
            </p>
          ) : null}
        </div>
      ) : null}

      {summary ? (
        <div>
          <h3>Metrics</h3>
          <ul className="metric-list">
            {summary.metrics.map((m) => (
              <li
                key={m.name}
                className={m.violated ? 'metric--violated' : ''}
                data-testid={`metric-${m.name}`}
                data-violated={m.violated || undefined}
              >
                <span className="metric__name">{m.name}</span>
                <strong className="metric__value">
                  {m.value === null ? '—' : m.value}
                </strong>
                <span className="metric__unit">{m.unit}</span>
                {m.limit !== null ? <span className="metric__limit">(limit {m.limit})</span> : null}
                {m.violated ? <span className="metric__flag">VIOLATED</span> : null}
              </li>
            ))}
          </ul>

          <h3>SCOAP delta</h3>
          {summary.scoap.length ? (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Net</th>
                  <th>CC0</th>
                  <th>CC1</th>
                  <th>CO</th>
                </tr>
              </thead>
              <tbody>
                {summary.scoap.map((row) => (
                  <tr key={row.net}>
                    <td>{row.net}</td>
                    <td>{row.controllability0}</td>
                    <td>{row.controllability1}</td>
                    <td>{row.observability}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="pane__empty">No SCOAP data — synthesis has not produced a netlist.</p>
          )}

          <h3>Stuck-at classification</h3>
          <ul className="fault-list">
            {FAULT_CLASSES.map(({ key, label, note }) => (
              <li
                key={key}
                className={`fault fault--${key}`}
                data-testid={`fault-${key}`}
                data-fault={key}
              >
                <span className="fault__label">{label}</span>
                <strong className="fault__count">{summary.faults[key as FaultKey]}</strong>
                <span className="fault__note">{note}</span>
              </li>
            ))}
          </ul>

          {summary.cpldBlockers.length ? (
            <>
              <h3>CPLD blockers</h3>
              <ul className="diag-list" data-testid="cpld-blockers">
                {summary.cpldBlockers.map((d) => (
                  <li key={d.code} className={`diag--${d.severity}`}>
                    {d.code}: {d.message}
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </div>
      ) : null}

      {analysis.state.status === 'idle' ? (
        <p className="pane__empty">Run analysis to see metrics.</p>
      ) : null}
    </section>
  );
}
