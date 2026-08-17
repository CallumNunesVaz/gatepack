import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useApi } from '../bridge/context';
import { useProject } from '../state/project';
import { renderSchematicAsync } from '../worker/schematicClient';
import {
  computePackageLayouts,
  readCellPositions,
  readNetMarkerPoints,
  unobservableNets,
  type Point,
} from '../worker/schematicOverlay';
import { useLinkContext } from '../selection/useLinkContext';
import { useHighlights } from '../selection/bus';
import { Icon, Tooltip } from '../ui';
import { IconButton, Spinner } from './kit';
import { selectionSvgTargets } from './schematicSelection';
import type { AnalysisSummary, PackedView } from '../../shared/api';
import './views.css';

const ZOOM_MIN = 0.25;
const ZOOM_MAX = 4;
const ZOOM_STEP = 1.25;

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

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
 *
 * The canvas is a self-scrolling surface (never the page body) with zoom and
 * fit-to-window; the §15.2 selection is drawn with the selection tokens, not a
 * view-local colour.
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
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const [showMapped, setShowMapped] = useState(true);
  const [showPacked, setShowPacked] = useState(false);
  const [showOverlay, setShowOverlay] = useState(false);

  const [zoom, setZoom] = useState(1);

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
      renderSchematicAsync(env.data)
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

  // §15.2 cross-highlight: mark the rendered cells/nets the current selection
  // implicates, using the selection tokens (`--gp-select-*`).
  useEffect(() => {
    const container = canvasRef.current;
    if (!container) return;
    container.querySelectorAll('.gp-sel').forEach((el) => el.classList.remove('gp-sel'));
    const targets = selectionSvgTargets(netlist, highlights);
    for (const id of targets.cellIds) {
      container.querySelectorAll(`[id="${id}"]`).forEach((el) => el.classList.add('gp-sel'));
    }
    for (const cls of targets.netClasses) {
      container.querySelectorAll(`[class~="${cls}"]`).forEach((el) => el.classList.add('gp-sel'));
    }
  }, [svg, netlist, highlights]);

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

  const zoomBy = (factor: number) => setZoom((z) => clamp(z * factor, ZOOM_MIN, ZOOM_MAX));
  const fitToWindow = () => {
    const el = scrollRef.current;
    if (!el || !svgSize) return;
    if (el.clientWidth <= 0 || el.clientHeight <= 0) return;
    const scale = Math.min(el.clientWidth / svgSize.width, el.clientHeight / svgSize.height);
    if (scale > 0) setZoom(clamp(scale, ZOOM_MIN, ZOOM_MAX));
  };

  return (
    <section className="pane schematic" data-testid="schematic-view">
      <header className="pane__header">
        <h2>Schematic</h2>
        <div className="schematic__toolbar">
          <IconButton
            icon="zoomOut"
            label="Zoom out"
            onClick={() => zoomBy(1 / ZOOM_STEP)}
            disabled={zoom <= ZOOM_MIN}
            tooltip="Zoom out"
          />
          <span className="zoom-readout" aria-live="polite" data-testid="schematic-zoom">
            {Math.round(zoom * 100)}%
          </span>
          <IconButton
            icon="zoomIn"
            label="Zoom in"
            onClick={() => zoomBy(ZOOM_STEP)}
            disabled={zoom >= ZOOM_MAX}
            tooltip="Zoom in"
          />
          <Tooltip content="Fit the whole schematic to the window">
            <button type="button" className="view-btn" onClick={fitToWindow} aria-label="Fit to window">
              <Icon name="fit" decorative />
              Fit
            </button>
          </Tooltip>
          <IconButton
            icon="refresh"
            label="Reset zoom"
            onClick={() => setZoom(1)}
            tooltip="Reset zoom to 100%"
          />
        </div>
      </header>

      <div className="schematic__layers" role="group" aria-label="Schematic layers">
        <label className="layer-toggle">
          <input type="checkbox" checked={showMapped} onChange={(e) => setShowMapped(e.target.checked)} />
          mapped netlist
        </label>
        <label className="layer-toggle">
          <input type="checkbox" checked={showPacked} onChange={(e) => setShowPacked(e.target.checked)} />
          packed netlist
        </label>
        <label className="layer-toggle">
          <input type="checkbox" checked={showOverlay} onChange={(e) => setShowOverlay(e.target.checked)} />
          test points / unobservable nets
        </label>
      </div>

      <div className="schematic__legend" aria-hidden="true">
        <span className="legend-item">
          <span className="legend-swatch legend-swatch--mapped" /> mapped
        </span>
        <span className="legend-item">
          <span className="legend-swatch legend-swatch--packed" /> packed
        </span>
        <span className="legend-item">
          <span className="legend-swatch legend-swatch--overlay" /> test point / unobservable
        </span>
        <span className="legend-item">
          <span className="legend-swatch legend-swatch--selection" /> selection
        </span>
      </div>

      {error ? (
        <div className="error-note" role="alert" data-testid="schematic-error">
          <Icon name="error" decorative />
          <span>schematic unavailable — {error}</span>
        </div>
      ) : null}

      {highlights.nets.length || highlights.cells.length ? (
        <div className="info-note" data-testid="schematic-highlight">
          <Icon name="link" decorative />
          <span>
            selection: nets {highlights.nets.join(', ') || '(none)'} · cells {highlights.cells.join(', ') || '(none)'}
          </span>
        </div>
      ) : null}

      <div
        className="schematic__canvas schematic__canvas--checker"
        data-testid="schematic-svg"
        ref={scrollRef}
      >
        {svg ? (
          <div
            className="schematic__zoom-host"
            style={{ transform: `scale(${zoom})` }}
          >
            <div
              ref={canvasRef}
              style={showMapped ? undefined : { display: 'none' }}
              dangerouslySetInnerHTML={{ __html: svg }}
            />
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
        ) : showMapped && !error ? (
          <Spinner label="laying out the netlist" />
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
