import { useEffect, useMemo, useState } from 'react';
import { useApi } from '../bridge/context';
import { useProject } from '../state/project';
import { useRevisionedTask } from '../hooks/useRevisionedTask';
import { parseWriteJson, simulateCombinational, type ParsedNetlist } from '../mapped/sim';
import { allMinterms, computeLiveOutputs, MAX_MINTERM_INPUTS, reachableStates } from '../truth/minterms';
import type { EstimateResult } from '../../shared/api';

const COVER_DEBOUNCE_MS = 300;

export function TruthTable() {
  const { model, revision } = useProject();
  const api = useApi();

  const [netlist, setNetlist] = useState<ParsedNetlist | null>(null);
  const [stateContext, setStateContext] = useState<string | undefined>(undefined);
  const [dontCare, setDontCare] = useState<Set<string>>(new Set());

  const cover = useRevisionedTask<EstimateResult>(revision, (t) => api.estimate(t));

  // Fetch the mapped netlist (build artefact) once on mount.
  useEffect(() => {
    let cancelled = false;
    api.mappedNetlist().then((env) => {
      if (cancelled || !env.ok) return;
      setNetlist(parseWriteJson(env.data));
    });
    return () => {
      cancelled = true;
    };
  }, [api]);

  // Debounced live cover preview (§16.1: < 1 s synthesis preview).
  useEffect(() => {
    const id = setTimeout(() => cover.run(), COVER_DEBOUNCE_MS);
    return () => clearTimeout(id);
  }, [revision]);

  useEffect(() => {
    if (model && stateContext === undefined) setStateContext(model.initial);
  }, [model, stateContext]);

  const inputs = model ? model.inputs.map((i) => i.name) : [];
  const outputs = model ? model.outputs.map((o) => o.name) : [];

  const minterms = useMemo(() => allMinterms(inputs), [inputs]);

  const liveRows = useMemo(
    () =>
      model
        ? minterms.map((env) => computeLiveOutputs(model, env, stateContext))
        : [],
    [model, minterms, stateContext],
  );

  const simRows = useMemo(
    () =>
      netlist
        ? minterms.map((env) => simulateCombinational(netlist, env))
        : [],
    [netlist, minterms],
  );

  const reachable = useMemo(() => (model ? reachableStates(model) : new Set<string>()), [model]);

  if (!model) {
    return <section className="pane"><p className="pane__empty">The spec does not parse yet.</p></section>;
  }

  const total = minterms.length;
  let specified = 0;
  let dcCount = 0;
  for (let row = 0; row < total; row += 1) {
    let rowSpecified = true;
    for (const output of outputs) {
      const key = `${row}:${output}`;
      const live = liveRows[row]?.[output];
      if (dontCare.has(key) || live === 'x') rowSpecified = false;
    }
    if (rowSpecified) specified += 1;
    else dcCount += 1;
  }
  const unreachableStates = model.states.filter((s) => !reachable.has(s)).length;
  const unreachable = unreachableStates * total;

  const tooMany = inputs.length > MAX_MINTERM_INPUTS;
  const shownRows = tooMany ? minterms.slice(0, 1024) : minterms;

  const toggle = (row: number, output: string) => {
    const key = `${row}:${output}`;
    const next = new Set(dontCare);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    setDontCare(next);
  };

  return (
    <section className="pane tt" data-testid="truth-table">
      <header className="pane__header">
        <h2>Truth table</h2>
        {model.states.length > 1 ? (
          <label>
            state{' '}
            <select value={stateContext} onChange={(e) => setStateContext(e.target.value)}>
              {model.states.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </label>
        ) : null}
        {netlist ? null : <span className="muted">no mapped netlist — divergence unavailable</span>}
      </header>

      <div className="tt__coverage" data-testid="coverage">
        <span className="cov">specified <strong>{specified}</strong></span>
        <span className="cov">don't-care <strong>{dcCount}</strong></span>
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

      {tooMany ? (
        <div className="error-note">
          {total} minterms (2^{inputs.length}) — showing the first 1024.
        </div>
      ) : null}

      <div className="tt__table-wrap">
        <table className="tt__table">
          <thead>
            <tr>
              <th>#</th>
              {inputs.map((name) => (
                <th key={name}>{name}</th>
              ))}
              {outputs.map((name) => (
                <th key={`live-${name}`}>live {name}</th>
              ))}
              {outputs.map((name) => (
                <th key={`sim-${name}`}>sim {name}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shownRows.map((env, row) => {
              const live = liveRows[row] ?? {};
              const sim = simRows[row] ?? {};
              let diverged = false;
              for (const output of outputs) {
                const l = live[output];
                const s = sim[output];
                if (dontCare.has(`${row}:${output}`)) continue;
                if (l !== undefined && s !== undefined && l !== 'x' && s !== 'x' && l !== s) {
                  diverged = true;
                }
              }
              return (
                <tr key={row} className={diverged ? 'tt__row--divergent' : ''} data-divergent={diverged || undefined}>
                  <td>{row}</td>
                  {inputs.map((name) => (
                    <td key={name}>{env[name]}</td>
                  ))}
                  {outputs.map((name) => {
                    const key = `${row}:${name}`;
                    const value = dontCare.has(key) ? '-' : live[name] ?? 'x';
                    return (
                      <td key={`live-${name}`}>
                        <button
                          className="tt__output-button"
                          onClick={() => toggle(row, name)}
                          title="click to cycle 0 → 1 → don't-care"
                          data-testid={`live-${row}-${name}`}
                        >
                          {value === '-' ? <span className="tt__cell-dc">-</span> : value === 'x' ? <span className="tt__cell-x">x</span> : value}
                        </button>
                      </td>
                    );
                  })}
                  {outputs.map((name) => {
                    const value = sim[name] ?? 'x';
                    const l = dontCare.has(`${row}:${name}`) ? '-' : live[name];
                    const divergent = l !== undefined && value !== 'x' && l !== 'x' && l !== '-' && l !== value;
                    return (
                      <td key={`sim-${name}`} className={divergent ? 'tt__cell-divergent' : ''}>
                        {value === 'x' ? <span className="tt__cell-x">x</span> : value}
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
