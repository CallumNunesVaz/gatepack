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
  applyHitTargets,
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
import { setInputSync, setTestPoints } from '../design/model';
import {
  applyEditAffordances,
  NO_BUILD_REFUSAL,
  regroupToPackage,
  stableNamesFromPacked,
  toggleTestPoint,
} from './schematicEdit';
import { Icon, Tooltip } from '../ui';
import { IconButton, Spinner } from './kit';
import { selectionSvgTargets } from './schematicSelection';
import type { Bit } from '../design/expr';
import type { AnalysisSummary, PackedView } from '../../shared/api';
import './views.css';

const ZOOM_MIN = 0.25;
const ZOOM_MAX = 4;
const ZOOM_STEP = 1.25;

/**
 * How far the pointer must travel before a press becomes a pan rather than a
 * click.
 *
 * The two gestures share a button, so the threshold is what keeps them apart.
 * Too small and ordinary hand tremor turns a click-to-select into a pan that
 * swallows the selection; too large and a short drag does nothing at all. 4 px
 * is the same order as the 5 px wire hit target measured in
 * `schematic-pointer.spec.ts`, which is the tremor figure this view already
 * designs around.
 */
const PAN_THRESHOLD_PX = 4;

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
  const { model, specText, editSpec, revision } = useProject();
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
  /** In-flight drag-to-pan: where the press started and the scroll it started from. */
  const pan = useRef<{
    x: number;
    y: number;
    scrollLeft: number;
    scrollTop: number;
    moved: boolean;
  } | null>(null);
  /** Set when a pan actually moved, so the `click` it ends with is not a select. */
  const panConsumedClick = useRef(false);
  /** Sheet point to hold under the pointer across the next zoom change. */
  const pendingAnchor = useRef<{
    sheetX: number;
    sheetY: number;
    offsetX: number;
    offsetY: number;
  } | null>(null);

  const [showMapped, setShowMapped] = useState(true);
  const [showPacked, setShowPacked] = useState(false);
  const [showOverlay, setShowOverlay] = useState(false);
  const [showValues, setShowValues] = useState(true);
  const [showFlow, setShowFlow] = useState(true);

  const [zoom, setZoom] = useState(1);
  const [panning, setPanning] = useState(false);
  const [pannable, setPannable] = useState(false);

  /* --- spec editing (§C12 input surface) -------------------------------- */
  const [editMode, setEditMode] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [dragSource, setDragSource] = useState<string | null>(null);

  /* --- signal probe (§24.2) ------------------------------------------- */
  const [probe, setProbe] = useState<Record<string, Bit>>({});
  const [flops, setFlops] = useState<FlopState>({});
  const [running, setRunning] = useState(false);
  const [hover, setHover] = useState<{ net: string; value: string } | null>(null);

  /* --- staleness (§16.1) ------------------------------------------------
   * The sheet is built from `build/mapped.json`, an artefact on disk. Editing
   * the spec — from this view or any other — does not rebuild it, so what is
   * drawn can stop matching the design. Every other expensive view is
   * revisioned for exactly this reason; this one was not, and it now draws
   * live 0/1 values, so a stale sheet showed confidently coloured values for a
   * design that no longer existed.
   *
   * Refetching alone would not fix it: `mappedNetlist()` re-reads the same
   * stale file and only looks fresher. So the honest move is to say the sheet
   * is out of date, stop claiming measured values, and offer the rebuild —
   * which stays the user's call, as it is in every other view.
   */
  const [builtAt, setBuiltAt] = useState<number | null>(null);
  const [netlistVersion, setNetlistVersion] = useState(0);
  const [rebuilding, setRebuilding] = useState(false);
  const stale = builtAt !== null && builtAt !== revision;

  /* --- artefact loading ------------------------------------------------ */

  useEffect(() => {
    let cancelled = false;
    setError(null);
    api.mappedNetlist().then((env) => {
      if (cancelled) return;
      setBuiltAt(revision);
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, netlistVersion]);

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
  }, [api, netlistVersion]);

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
  }, [api, netlistVersion]);

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

  const cellNames = useMemo(
    () => new Set(parsed ? parsed.cells.map((c) => c.name) : []),
    [parsed],
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

  // Apply a pending wheel-zoom anchor. This runs after React has written the
  // zoom host's new width/height, so the scroll assignment is measured against
  // the new scroll area rather than clamped to the old one.
  useLayoutEffect(() => {
    const host = scrollRef.current;
    const anchor = pendingAnchor.current;
    if (!host || !anchor) return;
    pendingAnchor.current = null;
    host.scrollLeft = anchor.sheetX * zoom - anchor.offsetX;
    host.scrollTop = anchor.sheetY * zoom - anchor.offsetY;
  }, [zoom]);

  // Wire click targets. A netlistsvg wire is a 1 px stroke, and a stroke's hit
  // region is exactly the painted stroke — measured at +/-0.5 px, which is a
  // fraction of ordinary hand tremor. Runs once per layout, before the value
  // stamps, so the invisible copies are stamped with the rest and resolve a
  // click through the same `data-gp-net` path as the wire they cover.
  useLayoutEffect(() => {
    const container = canvasRef.current;
    if (!container || !svg) return;
    applyHitTargets(container);
  }, [svg]);

  // §24.2 value stamps. Re-run on every probe change; this only sets attributes
  // on the existing layout, so stepping the clock never re-lays out the sheet.
  useLayoutEffect(() => {
    const container = canvasRef.current;
    if (!container || !svg) return;
    // A value drawn on a stale sheet is a measurement of a netlist that no
    // longer corresponds to the spec. Stop stamping rather than colour it
    // confidently; the banner says why.
    if (!showValues || stale || decoration === null) {
      clearNetValues(container);
      return;
    }
    applyNetValues(container, decoration);
    if (showFlow) applyFlowDots(container);
    else clearFlowDots(container);
  }, [svg, showValues, showFlow, decoration, stale]);

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

  // §C12 edit affordances: when editing, stamp each wire and input port with a
  // `title` naming the field and the value a click will write, and mark them so
  // the CSS can show an edit cursor. Off, every stamp is removed.
  useLayoutEffect(() => {
    const container = canvasRef.current;
    if (!container || !svg) return;
    applyEditAffordances(container, {
      active: editMode,
      testPoints: model ? model.testPoints.map((t) => t.net) : [],
      inputs: model ? model.inputs.map((i) => ({ name: i.name, sync: i.sync })) : [],
      gates: cellNames,
      showPacked,
    });
  }, [svg, editMode, model, cellNames, showPacked]);

  const rebuild = useCallback(() => {
    setRebuilding(true);
    setError(null);
    api
      .build()
      .then((env) => {
        if (!env.ok) {
          setError(env.error.message);
          return;
        }
        // Only now is the artefact on disk newer than the edit, so refetch.
        setNetlistVersion((v) => v + 1);
      })
      .finally(() => setRebuilding(false));
  }, [api]);

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

  /* --- spec edits (§C12): test points, input sync, regroup -------------- */

  const packingCells = useMemo(
    () => (parsed ? parsed.cells.map((c) => ({ name: c.name, func: c.type })) : []),
    [parsed],
  );

  const forceGroups = model?.packing.forceGroups ?? [];

  const stableNames = useMemo(
    () => (packed ? stableNamesFromPacked(packed.packages) : {}),
    [packed],
  );

  const toggleTestPointAt = useCallback(
    (net: string) => {
      if (!model) return;
      const result = toggleTestPoint(model.testPoints.map((t) => t.net), net);
      if (result.refusal !== null || result.nets === null) {
        setRefusal(result.refusal);
        return;
      }
      setRefusal(null);
      // Recompute from the live text, not the one this render closed over: the
      // inspector sits beside this view and edits the same document, and two
      // edits from one snapshot lose the earlier one.
      const nets = result.nets;
      editSpec((current) => setTestPoints(current, nets).text);
    },
    [model, specText, editSpec],
  );

  const toggleInputSyncAt = useCallback(
    (name: string) => {
      if (!model) return;
      const input = model.inputs.find((i) => i.name === name);
      if (!input) return;
      setRefusal(null);
      const next = !input.sync;
      editSpec((current) => setInputSync(current, name, next).text);
    },
    [model, editSpec],
  );

  const regroupInto = useCallback(
    (sourceInstance: string, targetInstanceCells: string[]) => {
      const result = regroupToPackage(
        specText,
        packingCells,
        forceGroups,
        stableNames,
        sourceInstance,
        targetInstanceCells,
      );
      if (result.text === null || result.refusal !== null) {
        setRefusal(result.refusal);
        return;
      }
      setRefusal(null);
      // The regroup decision is computed from `specText` above; re-run it
      // against the live text so a concurrent edit is not discarded.
      editSpec((current) => {
        const fresh = regroupToPackage(
          current, packingCells, forceGroups, stableNames, sourceInstance, targetInstanceCells,
        );
        return fresh.text;
      });
    },
    [specText, packingCells, forceGroups, stableNames, editSpec],
  );

  const onCanvasClick = (event: React.MouseEvent<HTMLDivElement>) => {
    // A pan ends with a `click` on whatever the pointer happens to be over.
    // Letting it through would mean every drag across the sheet also changed
    // the selection — or, in edit mode, rewrote the spec.
    if (panConsumedClick.current) {
      panConsumedClick.current = false;
      return;
    }
    const target = event.target as Element | null;
    if (editMode) {
      // In edit mode a click on a wire is a test-point edit and a click on an
      // input port is a synchroniser edit; nothing else happens, so a click
      // meant to *inspect* can never rewrite the spec.
      const net = target?.getAttribute?.('data-gp-net') ?? null;
      if (net !== null) {
        toggleTestPointAt(net);
        return;
      }
      const group = target?.closest?.('g[id^="cell_"]') ?? null;
      const id = group?.getAttribute('id') ?? null;
      if (id !== null) {
        const name = id.slice('cell_'.length);
        if (model && model.inputs.some((i) => i.name === name)) {
          toggleInputSyncAt(name);
          return;
        }
      }
      return;
    }
    const net = target?.getAttribute?.('data-gp-net') ?? null;
    if (net !== null) {
      setSelection({ kind: 'net', name: net });
      return;
    }
    const group = target?.closest?.('g[id^="cell_"]') ?? null;
    const id = group?.getAttribute('id') ?? null;
    if (id !== null) setSelection({ kind: 'cell', name: id.slice('cell_'.length) });
  };

  const onCanvasMouseDown = (event: React.MouseEvent<HTMLDivElement>) => {
    if (!editMode || !showPacked) return;
    const target = event.target as Element | null;
    const group = target?.closest?.('g[id^="cell_"]') ?? null;
    const id = group?.getAttribute('id') ?? null;
    if (id === null) return;
    const name = id.slice('cell_'.length);
    if (cellNames.has(name)) {
      setDragSource(name);
      setRefusal(null);
    }
  };

  const onCanvasMouseUp = (event: React.MouseEvent<HTMLDivElement>) => {
    const source = dragSource;
    setDragSource(null);
    if (!source) return;
    const target = event.target as Element | null;
    // An empty packed view offers no package to drop onto, so it has no
    // `[data-refdes]` boundary. The empty drop target stands in so the regroup
    // refusal (no build -> no stable names) is reachable and the user is *told
    // why* rather than having the drag silently swallowed.
    const dropZone = target?.closest?.('[data-gp-drop-zone]') ?? null;
    if (dropZone !== null) {
      setRefusal(NO_BUILD_REFUSAL);
      return;
    }
    const pkgEl = target?.closest?.('[data-refdes]') ?? null;
    const refdes = pkgEl?.getAttribute('data-refdes') ?? null;
    if (refdes === null) return;
    const pkg = packed?.packages.find((p) => p.refdes === refdes);
    if (!pkg) return;
    regroupInto(source, pkg.instanceCells);
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

  const packagesEmpty = packed === null || packed.packages.length === 0;

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

  /**
   * Wheel zoom, anchored under the pointer.
   *
   * Zooming about the scroll origin instead would throw whatever the user was
   * looking at off-screen on a large sheet, which is worse than no wheel zoom
   * at all. The zoom host is `transform: scale(z)` with `transform-origin: top
   * left`, so the sheet coordinate under the cursor is
   * `(scroll + offset) / z`; holding it fixed across the zoom gives the new
   * scroll offset directly.
   *
   * Plain wheel zooms rather than scrolls: this is a schematic viewer, the
   * gesture matches the EDA tools its users already have open, and the canvas
   * keeps its scrollbars (and shift+wheel) for panning.
   */
  const onWheel = (event: WheelEvent) => {
    const host = scrollRef.current;
    if (!host || event.deltaY === 0) return;
    // Shift+wheel is the conventional horizontal pan; leave it to the browser.
    if (event.shiftKey) return;
    event.preventDefault();

    const rect = host.getBoundingClientRect();
    const offsetX = event.clientX - rect.left;
    const offsetY = event.clientY - rect.top;

    // A trackpad reports many small deltas and a mouse a few large ones;
    // scaling by the step per notch would make the trackpad unusable, so the
    // factor is exponential in the delta and identical in feel for both.
    const next = clamp(zoom * Math.pow(ZOOM_STEP, -event.deltaY / 100), ZOOM_MIN, ZOOM_MAX);
    if (next === zoom) return;

    // Record the anchor now; the scroll is applied by the layout effect below,
    // once the zoom host has actually been resized. `requestAnimationFrame`
    // here is not late enough: the assignment ran against the *old* scroll area
    // and was clamped to it (measured — scrollLeft wanted 312 and got 55, the
    // old maximum), so the sheet drifted horizontally by exactly the amount it
    // could not scroll.
    pendingAnchor.current = {
      sheetX: (host.scrollLeft + offsetX) / zoom,
      sheetY: (host.scrollTop + offsetY) / zoom,
      offsetX,
      offsetY,
    };
    setZoom(next);
  };

  // Whether there is anything to pan *to*. A grab cursor over a sheet that
  // already fits the pane promises a movement the view cannot make, which is
  // the same class of lie as a button that does nothing. Re-measured on resize
  // as well as on zoom: the pane is a flex child of a resizable window, so its
  // client size changes without either the sheet or the zoom changing.
  useLayoutEffect(() => {
    const host = scrollRef.current;
    if (!host) {
      setPannable(false);
      return;
    }
    const measure = () => {
      const el = scrollRef.current;
      if (!el) return;
      setPannable(el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1);
    };
    measure();
    if (typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(measure);
    ro.observe(host);
    return () => ro.disconnect();
  }, [svg, zoom, svgSize, showMapped, showPacked]);

  /* --- drag to pan ------------------------------------------------------
   *
   * A large sheet is taller and wider than the pane, and the only way to reach
   * the rest of it was the scrollbars — on a schematic, where every other tool
   * lets you grab the sheet and move it. The wheel is already spoken for: it
   * zooms (and claims the gesture, see below), so it cannot also scroll.
   *
   * Left-drag pans and left-*click* still selects. Those share a button, so
   * they are separated by distance, not by modifier: the press is recorded and
   * nothing happens until the pointer has moved PAN_THRESHOLD_PX, at which
   * point the gesture becomes a pan and the `click` that ends it is dropped.
   * Middle-drag always pans, whatever it started on.
   *
   * The move/up listeners live on `window`, not on the canvas: a pan that
   * stopped the moment the pointer left the pane would strand the sheet
   * half-moved, and a mouseup delivered outside the canvas would leave the
   * drag latched on for ever.
   */
  const onPanStart = (event: React.MouseEvent<HTMLDivElement>) => {
    const host = scrollRef.current;
    if (!host) return;
    if (event.button !== 0 && event.button !== 1) return;
    // An edit-mode regroup drag owns the pointer from the same press
    // (`onCanvasMouseDown`); two drags on one gesture is one drag too many.
    if (event.button === 0 && editMode && showPacked) {
      const group = (event.target as Element | null)?.closest?.('g[id^="cell_"]') ?? null;
      if (group !== null) return;
    }
    pan.current = {
      x: event.clientX,
      y: event.clientY,
      scrollLeft: host.scrollLeft,
      scrollTop: host.scrollTop,
      moved: false,
    };
    // Middle-drag is unambiguously a pan, so claim it before the platform's
    // own autoscroll starts and fights us for the same gesture.
    if (event.button === 1) event.preventDefault();
  };

  useEffect(() => {
    const move = (event: MouseEvent) => {
      const state = pan.current;
      const host = scrollRef.current;
      if (!state || !host) return;
      // A mouseup delivered outside the window is not always delivered at all,
      // and a pan that missed its release stays latched: the sheet then follows
      // the pointer with no button held, and only another click frees it.
      // `buttons` is the live state of the physical buttons, so it catches the
      // release that the event did not.
      // A mouseup delivered outside the window is not always delivered at all,
      // and a pan that missed its release stays latched: the sheet then follows
      // the pointer with no button held, and only another click frees it.
      // `buttons` is the live state of the physical buttons, so it catches the
      // release that the event did not.
      if (event.buttons === 0) {
        pan.current = null;
        if (state.moved) {
          panConsumedClick.current = true;
          setPanning(false);
        }
        return;
      }
      const dx = event.clientX - state.x;
      const dy = event.clientY - state.y;
      if (!state.moved) {
        if (Math.abs(dx) < PAN_THRESHOLD_PX && Math.abs(dy) < PAN_THRESHOLD_PX) return;
        state.moved = true;
        setPanning(true);
      }
      // Drag the sheet with the pointer: content moves the way the hand does,
      // so the scroll offset moves the other way.
      host.scrollLeft = state.scrollLeft - dx;
      host.scrollTop = state.scrollTop - dy;
      // Without this the drag also runs a text selection across the sheet's
      // `<text>` labels and paints the schematic blue as it goes.
      event.preventDefault();
    };
    const up = () => {
      const state = pan.current;
      pan.current = null;
      if (!state || !state.moved) return;
      panConsumedClick.current = true;
      setPanning(false);
    };
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', up);
    return () => {
      window.removeEventListener('mousemove', move);
      window.removeEventListener('mouseup', up);
    };
  }, []);

  // The wheel listener is attached natively, NOT through React's `onWheel`.
  //
  // React registers `wheel` at the root container as a *passive* listener, so
  // `preventDefault()` inside an `onWheel` prop is silently ignored. The zoom
  // still happened, which is why this went unnoticed: the canvas simply
  // scrolled at the same time, so a wheel gesture both zoomed the sheet and
  // slid it out from under the pointer. A non-passive listener is the only way
  // to claim the gesture. Caught by asserting `defaultPrevented` in
  // `schematic-pointer.spec.ts` rather than by looking at it.
  const wheelHandler = useRef(onWheel);
  wheelHandler.current = onWheel;
  useEffect(() => {
    const host = scrollRef.current;
    if (!host) return;
    const listener = (event: WheelEvent) => wheelHandler.current(event);
    host.addEventListener('wheel', listener, { passive: false });
    return () => host.removeEventListener('wheel', listener);
  }, [svg]);
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
          <Tooltip
            content={
              editMode
                ? 'stop editing the spec through the schematic'
                : 'edit the spec (test points, input synchronisers, packing) by clicking the schematic'
            }
          >
            <button
              type="button"
              className="view-btn"
              aria-pressed={editMode}
              data-testid="schematic-edit-toggle"
              onClick={() => {
                setEditMode((e) => !e);
                setRefusal(null);
                setDragSource(null);
              }}
            >
              <Icon name="provenance" decorative />
              edit
            </button>
          </Tooltip>
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

      {stale ? (
        <div className="stale-note" role="status" data-testid="schematic-stale">
          <Icon name="warning" decorative />
          <span>
            the spec changed since this sheet was built — it shows the previous
            design{showValues ? ', so signal values are not drawn' : ''}
          </span>
          <button
            type="button"
            className="view-btn"
            onClick={rebuild}
            disabled={rebuilding}
            data-testid="schematic-rebuild"
          >
            <Icon name="build" decorative />
            {rebuilding ? 'Rebuilding…' : 'Rebuild'}
          </button>
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

      {editMode ? (
        <div className="info-note" data-testid="schematic-edit-hint">
          <Icon name="provenance" decorative />
          <span>
            {dragSource
              ? `moving ${dragSource} — click the package to regroup it into`
              : 'edit: click a wire to toggle its test point; click an input port to toggle its synchroniser; drag a gate into a package to regroup'}
          </span>
        </div>
      ) : null}

      {refusal ? (
        <div className="error-note" role="alert" data-testid="schematic-edit-refusal">
          <Icon name="error" decorative />
          <span>{refusal}</span>
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
        data-edit={editMode ? 'on' : 'off'}
        data-panning={panning ? 'on' : 'off'}
        data-pannable={pannable ? 'on' : 'off'}
        ref={scrollRef}
        onMouseDown={onPanStart}
        onMouseUp={onCanvasMouseUp}
      >
        {svg ? (
          <div
            className="schematic__zoom-host"
            style={{
              transform: `scale(${zoom})`,
              // `transform` scales what is drawn but not the layout box, so the
              // scroll container sized itself to the *unzoomed* sheet: zooming
              // in pushed the right-hand side of a schematic somewhere no
              // scrollbar could reach, and wheel-zoom could not hold its anchor
              // horizontally because there was nothing to scroll. Reserving the
              // scaled size gives the scroll area the sheet actually occupies.
              ...(svgSize
                ? { width: svgSize.width * zoom, height: svgSize.height * zoom }
                : null),
            }}
          >
            {/* eslint-disable-next-line jsx-a11y/no-static-element-interactions */}
            <div
              ref={canvasRef}
              style={showMapped ? undefined : { display: 'none' }}
              onMouseOver={onCanvasHover}
              onMouseLeave={onCanvasLeave}
              onMouseDown={onCanvasMouseDown}
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
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  pointerEvents: dragSource ? 'auto' : 'none',
                }}
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

                {showPacked && editMode && packagesEmpty ? (
                  <g
                    data-gp-drop-zone="empty"
                    data-testid="schematic-drop-zone"
                    transform="translate(20, 20)"
                  >
                    <rect className="packed-drop-zone" width={240} height={36} rx={4} />
                    <text className="packed-drop-zone-label" x={12} y={23}>
                      drop a gate here to regroup
                    </text>
                  </g>
                ) : null}

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
