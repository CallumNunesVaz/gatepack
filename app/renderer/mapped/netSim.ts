/**
 * Whole-netlist value evaluation for the C12 signal overlay (§24.2, M16).
 *
 * `sim.ts` evaluates the combinational cone and reports *output ports* — enough
 * for the truth-table divergence column, not enough to colour a schematic,
 * which needs a value on every net including the internal `$abc$…$new_n12_`
 * ones. It also treats every F-cell output as `x`, which on a sequential design
 * leaves almost the whole sheet unknown.
 *
 * This module keeps the same discipline — arithmetic over the netlist the core
 * produced, never synthesis, never a decision — and adds two things:
 *
 *  - **every net**, not just the ports; and
 *  - **flop state**, held by the caller and advanced one clock edge at a time,
 *    so a sequential design can actually be walked.
 *
 * Async reset/set is applied §9.2-style: `RST_N`/`SET_N` are level-sensitive and
 * take effect *without* a clock edge, so asserting reset changes the sheet
 * immediately. They are re-evaluated inside the fixpoint because the reset net
 * is itself driven by logic (the §9.3 two-flop synchroniser feeds the state
 * flops from `rst_n_s2`, not from the raw pin).
 *
 * Unknown stays unknown. A cell type `cells.ts` does not model leaves its
 * output at `x` rather than guessing, and `x` renders as "no value" rather than
 * as a low net — a net drawn dim is a net measured low.
 */

import { evaluateCell } from './cells';
import { clockPin, isFlopType, outputPins } from './pins';
import type { NetlistCell, NetValues, ParsedNetlist } from './sim';
import type { Bit } from '../design/expr';

/** Flop instance name -> the bit currently held on its `Q`. */
export type FlopState = Record<string, Bit>;

export interface EvaluatedNetlist {
  /** Net name -> value. Constants resolve to themselves; unknown is `x`. */
  values: NetValues;
  /** Flop instances whose `Q` an async control forced this evaluation. */
  asyncForced: string[];
}

function constantBit(v: string): Bit {
  return v === '0' || v === '1' ? v : 'x';
}

/** Read a connection that may be a net name or a literal constant. */
function read(values: NetValues, conn: string): Bit {
  if (conn in values) return values[conn];
  return constantBit(conn);
}

/** The flop cells of a netlist, in the netlist's own (sorted) order. */
export function flopCells(netlist: ParsedNetlist): NetlistCell[] {
  return netlist.cells.filter((c) => isFlopType(c.type));
}

/** Every flop `Q` unknown — the honest state before the design is driven. */
export function initialFlopState(netlist: ParsedNetlist): FlopState {
  const out: FlopState = {};
  for (const cell of flopCells(netlist)) out[cell.name] = 'x';
  return out;
}

/**
 * The async override a flop's controls impose right now, or `null` when the
 * flop is free to hold its state. Active-low, per §9.2: the control *asserts*
 * at 0. An `x` on a control is not an assertion — it is an unknown, and forcing
 * on an unknown would invent a value.
 */
function asyncOverride(cell: NetlistCell, values: NetValues): Bit | null {
  const rst = cell.connections['RST_N'];
  if (rst !== undefined && read(values, rst) === '0') return '0';
  const set = cell.connections['SET_N'];
  if (set !== undefined && read(values, set) === '0') return '1';
  return null;
}

/**
 * Evaluate every net under an input assignment and a held flop state.
 *
 * The loop is a fixpoint rather than a topological walk because the async
 * controls make the graph cyclic in the value domain: a flop's `Q` depends on a
 * reset net that may be driven through other flops. On a well-formed design it
 * settles in a few passes. It is *bounded* rather than provably monotone — a
 * reset network that clears its own source can oscillate, which is not
 * hypothetical (it is what the `reset_polarity_flip` mutation produces) — so
 * the pass count is capped at the cell count and the result is whatever the
 * last pass held. A capped result is still an honest reading of a design that
 * does not settle; it is not reported as converged.
 */
