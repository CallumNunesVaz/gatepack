import { useApi } from '../bridge/context';
import { useProject } from '../state/project';
import { useRevisionedTask } from '../hooks/useRevisionedTask';
import type { AnalysisSummary } from '../../shared/api';

export function AnalysisView() {
  const { revision } = useProject();
  const api = useApi();
  const { state, run, isStale } = useRevisionedTask<AnalysisSummary>(revision, (t) => api.analyse(t));

  return (
    <section className="pane" data-testid="analysis-view">
      <header className="pane__header">
        <h2>Analysis</h2>
        <button onClick={run} disabled={state.status === 'running'}>
          {state.status === 'running' ? 'Analysing…' : 'Run analysis'}
        </button>
      </header>
      {isStale ? <div className="stale-note">Stale — the source has changed.</div> : null}
      {state.status === 'success' && state.data ? (
        <div>
          <h3>Metrics</h3>
          <ul className="metric-list">
            {state.data.metrics.map((m) => (
              <li key={m.name} className={m.violated ? 'metric--violated' : ''}>
                <span>{m.name}</span>
                <strong>{m.value}</strong>
                <span>{m.unit}</span>
                {m.limit !== null ? <span> (limit {m.limit})</span> : null}
              </li>
            ))}
          </ul>
          <h3>SCOAP</h3>
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
              {state.data.scoap.map((row) => (
                <tr key={row.net}>
                  <td>{row.net}</td>
                  <td>{row.controllability0}</td>
                  <td>{row.controllability1}</td>
                  <td>{row.observability}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <h3>Stuck-at faults</h3>
          <ul className="fault-list">
            {(['detected', 'undetected', 'redundant', 'untestable'] as const).map((k) => (
              <li key={k}>
                {k}: {state.data!.faults[k]}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {state.status === 'idle' ? <p className="pane__empty">Run analysis to see metrics.</p> : null}
    </section>
  );
}
