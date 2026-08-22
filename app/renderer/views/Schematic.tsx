import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useApi } from '../bridge/context';
import { useProject } from '../state/project';
import { renderSchematicAsync } from '../worker/schematicClient';
import { prepareNetlist } from '../worker/prepareNetlist';
import {
  computePackageLayouts,
  readCellPositions,
  readNetMarkerPoints,
  unobservableNets,
  type Point,
} from '../worker/schematicOverlay';
import { parseWriteJson, type ParsedNetlist } from '../mapped/sim';
import {
  clockNets,
  evaluateNets,
  initialFlopState,
  isSequential,
  settleAsync,
  stepClock,
  type FlopState,
} from '../mapped/netSim';
import {
  applyCellLabels,
  applyFlowDots,
  applyNetValues,
  clearFlowDots,
  clearNetValues,
  highlightNet,
  netClassOf,
  clockNetClasses,
  netNameClasses,
  netValueClasses,
  type CellLabel,
} from './schematicDecorate';
import { useLinkContext } from '../selection/useLinkContext';
import { useHighlights, useSelection } from '../selection/bus';
import { Icon, Tooltip } from '../ui';
import { IconButton, Spinner } from './kit';
import { selectionSvgTargets } from './schematicSelection';
import type { Bit } from '../design/expr';
import type { AnalysisSummary, PackedView } from '../../shared/api';
import './views.css';

const ZOOM_MIN = 0.25;
const ZOOM_MAX = 4;
const ZOOM_STEP = 1.25;

