/**
 * The pure mapping behind §15.2 linked selection: a selection in any view
 * resolves to the artefacts it implicates in every other view, and back.
 *
 * Two carriers cross the views:
 *
 *  * **provenance** (`provenance()`): pointer -> nets + cells, each `exact` or
 *    `inferred`. This is the spine; where it is partial or absent the map says
 *    so (`confidence: 'none'`) rather than implying a false one-to-one.
 *  * **cone** (`mappedNetlist()`): a truth-table row implicates the gates in the
 *    combinational cone of its outputs, computed structurally — which is what
 *    makes "a diverging row highlights its gates" real.
 *
 * The `diverges` flag itself always comes from the *core* (`simulate()`); this
 * module only uses it to decide which output nets to highlight.
 */

import type { ProvenanceMap, SimulationRow } from '../../shared/api';
import type { DesignModel } from '../design/model';
import type { ParsedNetlist } from '../mapped/sim';
import { EMPTY_HIGHLIGHTS, type HighlightSet, type LinkConfidence, type LinkContext, type Selection } from './types';

const CONSTANTS = new Set(['0', '1', 'x', 'z']);

/* ------------------------------------------------------------------ */
/* Pointer parsing (§15.1 token: `design.yaml:12:transitions[3]`)      */
/* ------------------------------------------------------------------ */

export interface ParsedPointer {
  filename: string;
  line: number | null;
  path: string;
}

export function parsePointer(pointer: string): ParsedPointer {
  const first = pointer.indexOf(':');
  const second = first === -1 ? -1 : pointer.indexOf(':', first + 1);
  const filename = first === -1 ? pointer : pointer.slice(0, first);
  const lineText = second === -1 ? pointer.slice(first + 1) : pointer.slice(first + 1, second);
  const path = second === -1 ? pointer.slice(first + 1) : pointer.slice(second + 1);
  const line = Number(lineText);
  return { filename, line: Number.isFinite(line) ? line : null, path };
}

/* ------------------------------------------------------------------ */
/* Provenance index                                                     */
/* ------------------------------------------------------------------ */

type Entry = ProvenanceMap['entries'][number];

export interface ProvenanceIndex {
  /** path (e.g. `transitions[2]`) -> matching entries. */
  byPath: Map<string, Entry[]>;
  /** net name -> matching entries. */
  byNet: Map<string, Entry[]>;
  /** cell name -> matching entries. */
  byCell: Map<string, Entry[]>;
}

export function indexProvenance(provenance: ProvenanceMap): ProvenanceIndex {
  const byPath = new Map<string, Entry[]>();
  const byNet = new Map<string, Entry[]>();
  const byCell = new Map<string, Entry[]>();
  for (const entry of provenance.entries) {
    const { path } = parsePointer(entry.pointer);
    push(byPath, path, entry);
    for (const net of entry.nets) push(byNet, net, entry);
    for (const cell of entry.cells) push(byCell, cell, entry);
  }
  return { byPath, byNet, byCell };
}

function push(map: Map<string, Entry[]>, key: string, entry: Entry): void {
  const list = map.get(key);
  if (list) list.push(entry);
  else map.set(key, [entry]);
}

/** Confidence of the strongest provenance link for a set of pointer paths. */
export function linkConfidence(index: ProvenanceIndex, paths: string[]): LinkConfidence {
  let inferred = false;
  for (const path of paths) {
    const entries = index.byPath.get(path);
    if (!entries) continue;
    if (entries.some((e) => e.confidence === 'exact')) return 'exact';
    inferred = true;
  }
  return inferred ? 'inferred' : 'none';
}

/* ------------------------------------------------------------------ */
/* Path <-> selection                                                  */
/* ------------------------------------------------------------------ */

/** The provenance paths that identify a state / transition / input. */
function selectionPaths(selection: Selection, model: DesignModel): string[] {
  if (selection.kind === 'transition') {
    return model.transitions
      .map((t, i) => ({ t, i }))
      .filter(({ t }) => t.from === selection.from && t.to === selection.to)
      .map(({ i }) => `transitions[${i}]`);
  }
  if (selection.kind === 'state') {
    // C1 emits the bare token `states` for every state register, not
    // `states[i]` — all state bits share one pointer. Asking for an index
    // matched nothing, so every state selection read "no link" even though
    // states are the construct kind with the BEST provenance (exact, 1/1 on
    // every golden). The link is therefore state-group-wide, not per-state.
    const i = model.states.indexOf(selection.id);
    return i === -1 ? [] : ['states'];
  }
  if (selection.kind === 'input') {
    const i = model.inputs.findIndex((p) => p.name === selection.name);
    return i === -1 ? [] : [`inputs[${i}]`];
  }
  return [];
}

