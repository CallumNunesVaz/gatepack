import { useEffect, useMemo, useState } from 'react';
import { useApi } from '../bridge/context';
import { useProject } from '../state/project';
import { renderInWorker } from '../worker/schematicClient';
import type { AnalysisSummary } from '../../shared/api';

/**
 * C12 schematic view. Renders the mapped netlist (Yosys `write_json`) with
 * netlistsvg + elkjs in a web worker — IEEE gate symbols, orthogonal routing —
 * never React Flow. This view renders; it never edits.
 *
 * Layers are independently toggleable. The mapped (logical) layer is fully
 * rendered from `mappedNetlist()`. The packed layer (package-boundary
 * containers) and the test-point/unobservable overlay are surfaced as far as the
 * IPC contract allows (see docs/BUILD-NOTES-M13-15.md for the contract gaps).
 */
export function Schematic() {
  const { model } = useProject();
  const api = useApi();

  const [svg, setSvg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisSummary | null>(null);

  const [showMapped, setShowMapped] = useState(true);
  const [showPacked, setShowPacked] = useState(false);
  const [showOverlay, setShowOverlay] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.mappedNetlist().then((env) => {
      if (cancelled || !env.ok) return;
      renderInWorker(env.data)
        .then((s) => {
          if (!cancelled) setSvg(s);
        })
        .catch((e: unknown) => {
          if (!cancelled) setError(e instanceof Error ? e.message : String(e));
        });
    });
    return () => {
      cancelled = true;
    };
  }, [api]);

  useEffect(() => {
    let cancelled = false;
    api.analyse().then((env) => {
      if (cancelled && env.ok) return;
      if (env.ok) setAnalysis(env.data);
    });
    return () => {
      cancelled = true;
    };
  }, [api]);

  const unobservableNets = useMemo(
    () => (analysis ? analysis.scoap.filter((s) => s.observability === 0).map((s) => s.net) : []),
    [analysis],
  );
  const testPoints = useMemo(() => (model ? model.testPoints.map((t) => t.net) : []), [model]);

  return (
    <section className="pane schematic" data-testid="schematic-view">
      <header className="pane__header">
        <h2>Schematic</h2>
      </header>

      <div className="schematic__layers">
        <label>
          <input type="checkbox" checked={showMapped} onChange={(e) => setShowMapped(e.target.checked)} />
          mapped netlist
        </label>
        <label>
          <input type="checkbox" checked={showPacked} onChange={(e) => setShowPacked(e.target.checked)} />
          packed netlist
        </label>
        <label>
          <input type="checkbox" checked={showOverlay} onChange={(e) => setShowOverlay(e.target.checked)} />
          test points / unobservable nets
        </label>
      </div>

      {error ? <div className="error-note">{error}</div> : null}

      {showMapped ? (
        svg ? (
          <div
            className="schematic__canvas"
            data-testid="schematic-svg"
            dangerouslySetInnerHTML={{ __html: svg }}
          />
        ) : (
          <div className="schematic__canvas schematic__canvas--empty">
            <span className="muted">laying out the netlist…</span>
          </div>
        )
      ) : null}

      {showPacked ? (
        <div className="stale-note">
          The packed netlist (package-boundary containers) is not exposed by the IPC contract
          (`mappedNetlist()` returns the logical netlist only). See BUILD-NOTES.
        </div>
      ) : null}

      {showOverlay ? (
        <div className="schematic__overlay" data-testid="schematic-overlay">
          <div>
            <strong>test points:</strong>{' '}
            {testPoints.length ? testPoints.join(', ') : '(none declared)'}
          </div>
          <div>
            <strong>unobservable nets (SCOAP CO = 0):</strong>{' '}
            {unobservableNets.length ? unobservableNets.join(', ') : '(none reported)'}
          </div>
        </div>
      ) : null}
    </section>
  );
}
