import { useApi } from '../bridge/context';
import { useProject } from '../state/project';
import { useRevisionedTask } from '../hooks/useRevisionedTask';
import { StatusBadge } from '../components/StatusBadge';
import type { Check, Counterexample, VerifyResult } from '../../shared/api';

function CounterexampleTrace({ cex }: { cex: Counterexample }) {
  const signalNames = new Set<string>();
  for (const step of cex.steps) for (const name of Object.keys(step)) signalNames.add(name);
  const names = [...signalNames].sort();
  return (
    <details className="counterexample">
      <summary>Counterexample ({cex.steps.length} cycles)</summary>
      <table className="cex-table">
        <thead>
          <tr>
            <th>cycle</th>
            {names.map((n) => (
              <th key={n}>{n}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {cex.steps.map((step, i) => (
            <tr key={i}>
              <td>{i}</td>
              {names.map((n) => (
                <td key={n}>{step[n] ?? 'x'}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {cex.pointers.length > 0 ? (
        <div className="cex-pointers">implicated: {cex.pointers.join(', ')}</div>
      ) : null}
    </details>
  );
}

function CheckRow({ check }: { check: Check }) {
  return (
    <li className="check-row" data-check={check.name}>
      <StatusBadge status={check.status} bound={check.bound} skippedReason={check.skippedReason} />
      <span className="check-name">{check.name}</span>
      <span className="check-kind">{check.kind}</span>
      <span className="check-duration">{check.durationMs} ms</span>
      {check.counterexample ? <CounterexampleTrace cex={check.counterexample} /> : null}
    </li>
  );
}

export function VerificationPanel() {
  const { revision } = useProject();
  const api = useApi();
  const { state, run, isStale } = useRevisionedTask<VerifyResult>(revision, (t) => api.verify(t));

  return (
    <section className="pane" data-testid="verification-panel">
      <header className="pane__header">
        <h2>Verification</h2>
        <button onClick={run} disabled={state.status === 'running'}>
          {state.status === 'running' ? 'Running…' : 'Run verification'}
        </button>
      </header>

      {isStale ? (
        <div className="stale-note" data-testid="verification-stale">
          The source has changed since this result was produced — it no longer applies.
        </div>
      ) : null}

      {state.status === 'error' ? (
        <div className="error-note" data-testid="verification-error">
          {state.error?.message}
        </div>
      ) : null}

      {state.status === 'success' && state.data ? (
        <div className="verify-summary" data-testid="verification-result">
          <div className={`verify-overall verify-overall--${state.data.allPassed ? 'pass' : 'not-pass'}`}>
            {state.data.allPassed ? 'All checks passed' : 'Not all checks passed'}
          </div>
          <ul className="check-list">
            {state.data.checks.map((check) => (
              <CheckRow key={check.name} check={check} />
            ))}
          </ul>
        </div>
      ) : null}

      {state.status === 'idle' ? (
        <p className="pane__empty">No verification has been run for the current source.</p>
      ) : null}
    </section>
  );
}