/** Selection(s) a provenance path maps back to (the reverse direction). */
function pathToSelections(path: string, model: DesignModel): Selection[] {
  const transition = /^transitions\[(\d+)\]$/.exec(path);
  if (transition) {
    const i = Number(transition[1]);
    const t = model.transitions[i];
    return t ? [{ kind: 'transition', from: t.from, to: t.to }] : [];
  }
  // `states` covers every state at once (see selectionToPaths): the reverse
  // direction therefore selects them all rather than guessing one.
  if (path === 'states') {
    return model.states.map((id) => ({ kind: 'state', id }) as Selection);
  }
  const input = /^inputs\[(\d+)\]$/.exec(path);
  if (input) {
    const name = model.inputs[Number(input[1])]?.name;
    return name ? [{ kind: 'input', name }] : [];
  }
  return [];
}

/* ------------------------------------------------------------------ */
/* Cone                                                                */
/* ------------------------------------------------------------------ */

/** Net -> driving cell name (first driver wins; single-bit netlist). */
function driverByNet(netlist: ParsedNetlist): Map<string, string> {
  const drivers = new Map<string, string>();
  for (const cell of netlist.cells) {
    for (const [pin, conn] of Object.entries(cell.connections)) {
      if (cell.directions[pin] === 'output' && conn && !CONSTANTS.has(conn) && !drivers.has(conn)) {
        drivers.set(conn, cell.name);
      }
    }
  }
  return drivers;
}

/**
 * Transitive fan-in cells of `seedNets` (the combinational cone). A cell is
 * implicated in a truth-table row iff it sits in this set.
 */
export function coneCells(netlist: ParsedNetlist, seedNets: string[]): string[] {
  const drivers = driverByNet(netlist);
  const byName = new Map(netlist.cells.map((c) => [c.name, c]));
  const cells = new Set<string>();
  const queue = [...seedNets];
  const seenNets = new Set<string>();
  while (queue.length) {
    const net = queue.pop() as string;
    const driver = drivers.get(net);
    if (!driver || cells.has(driver)) continue;
    cells.add(driver);
    const cell = byName.get(driver);
    if (!cell) continue;
    for (const [pin, conn] of Object.entries(cell.connections)) {
      if (cell.directions[pin] === 'input' && conn && !CONSTANTS.has(conn) && !seenNets.has(conn)) {
        seenNets.add(conn);
        queue.push(conn);
      }
    }
  }
  return [...cells].sort();
}

/* ------------------------------------------------------------------ */
/* Divergence                                                          */
/* ------------------------------------------------------------------ */

/** Output names on which a row diverges (both sides known and different). */
export function divergingOutputs(row: SimulationRow): string[] {
  return Object.keys(row.expected).filter((name) => {
    const got = row.actual?.[name];
    return got !== undefined && got !== 'x' && got !== row.expected[name];
  });
}

/* ------------------------------------------------------------------ */
/* Resolution                                                          */
/* ------------------------------------------------------------------ */

function provenanceHighlights(
  index: ProvenanceIndex,
  paths: string[],
): { pointers: string[]; nets: string[]; cells: string[] } {
  const pointers = new Set<string>();
  const nets = new Set<string>();
  const cells = new Set<string>();
  for (const path of paths) {
    for (const entry of index.byPath.get(path) ?? []) {
      pointers.add(entry.pointer);
      for (const n of entry.nets) nets.add(n);
      for (const c of entry.cells) cells.add(c);
    }
  }
  return { pointers: [...pointers].sort(), nets: [...nets].sort(), cells: [...cells].sort() };
}

/** Which truth-table rows implicate a cell (all rows if it is in the output cone). */
function mintermsForCell(cellName: string, ctx: LinkContext): number[] {
  if (!ctx.netlist || !ctx.simulation) return [];
  const inCone = coneCells(ctx.netlist, ctx.netlist.outputs).includes(cellName);
  return inCone ? ctx.simulation.rows.map((_, i) => i) : [];
}

function mintermHighlights(index: number, ctx: LinkContext): { nets: string[]; cells: string[] } {
  if (!ctx.netlist) return { nets: [], cells: [] };
  const row = ctx.simulation?.rows[index];
  const seeds = row ? divergingOutputs(row) : [];
  const seedNets = seeds.length ? seeds : ctx.netlist.outputs;
  return { nets: seedNets.slice().sort(), cells: coneCells(ctx.netlist, seedNets) };
}

