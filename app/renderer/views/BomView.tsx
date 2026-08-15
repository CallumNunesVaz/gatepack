import { useApi } from '../bridge/context';
import { useProject } from '../state/project';
import { useRevisionedTask } from '../hooks/useRevisionedTask';
import type { BuildResult } from '../../shared/api';

export function BomView() {
  const { revision } = useProject();
  const api = useApi();
  const { state, run, isStale } = useRevisionedTask<BuildResult>(revision, (t) => api.build(t));

  return (
    <section className="pane" data-testid="bom-view">
      <header className="pane__header">
        <h2>Packing &amp; BOM</h2>
        <button onClick={run} disabled={state.status === 'running'}>
          {state.status === 'running' ? 'Building…' : 'Run build'}
        </button>
      </header>
      {isStale ? <div className="stale-note">Stale — the source has changed.</div> : null}
      {state.status === 'success' && state.data ? (
        <div>
          <div className="stat-row">
            <span>Packages</span>
            <strong>{state.data.packageCount}</strong>
            <span>Spares</span>
            <strong>{state.data.spareCount}</strong>
            <span>pack_cost</span>
            <strong>{state.data.packCost}</strong>
          </div>
          <table className="data-table">
            <thead>
              <tr>
                <th>Part</th>
                <th>Qty</th>
                <th>Package</th>
                <th>Refdes</th>
                <th>Mfrs</th>
              </tr>
            </thead>
            <tbody>
              {state.data.bom.map((line) => (
                <tr key={line.partNumber} className={line.singleSourced ? 'row--single-sourced' : ''}>
                  <td>
                    {line.partNumber}
                    {line.singleSourced ? <span className="single-source-marker">SINGLE-SOURCE</span> : null}
                  </td>
                  <td>{line.quantity}</td>
                  <td>{line.package}</td>
                  <td>{line.refdes.join(', ')}</td>
                  <td>{line.manufacturers.join('; ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {state.status === 'idle' ? <p className="pane__empty">Run a build to see the BOM.</p> : null}
    </section>
  );
}
