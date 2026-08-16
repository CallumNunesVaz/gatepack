import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useApi } from '../bridge/context';
import { useProject } from '../state/project';
import { renderInWorker } from '../worker/schematicClient';
import {
  computePackageLayouts,
  readCellPositions,
  readNetMarkerPoints,
  unobservableNets,
  type Point,
} from '../worker/schematicOverlay';
import { useLinkContext } from '../selection/useLinkContext';
import { useHighlights } from '../selection/bus';
import type { AnalysisSummary, PackedView } from '../../shared/api';

/**
 * C12 schematic view. Renders the mapped netlist (Yosys `write_json`) with
 * netlistsvg + elkjs in a web worker — IEEE gate symbols, orthogonal routing —
 * never React Flow. This view renders; it never edits.
 *
 * Layers are independently toggleable and drawn *over* the one netlistsvg
 * layout rather than re-laying it out:
 *
 * - mapped (logical) — the netlistsvg render, from `mappedNetlist()`.
 * - packed — package-boundary containers from `packedNetlist()`, hit-tested by
 *   the instance names netlistsvg keys its `id="cell_…"` groups with.
 * - overlay — test points and SCOAP-unobservable nets from `analyse()`.
 */
export function Schematic() {
  const { model } = useProject();
  const api = useApi();
  const ctx = useLinkContext();
  const highlights = useHighlights(ctx);

  const [svg, setSvg] = useState<string | null>(null);
  const [netlist, setNetlist] = useState<unknown>(null);
  const [error, setError] = useState<string | null>(null);
  const [packed, setPacked] = useState<PackedView | null>(null);
  const [packedError, setPackedError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisSummary | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  const [svgSize, setSvgSize] = useState<{ width: number; height: number } | null>(null);
  const [positions, setPositions] = useState<Map<string, Point> | null>(null);
  const [netPoints, setNetPoints] = useState<Map<string, Point> | null>(null);

  const canvasRef = useRef<HTMLDivElement | null>(null);

  const [showMapped, setShowMapped] = useState(true);
  const [showPacked, setShowPacked] = useState(false);
  const [showOverlay, setShowOverlay] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    api.mappedNetlist().then((env) => {
      if (cancelled) return;
      if (!env.ok) {
        // A failed netlist fetch must be reported, never shown as a perpetual
        // "laying out the netlist…" spinner (§15: report the state you have).
        setError(env.error.message);
        return;
      }
      setNetlist(env.data);
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
    setPackedError(null);
    api.packedNetlist().then((env) => {
      if (cancelled) return;
      if (env.ok) setPacked(env.data);
      else setPackedError(env.error.message);
    });
    return () => {
      cancelled = true;
    };
  }, [api]);

  useEffect(() => {
    let cancelled = false;
    setAnalysisError(null);
    api.analyse().then((env) => {
      if (cancelled) return;
      if (env.ok) setAnalysis(env.data);
      else setAnalysisError(env.error.message);
    });
    return () => {
      cancelled = true;
    };
  }, [api]);

  // Read the netlistsvg layout once it is in the DOM: the `<svg>` size and the
  // per-cell `translate()` positions, so the overlays can be drawn over it
  // without re-running layout. Uses attributes only — never `getBBox` — so it
  // works in jsdom as well as the real renderer.
  useLayoutEffect(() => {
    const container = canvasRef.current;
    if (!container || !svg) return;
    const svgEl = container.querySelector('svg');
    if (!svgEl) return;
    const width = Number(svgEl.getAttribute('width') ?? 0);
    const height = Number(svgEl.getAttribute('height') ?? 0);
    if (width > 0 && height > 0) {
      setSvgSize({ width, height });
    }
    setPositions(readCellPositions(svgEl));
    if (netlist) setNetPoints(readNetMarkerPoints(svgEl, netlist));
  }, [svg, netlist]);

  const unobservable = useMemo(
    () => (analysis ? unobservableNets(analysis) : []),
    [analysis],
  );
  const testPoints = useMemo(
    () => (model ? model.testPoints.map((t) => t.net) : []),
    [model],
  );

  const packageLayouts = useMemo(
    () => (packed && positions ? computePackageLayouts(packed.packages, positions) : null),
    [packed, positions],
  );

  const overlayActive = showPacked || showOverlay;

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

      {highlights.nets.length || highlights.cells.length ? (
        <div className="schematic__overlay" data-testid="schematic-highlight">
          <strong>selection:</strong>{' '}
          <span className="link-list">
            nets {highlights.nets.join(', ') || '(none)'} · cells {highlights.cells.join(', ') || '(none)'}
          </span>
        </div>
      ) : null}

      <div
        className="schematic__canvas"
        data-testid="schematic-svg"
        style={{ position: 'relative' }}
      >
        {svg ? (
          <div
            ref={canvasRef}
            style={showMapped ? undefined : { display: 'none' }}
            dangerouslySetInnerHTML={{ __html: svg }}
          />
        ) : showMapped ? (
          <span className="muted">
            {error ? `schematic unavailable — ${error}` : 'laying out the netlist…'}
          </span>
        ) : null}

        {overlayActive && svgSize ? (
          <svg
            className="schematic__overlay-layer"
            data-testid="schematic-overlay"
            width={svgSize.width}
            height={svgSize.height}
            viewBox={`0 0 ${svgSize.width} ${svgSize.height}`}
            style={{ position: 'absolute', top: 0, left: 0, pointerEvents: 'none' }}
          >
            {showPacked && packageLayouts
              ? packageLayouts.map((pkg) => {
                  const used = pkg.capacity - pkg.spare;
                  return (
                    <g
                      key={pkg.refdes}
                      data-testid="packed-package"
                      data-refdes={pkg.refdes}
                      transform={`translate(${pkg.x},${pkg.y})`}
                    >
                      <rect className="packed-boundary" width={pkg.width} height={pkg.height} rx={3} />
                      <text className="packed-label" x={5} y={12}>
                        {pkg.refdes} · {pkg.partNumber}
                      </text>
                      {Array.from({ length: pkg.capacity }, (_, i) => (
                        <rect
                          key={i}
                          data-testid={i < used ? 'packed-slot' : 'packed-spare-slot'}
                          data-slot={i < used ? 'used' : 'spare'}
                          x={5 + i * 11}
                          y={18}
                          width={7}
                          height={7}
                        />
                      ))}
                    </g>
                  );
                })
              : null}

            {showOverlay
              ? unobservable.map((net, i) => {
                  const pt = netPoints?.get(net);
                  return (
                    <g
                      key={`u-${net}`}
                      data-testid="unobservable-net"
                      data-net={net}
                      transform={`translate(${pt ? pt.x : 0},${pt ? pt.y : 40 + i * 18})`}
                    >
                      <circle r={5} className="unobservable-dot" />
                      <text className="unobservable-label" x={9} y={4}>
                        ∞ {net}
                      </text>
                    </g>
                  );
                })
              : null}

            {showOverlay
              ? testPoints.map((net, i) => {
                  const pt = netPoints?.get(net);
                  const y = pt ? pt.y : 40 + (unobservable.length + i) * 18;
                  return (
                    <g
                      key={`t-${net}`}
                      data-testid="test-point"
                      data-net={net}
                      transform={`translate(${pt ? pt.x : 0},${y})`}
                    >
                      <circle r={5} className="testpoint-dot" />
                      <text className="testpoint-label" x={9} y={4}>
                        TP {net}
                      </text>
                    </g>
                  );
                })
              : null}
          </svg>
        ) : null}
      </div>

      {showPacked && packedError ? (
        <div className="stale-note" data-testid="schematic-packed-error">
          packed netlist unavailable — {packedError}
        </div>
      ) : null}

      {showOverlay && analysisError ? (
        <div className="error-note" data-testid="schematic-analysis-error">
          analysis unavailable — {analysisError}
        </div>
      ) : null}
    </section>
  );
}