function transitionIndices(model: DesignModel, from: string, to: string): number[] {
  return model.transitions
    .map((_t, i) => i)
    .filter((i) => model.transitions[i].from === from && model.transitions[i].to === to);
}

function statesFrom(selections: Selection[]): string[] {
  const out = new Set<string>();
  for (const s of selections) {
    if (s.kind === 'state') out.add(s.id);
    else if (s.kind === 'transition') {
      out.add(s.from);
      out.add(s.to);
    }
  }
  return [...out].sort();
}

export function resolveSelection(selection: Selection, ctx: LinkContext): HighlightSet {
  const index = indexProvenance(ctx.provenance);
  const model = ctx.model;

  if (selection.kind === 'transition') {
    const paths = selectionPaths(selection, model);
    const { pointers, nets, cells } = provenanceHighlights(index, paths);
    return {
      pointers,
      nets,
      cells,
      minterms: [],
      states: [selection.from, selection.to],
      transitions: transitionIndices(model, selection.from, selection.to),
      confidence: linkConfidence(index, paths),
    };
  }

  if (selection.kind === 'state') {
    const paths = selectionPaths(selection, model);
    const { pointers, nets, cells } = provenanceHighlights(index, paths);
    return { pointers, nets, cells, minterms: [], states: [selection.id], transitions: [], confidence: linkConfidence(index, paths) };
  }

  if (selection.kind === 'input') {
    const paths = selectionPaths(selection, model);
    const { pointers, nets, cells } = provenanceHighlights(index, paths);
    return { pointers, nets, cells, minterms: [], states: [], transitions: [], confidence: linkConfidence(index, paths) };
  }

  if (selection.kind === 'minterm') {
    const { nets, cells } = mintermHighlights(selection.index, ctx);
    const row = ctx.simulation?.rows[selection.index];
    const states = row?.state ? [row.state] : [];
    return { pointers: [], nets, cells, minterms: [selection.index], states, transitions: [], confidence: 'none' };
  }

  if (selection.kind === 'cell') {
    const entries = index.byCell.get(selection.name) ?? [];
    const paths = entries.map((e) => parsePointer(e.pointer).path);
    const selections = paths.flatMap((p) => pathToSelections(p, model));
    const outputNet = outputNetOf(ctx.netlist, selection.name);
    const confidence = entries.some((e) => e.confidence === 'exact') ? 'exact' : entries.length ? 'inferred' : 'none';
    return {
      pointers: entries.map((e) => e.pointer),
      nets: outputNet ? [outputNet] : [],
      cells: [selection.name],
      minterms: mintermsForCell(selection.name, ctx),
      states: statesFrom(selections),
      transitions: selections
        .filter((s): s is Extract<Selection, { kind: 'transition' }> => s.kind === 'transition')
        .flatMap((s) => transitionIndices(model, s.from, s.to)),
      confidence,
    };
  }

  if (selection.kind === 'net') {
    const entries = index.byNet.get(selection.name) ?? [];
    const paths = entries.map((e) => parsePointer(e.pointer).path);
    const selections = paths.flatMap((p) => pathToSelections(p, model));
    const confidence = entries.some((e) => e.confidence === 'exact') ? 'exact' : entries.length ? 'inferred' : 'none';
    return {
      pointers: entries.map((e) => e.pointer),
      nets: [selection.name],
      cells: ctx.netlist ? coneCells(ctx.netlist, [selection.name]) : [],
      minterms: [],
      states: statesFrom(selections),
      transitions: selections
        .filter((s): s is Extract<Selection, { kind: 'transition' }> => s.kind === 'transition')
        .flatMap((s) => transitionIndices(model, s.from, s.to)),
      confidence,
    };
  }

  // package / property: the IPC contract does not expose a cell->refdes map or
  // the counterexample pointers outside `verify()`, so these map to nothing
  // rather than a false highlight (§15.2 "never imply a false one-to-one").
  return EMPTY_HIGHLIGHTS;
}

function outputNetOf(netlist: ParsedNetlist | null, cellName: string): string | null {
  if (!netlist) return null;
  const cell = netlist.cells.find((c) => c.name === cellName);
  if (!cell) return null;
  for (const [pin, conn] of Object.entries(cell.connections)) {
    if (cell.directions[pin] === 'output' && conn && !CONSTANTS.has(conn)) return conn;
  }
  return null;
}
