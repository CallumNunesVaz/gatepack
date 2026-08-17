import { useEffect } from 'react';
import { useApi } from '../bridge/context';
import { useProject } from '../state/project';
import { useRevisionedTask } from '../hooks/useRevisionedTask';
import { StatusBadge } from '../components/StatusBadge';
import { useSelection } from '../selection/bus';
import { setVerifyResult } from '../selection/linkData';
import { Icon } from '../ui';
import { ActionButton, EmptyState } from './kit';
import type { Check, Counterexample, VerifyResult } from '../../shared/api';
import './views.css';

/** The raw property name behind a `property <name>` check, or null if not one. */
function propertyName(check: Check): string | null {
  if (check.kind !== 'property') return null;
  return check.name.startsWith('property ') ? check.name.slice('property '.length) : check.name;
}

function activateOnEnterOrSpace(handler: () => void) {
  return (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      handler();
    }
  };
}

function CounterexampleTrace({
  cex,
  selectedCycle,
  onSelectStep,
}: {
  cex: Counterexample;
  selectedCycle: number | null;
  onSelectStep: (cycle: number) => void;
}) {
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
            <tr
              key={i}
              tabIndex={0}
              className={selectedCycle === i ? 'cex-step--highlight' : ''}
              data-cycle={i}
              data-highlight={selectedCycle === i || undefined}
              onClick={(e) => {
                e.stopPropagation();
                onSelectStep(i);
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  e.stopPropagation();
                  onSelectStep(i);
                }
              }}
            >
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

function CheckRow({
  check,
  selected,
  selectedCycle,
  onSelectProperty,
  onSelectStep,
}: {
  check: Check;
  selected: boolean;
  selectedCycle: number | null;
  onSelectProperty: (name: string) => void;
  onSelectStep: (cycle: number) => void;
}) {
  const name = propertyName(check);
  const select = () => {
    if (name) onSelectProperty(name);
  };
  return (
    <li
      className={selected ? 'check-row check-row--highlight' : 'check-row'}
      data-check={check.name}
      data-highlight={selected || undefined}
      onClick={select}
      tabIndex={0}
      onKeyDown={activateOnEnterOrSpace(select)}
      aria-selected={selected}
    >
      <div className="check-row__main">
        <StatusBadge
          status={check.status}
          bound={check.bound}
          skippedReason={check.skippedReason}
          detail={check.detail}
        />
        <span className="check-name">{check.name}</span>
        <span className="check-kind">{check.kind}</span>
        <span className="check-duration">{check.durationMs} ms</span>
      </div>
      {check.detail ? (
        <pre className="check-detail" data-testid="check-detail">
          {check.detail}
        </pre>
      ) : null}
      {check.counterexample && name ? (
        <CounterexampleTrace
          cex={check.counterexample}
          selectedCycle={selectedCycle}
          onSelectStep={onSelectStep}
        />
      ) : null}
    </li>
  );
}

export function VerificationPanel() {
  const { revision } = useProject();
  const api = useApi();
  const { state, run, isStale } = useRevisionedTask<VerifyResult>(revision, (t) => api.verify(t));
  const { selection, setSelection } = useSelection();

  // Publish the verified result into the selection spine so a property (or
  // counterexample-step) selection resolves against the same result this panel
  // just showed. `verify()` is expensive and revisioned here; the link context
  // only reads it back.
  useEffect(() => {
    if (state.status === 'success' && state.data) setVerifyResult(state.data);
  }, [state]);

  const selectedProperty = selection?.kind === 'property' ? selection.name : null;
  const selectedCex = selection?.kind === 'cexStep' ? selection : null;

  return (
    <section className="pane" data-testid="verification-panel">
      <header className="pane__header">
        <h2>Verification</h2>
        <ActionButton
          icon="verify"
          label="Run verification"
          busyLabel="Running"
          busy={state.status === 'running'}
          onClick={run}
          primary
        />
      </header>

      {isStale ? (
        <div className="stale-note" data-testid="verification-stale">
          The source has changed since this result was produced — it no longer applies.
        </div>
      ) : null}

      {state.status === 'error' ? (
        <div className="error-note" data-testid="verification-error" role="alert">
          <Icon name="error" decorative />
          <span>{state.error?.message}</span>
        </div>
      ) : null}

      {state.status === 'success' && state.data ? (
        <div className="verify-summary" data-testid="verification-result">
          <div className={`verify-overall verify-overall--${state.data.allPassed ? 'pass' : 'not-pass'}`}>
            <Icon name={state.data.allPassed ? 'check' : 'warning'} size={16} decorative />
            {state.data.allPassed ? 'All checks passed' : 'Not all checks passed'}
          </div>
          <ul className="check-list">
            {state.data.checks.map((check) => {
              const name = propertyName(check);
              return (
                <CheckRow
                  key={check.name}
                  check={check}
                  selected={name !== null && name === selectedProperty}
                  selectedCycle={selectedCex && name === selectedCex.property ? selectedCex.cycle : null}
                  onSelectProperty={(n) => setSelection({ kind: 'property', name: n })}
                  onSelectStep={(cycle) =>
                    setSelection({ kind: 'cexStep', property: name ?? '', cycle })
                  }
                />
              );
            })}
          </ul>
        </div>
      ) : null}

      {state.status === 'idle' ? (
        <EmptyState
          icon="verify"
          title="No verification has been run for the current source."
          hint="Run verification to see formal equivalence, property and exhaustive-simulation results."
          testId="verification-empty"
        />
      ) : null}
    </section>
  );
}