export function evaluateNets(
  netlist: ParsedNetlist,
  inputs: Record<string, Bit>,
  flops: FlopState,
): EvaluatedNetlist {
  // Seed *every* net the netlist mentions at `x`, then refine. A net an
  // unmodelled cell drives must come back as an explicit unknown rather than as
  // a missing key: the caller cannot tell an absent key from a net it forgot to
  // ask about, and "no value" quietly rendering as "low" is exactly the failure
  // this overlay exists to avoid.
  const values: NetValues = {};
  for (const cell of netlist.cells) {
    for (const conn of Object.values(cell.connections)) {
      if (conn !== '0' && conn !== '1' && conn !== 'x' && conn !== 'z') values[conn] = 'x';
    }
  }
  for (const name of netlist.inputs) values[name] = inputs[name] ?? 'x';

  const flopList = flopCells(netlist);
  const forced = new Set<string>();

  const write = (conn: string | undefined, bit: Bit): boolean => {
    if (conn === undefined) return false;
    if (conn === '0' || conn === '1' || conn === 'x' || conn === 'z') return false;
    if (values[conn] === bit) return false;
    values[conn] = bit;
    return true;
  };

  const passes = Math.max(2, netlist.cells.length + 2);
  for (let p = 0; p < passes; p += 1) {
    let changed = false;

    // Flop outputs first: they are the state the combinational cone reads.
    for (const cell of flopList) {
      const override = asyncOverride(cell, values);
      if (override !== null) forced.add(cell.name);
      else forced.delete(cell.name);
      const q = override ?? flops[cell.name] ?? 'x';
      for (const pin of outputPins(cell.type)) {
        if (write(cell.connections[pin], q)) changed = true;
      }
    }

    for (const cell of netlist.cells) {
      if (isFlopType(cell.type)) continue;
      const inputBits: Record<string, Bit> = {};
      for (const [pin, conn] of Object.entries(cell.connections)) {
        if (cell.directions[pin] !== 'output') inputBits[pin] = read(values, conn);
      }
      const result = evaluateCell(cell.type, inputBits);
      if (result === null) continue; // unmodelled: leave its output unknown
      for (const [pin, conn] of Object.entries(cell.connections)) {
        if (cell.directions[pin] === 'output' && write(conn, result)) changed = true;
      }
    }

    if (!changed && p > 0) break;
  }

  return { values, asyncForced: [...forced].sort() };
}

/**
 * Settle the level-sensitive async controls with **no clock edge**: every flop
 * whose `RST_N`/`SET_N` is asserted takes the forced value, every other flop
 * holds.
 *
 * This is what asserting reset does on a real board, and it cascades: the §9.3
 * synchroniser flops take the raw reset pin, their `Q` drives the synchronised
 * reset, and the state flops take *that*. `evaluateNets` resolves the cascade
 * to a fixpoint first, so one pass over the settled values is enough.
 */
export function settleAsync(
  netlist: ParsedNetlist,
  inputs: Record<string, Bit>,
  flops: FlopState,
): FlopState {
  const { values } = evaluateNets(netlist, inputs, flops);
  const next: FlopState = { ...flops };
  for (const cell of flopCells(netlist)) {
    const override = asyncOverride(cell, values);
    if (override !== null) next[cell.name] = override;
  }
  return next;
}

/**
 * Advance one rising clock edge: every flop takes its `D`, except one an async
 * control is holding, which keeps the forced value.
 *
 * The clock net itself is not consulted. This is an *edge*, not a level: the
 * caller says "step", the way a waveform viewer's step button does. Modelling
 * the clock as a level would need a two-phase evaluation the schematic has no
 * way to show, and gated clocks are out of scope for a §C12 rendering.
 */
export function stepClock(
  netlist: ParsedNetlist,
  inputs: Record<string, Bit>,
  flops: FlopState,
): FlopState {
  const { values } = evaluateNets(netlist, inputs, flops);
  const next: FlopState = { ...flops };
  for (const cell of flopCells(netlist)) {
    const override = asyncOverride(cell, values);
    if (override !== null) {
      next[cell.name] = override;
      continue;
    }
    const d = cell.connections['D'];
    next[cell.name] = d === undefined ? 'x' : read(values, d);
  }
  return next;
}

/** True when the netlist has a clockable flop, i.e. the step control applies. */
export function isSequential(netlist: ParsedNetlist): boolean {
  return netlist.cells.some((c) => isFlopType(c.type) && clockPin(c.type) !== null);
}

/**
 * Nets that carry a clock, so the view can leave them out of the "flow of
 * logic" animation — a clock is not data moving through the cone, and marching
 * every clock net at once drowns the sheet.
 */
export function clockNets(netlist: ParsedNetlist): Set<string> {
  const out = new Set<string>();
  for (const cell of netlist.cells) {
    const pin = clockPin(cell.type);
    if (pin === null) continue;
    const conn = cell.connections[pin];
    if (conn !== undefined && conn !== '0' && conn !== '1' && conn !== 'x') out.add(conn);
  }
  return out;
}