/** Auto-run clock period. Slow enough to read a state change on the sheet. */
const RUN_PERIOD_MS = 700;

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/**
 * C12 schematic view. Renders the mapped netlist (Yosys `write_json`) with
 * netlistsvg + elkjs — IEEE gate symbols, orthogonal routing — never React
 * Flow. This view renders; it never edits.
 *
 * Layers are independently toggleable and drawn *over* the one netlistsvg
 * layout rather than re-laying it out:
 *
 * - mapped (logical) — the netlistsvg render, from `mappedNetlist()`.
 * - packed — package-boundary containers from `packedNetlist()`, hit-tested by
 *   the instance names netlistsvg keys its `id="cell_…"` groups with.
 * - overlay — test points and SCOAP-unobservable nets from `analyse()`.
 * - signals — §24.2/M16 per-vector values: every net carries its 0/1/x, a high
 *   net glows and a low net dims, and the flow animation marches along the
 *   wires that are actually carrying a one.
 *
 * The signal layer is driven by a **probe**: the engineer sets each input pin
 * and steps the clock, and `mapped/netSim.ts` evaluates the netlist the core
 * built. That is arithmetic over an existing artefact, the same standing the
 * truth table's divergence column has — it is not a decision, and it is not
 * schematic capture (§24.3: C12 renders, it never edits).
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
  const { setSelection } = useSelection();

  const [svg, setSvg] = useState<string | null>(null);
  const [constants, setConstants] = useState<Map<string, Bit>>(new Map());
  const [netlist, setNetlist] = useState<unknown>(null);
  const [error, setError] = useState<string | null>(null);
  const [packed, setPacked] = useState<PackedView | null>(null);
  const [packedError, setPackedError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisSummary | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [unresolvedTypes, setUnresolvedTypes] = useState<string[]>([]);

  const [svgSize, setSvgSize] = useState<{ width: number; height: number } | null>(null);
  const [positions, setPositions] = useState<Map<string, Point> | null>(null);
  const [netPoints, setNetPoints] = useState<Map<string, Point> | null>(null);

  const canvasRef = useRef<HTMLDivElement | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const [showMapped, setShowMapped] = useState(true);
  const [showPacked, setShowPacked] = useState(false);
  const [showOverlay, setShowOverlay] = useState(false);
  const [showValues, setShowValues] = useState(true);
  const [showFlow, setShowFlow] = useState(true);

  const [zoom, setZoom] = useState(1);

  /* --- signal probe (§24.2) ------------------------------------------- */
  const [probe, setProbe] = useState<Record<string, Bit>>({});
  const [flops, setFlops] = useState<FlopState>({});
  const [running, setRunning] = useState(false);
  const [hover, setHover] = useState<{ net: string; value: string } | null>(null);

  /* --- artefact loading ------------------------------------------------ */

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

  /**
   * The netlist netlistsvg is actually given: the core's `mapped.json` plus the
   * `port_directions` post-`abc` output does not carry, and the refdes/type
   * display attributes. Without the directions netlistsvg classifies no ports
   * and routes no wires — see `prepareNetlist.ts`.
   *
   * This waits for `packed` so the refdes labels are right the first time; a
   * packed view that never arrives (`packedError`) still renders, without them.
   */
  const prepared = useMemo(() => {
    if (netlist === null) return null;
    if (packed === null && packedError === null) return null;
    return prepareNetlist(netlist, packed);
  }, [netlist, packed, packedError]);

  useEffect(() => {
    if (prepared === null) return;
    let cancelled = false;
    setUnresolvedTypes(prepared.unresolvedTypes);
    renderSchematicAsync(prepared.netlist)
      .then((r) => {
        if (cancelled) return;
        setConstants(r.constants);
        setSvg(r.svg);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [prepared]);

  /* --- evaluation ------------------------------------------------------ */

  const parsed: ParsedNetlist | null = useMemo(
    () => (prepared ? parseWriteJson(prepared.netlist) : null),
    [prepared],
  );

  const clockSignal = model?.clock?.signal ?? null;
  const resetSignal = model?.reset.signal ?? null;
  const resetAsserted: Bit = model?.reset.active === 'high' ? '1' : '0';
  const resetReleased: Bit = resetAsserted === '0' ? '1' : '0';

  /**
   * Probe pins: every input port except the clock, which is stepped rather than
   * driven. Reset starts *released* and the flops start unknown, which is the
   * true state of a board at power-on — the engineer pulses reset to get a
   * defined one, exactly as §9.3 requires of the real design.
   */
  const probePins = useMemo(
    () => (parsed ? parsed.inputs.filter((name) => name !== clockSignal) : []),
    [parsed, clockSignal],
  );

  useEffect(() => {
    if (parsed === null) return;
    const next: Record<string, Bit> = {};
    for (const name of parsed.inputs) {
      next[name] = name === resetSignal ? resetReleased : '0';
    }
    setProbe(next);
    setFlops(initialFlopState(parsed));
    setRunning(false);
  }, [parsed, resetSignal, resetReleased]);

  const evaluated = useMemo(
    () => (parsed ? evaluateNets(parsed, probe, flops) : null),
    [parsed, probe, flops],
  );

  const sequential = useMemo(() => (parsed ? isSequential(parsed) : false), [parsed]);

  const decoration = useMemo(() => {
    if (prepared === null || evaluated === null || parsed === null) return null;
    // The constants netlistsvg materialised are known values on real wires, so
    // they seed the map; anything the evaluator resolved overrides them.
    const values = new Map(constants);
    for (const [cls, bit] of netValueClasses(prepared.netlist, evaluated.values)) {
      values.set(cls, bit);
    }
    const names = netNameClasses(prepared.netlist);
    for (const cls of constants.keys()) {
      if (!names.has(cls)) names.set(cls, constants.get(cls) === '1' ? "1'b1" : "1'b0");
    }
    return {
      values,
      names,
      clockClasses: clockNetClasses(prepared.netlist, clockNets(parsed)),
    };
  }, [prepared, evaluated, parsed, constants]);

  const cellLabels = useMemo(() => {
    const out = new Map<string, CellLabel>();
    if (parsed === null) return out;
    const refdes = new Map<string, string>();
    for (const pkg of packed?.packages ?? []) {
      for (const instance of pkg.instanceCells) refdes.set(instance, pkg.refdes);
    }
    for (const cell of parsed.cells) {
      out.set(cell.name, { refdes: refdes.get(cell.name) ?? null, type: cell.type });
    }
    return out;
  }, [parsed, packed]);

  /* --- DOM passes over the one layout ---------------------------------- */

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

  // Refdes/type labels. netlistsvg's own `s:attribute` substitution cannot do
  // this on a gatepack netlist; `schematicDecorate.ts` records why.
  useLayoutEffect(() => {
    const container = canvasRef.current;
    if (!container || !svg) return;
    applyCellLabels(container, cellLabels);
  }, [svg, cellLabels]);

  // §24.2 value stamps. Re-run on every probe change; this only sets attributes
  // on the existing layout, so stepping the clock never re-lays out the sheet.
  useLayoutEffect(() => {
    const container = canvasRef.current;
    if (!container || !svg) return;
    if (!showValues || decoration === null) {
      clearNetValues(container);
      return;
    }
    applyNetValues(container, decoration);
    if (showFlow) applyFlowDots(container);
    else clearFlowDots(container);
  }, [svg, showValues, showFlow, decoration]);

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

  /* --- probe controls --------------------------------------------------- */

  const step = useCallback(() => {
    setFlops((held) => (parsed ? stepClock(parsed, probe, held) : held));
  }, [parsed, probe]);

  useEffect(() => {
    if (!running || !sequential) return;
    const id = window.setInterval(step, RUN_PERIOD_MS);
    return () => window.clearInterval(id);
  }, [running, sequential, step]);

  /**
   * A §9.3/§9.6 reset pulse: assert, release, then **exactly three** edges.
   *
   * The order matters and is easy to get backwards. Assertion is asynchronous,
   * so it clears every flop with no edge at all — including every one-hot state
   * bit, which is why "during reset" is not the same as "in the initial state"
   * (M0-FINDINGS §6: the encoding is set-via-feedback, so `initial` is *loaded*,
   * not held). The initial state arrives on the third edge after **release**; a
   * fourth advances past it. This mirrors the flush in `verify/simulation.py`.
   */
  const pulseReset = useCallback(() => {
    if (parsed === null || resetSignal === null) return;
    const asserted = { ...probe, [resetSignal]: resetAsserted };
    // Assert with no edge: async clear, exactly as the board sees it.
    let held = settleAsync(parsed, asserted, flops);
    const released = { ...probe, [resetSignal]: resetReleased };
    for (let i = 0; i < 3; i += 1) held = stepClock(parsed, released, held);
    setFlops(held);
    setProbe(released);
    setRunning(false);
  }, [parsed, probe, flops, resetSignal, resetAsserted, resetReleased]);

  const releaseReset = useCallback(() => {
    if (resetSignal === null) return;
    setProbe((p) => ({ ...p, [resetSignal]: resetReleased }));
  }, [resetSignal, resetReleased]);

  const clearState = useCallback(() => {
    if (parsed === null) return;
    setFlops(initialFlopState(parsed));
    setRunning(false);
  }, [parsed]);

  const toggleProbe = (name: string) => {
    setProbe((p) => {
      const current = p[name] ?? 'x';
      const next: Bit = current === '1' ? '0' : '1';
      return { ...p, [name]: next };
    });
  };

  /* --- hover / click on the sheet -------------------------------------- */

  const onCanvasHover = (event: React.MouseEvent<HTMLDivElement>) => {
    const container = canvasRef.current;
    const target = event.target as Element | null;
    const net = target?.getAttribute?.('data-gp-net') ?? null;
    if (net === null) {
      setHover(null);
      if (container) highlightNet(container, null);
      return;
    }
    setHover({ net, value: target?.getAttribute('data-gp-value') ?? 'x' });
    // Light the whole net, not the one segment under the pointer: a net is
    // drawn as many disjoint runs, and highlighting one of them says something
    // about a line rather than about a signal.
    if (container) highlightNet(container, netClassOf(target));
  };

  const onCanvasLeave = () => {
    setHover(null);
    if (canvasRef.current) highlightNet(canvasRef.current, null);
  };

  const onCanvasClick = (event: React.MouseEvent<HTMLDivElement>) => {
    const target = event.target as Element | null;
    const net = target?.getAttribute?.('data-gp-net') ?? null;
    if (net !== null) {
      setSelection({ kind: 'net', name: net });
      return;
    }
    const group = target?.closest?.('g[id^="cell_"]') ?? null;
    const id = group?.getAttribute('id') ?? null;
    if (id !== null) setSelection({ kind: 'cell', name: id.slice('cell_'.length) });
  };

  /* --- derived overlays ------------------------------------------------- */

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

  const highCount = useMemo(() => {
    if (decoration === null) return 0;
    let n = 0;
    for (const v of decoration.values.values()) if (v === '1') n += 1;
    return n;
  }, [decoration]);

  const unknownCount = useMemo(() => {
    if (decoration === null) return 0;
    let n = 0;
    for (const v of decoration.values.values()) if (v === 'x') n += 1;
    return n;
  }, [decoration]);

  const zoomBy = (factor: number) => setZoom((z) => clamp(z * factor, ZOOM_MIN, ZOOM_MAX));
  const fitToWindow = () => {
    const el = scrollRef.current;
    if (!el || !svgSize) return;
    if (el.clientWidth <= 0 || el.clientHeight <= 0) return;
    const scale = Math.min(el.clientWidth / svgSize.width, el.clientHeight / svgSize.height);
    if (scale > 0) setZoom(clamp(scale, ZOOM_MIN, ZOOM_MAX));
  };

  const resetHeld = resetSignal !== null && probe[resetSignal] === resetAsserted;

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
        <label className="layer-toggle">
          <input
            type="checkbox"
            checked={showValues}
            onChange={(e) => setShowValues(e.target.checked)}
            data-testid="schematic-values-toggle"
          />
          signal values
        </label>
        <label className="layer-toggle">
          <input
            type="checkbox"
            checked={showFlow}
            disabled={!showValues}
            onChange={(e) => setShowFlow(e.target.checked)}
            data-testid="schematic-flow-toggle"
          />
          flow animation
        </label>
      </div>

      {showValues && parsed && probePins.length > 0 ? (
        <div className="schematic__probe" data-testid="schematic-probe">
          <span className="probe__title">probe</span>
          {probePins.map((name) => {
            const value = probe[name] ?? 'x';
            return (
              <button
                key={name}
                type="button"
                className="probe__pin"
                data-value={value}
                data-testid={`probe-pin-${name}`}
                aria-pressed={value === '1'}
                onClick={() => toggleProbe(name)}
                title={`drive ${name} — currently ${value}`}
              >
                <span className="probe__pin-name">{name}</span>
                <span className="probe__pin-value">{value}</span>
              </button>
            );
          })}

          {sequential ? (
            <span className="probe__clock">
              <button
                type="button"
                className="view-btn"
                onClick={step}
                data-testid="schematic-step"
                title="advance one rising clock edge"
              >
                <Icon name="chevronRight" decorative />
                Step
              </button>
              <button
                type="button"
                className="view-btn"
                onClick={() => setRunning((r) => !r)}
                data-testid="schematic-run"
                aria-pressed={running}
                title={running ? 'stop the free-running clock' : 'free-run the clock'}
              >
                <Icon name={running ? 'cancel' : 'simulate'} decorative />
                {running ? 'Stop' : 'Run'}
              </button>
              {resetSignal !== null ? (
                <button
                  type="button"
                  className="view-btn"
                  onClick={resetHeld ? releaseReset : pulseReset}
                  data-testid="schematic-reset"
                  title={
                    resetHeld
                      ? `release ${resetSignal}`
                      : `assert ${resetSignal} and clock the §9.3 synchroniser through`
                  }
                >
                  <Icon name="refresh" decorative />
                  {resetHeld ? `Release ${resetSignal}` : 'Reset'}
                </button>
              ) : null}
              <button
                type="button"
                className="view-btn"
                onClick={clearState}
                data-testid="schematic-clear"
                title="return every flop to unknown"
              >
                Clear state
              </button>
            </span>
          ) : null}
        </div>
      ) : null}

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
        {showValues ? (
          <>
            <span className="legend-item">
              <span className="legend-swatch legend-swatch--high" /> logic 1
            </span>
            <span className="legend-item">
              <span className="legend-swatch legend-swatch--low" /> logic 0
            </span>
            <span className="legend-item">
              <span className="legend-swatch legend-swatch--unknown" /> unknown (x)
            </span>
          </>
        ) : null}
      </div>

      {error ? (
        <div className="error-note" role="alert" data-testid="schematic-error">
          <Icon name="error" decorative />
          <span>schematic unavailable — {error}</span>
        </div>
      ) : null}

      {unresolvedTypes.length ? (
        <div className="stale-note" data-testid="schematic-unresolved">
          drawn without pins — no pin table for {unresolvedTypes.join(', ')}
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

      {showValues && decoration ? (
        <div className="schematic__readout" data-testid="schematic-readout">
          {hover ? (
            <span className="readout__net">
              <code>{hover.net}</code> = <strong data-value={hover.value}>{hover.value}</strong>
            </span>
          ) : (
            <span className="readout__net readout__net--idle">hover a wire for its value</span>
          )}
          <span className="readout__counts">
            {highCount} high · {decoration.values.size - highCount - unknownCount} low · {unknownCount} unknown
          </span>
          {evaluated && evaluated.asyncForced.length ? (
            <span className="readout__forced">
              async control holding {evaluated.asyncForced.length} flop
              {evaluated.asyncForced.length === 1 ? '' : 's'}
            </span>
          ) : null}
        </div>
      ) : null}

      <div
        className="schematic__canvas schematic__canvas--checker"
        data-testid="schematic-svg"
        data-flow={showValues && showFlow ? 'on' : 'off'}
        ref={scrollRef}
      >
        {svg ? (
          <div
            className="schematic__zoom-host"
            style={{ transform: `scale(${zoom})` }}
          >
            {/* eslint-disable-next-line jsx-a11y/no-static-element-interactions */}
            <div
              ref={canvasRef}
              style={showMapped ? undefined : { display: 'none' }}
              onMouseOver={onCanvasHover}
              onMouseLeave={onCanvasLeave}
              onClick={onCanvasClick}
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
