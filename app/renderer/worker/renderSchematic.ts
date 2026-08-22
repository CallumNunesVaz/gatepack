/**
 * netlistsvg + elkjs schematic rendering, isolated so it is testable without a
 * Worker. netlistsvg consumes Yosys `write_json` directly and produces IEEE gate
 * symbols with orthogonal routing; elkjs (used internally by netlistsvg) runs
 * the layout. This module is imported by the web worker so the layout never
 * blocks the UI thread.
 *
 * The skin is **ours**, not netlistsvg's `default.svg`. The stock skin only
 * aliases Yosys internal cell names (`$_AND_`, `$dff`, …); a gatepack netlist is
 * post-`abc`, so every cell is a 74AUP library cell (`AND2`, `NAND2`, `DFF_R`)
 * and matched none of them. Every gate fell through to the `generic` template,
 * which — with no `port_directions` in post-`abc` `write_json` — could classify
 * no pins, so netlistsvg drew no ports and no wires. See `gatepack.skin.svg`
 * for the symbol set and `prepareNetlist.ts` for the directions.
 */

import netlistsvg from 'netlistsvg';
import skin from './gatepack.skin.svg?raw';
import type { Bit } from '../design/expr';

export interface SchematicRender {
  svg: string;
  /**
   * `net_<bits>` class -> the literal netlistsvg materialised on that wire.
   *
   * netlistsvg turns a constant connection into a real node on a real net, so a
   * `D: ["1"]` tie-high becomes `D: [21]` — a bit index that appears in no
   * `netnames` entry and therefore has no value in any evaluation of the
   * original netlist. Without this map that wire renders as *unknown*, which is
   * a lie about a net that is tied to a rail.
   */
  constants: Map<string, Bit>;
}

function asRecord(v: unknown): Record<string, unknown> | null {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : null;
}

/**
 * Compare the netlist as given with the one netlistsvg rewrote, and record the
 * bit index it assigned to each literal.
 */
function constantClasses(original: unknown, laidOut: unknown): Map<string, Bit> {
  const out = new Map<string, Bit>();
  const before = asRecord(asRecord(original)?.['modules']);
  const after = asRecord(asRecord(laidOut)?.['modules']);
  if (before === null || after === null) return out;

  for (const [moduleName, moduleRaw] of Object.entries(before)) {
    const cellsBefore = asRecord(asRecord(moduleRaw)?.['cells']);
    const cellsAfter = asRecord(asRecord(after[moduleName])?.['cells']);
    if (cellsBefore === null || cellsAfter === null) continue;

    for (const [instance, cellRaw] of Object.entries(cellsBefore)) {
      const connBefore = asRecord(asRecord(cellRaw)?.['connections']);
      const connAfter = asRecord(asRecord(cellsAfter[instance])?.['connections']);
      if (connBefore === null || connAfter === null) continue;

      for (const [pin, bitsRaw] of Object.entries(connBefore)) {
        const literal = Array.isArray(bitsRaw) ? bitsRaw[0] : undefined;
        if (literal !== '0' && literal !== '1') continue;
        const assigned = connAfter[pin];
        const bit = Array.isArray(assigned) ? assigned[0] : undefined;
        if (typeof bit !== 'number') continue;
        out.set(`net_${bit}`, literal);
      }
    }
  }
  return out;
}

export async function renderSchematic(netlist: unknown): Promise<SchematicRender> {
  // netlistsvg **mutates what it is given**: `addConstants` and
  // `addSplitsJoins` rewrite the cells' `connections` in place. The schematic
  // view hands the same object to the evaluator, and the §15.2 link context
  // holds a parse of it, so rendering silently corrupted both — a tie-high
  // input came back as an unresolvable bit index and every net downstream of it
  // evaluated to `x`. Render against a copy and the caller's netlist is
  // untouched.
  const copy: unknown = structuredClone(netlist);
  const svg: string = await netlistsvg.render(skin, copy);
  return { svg, constants: constantClasses(netlist, copy) };
}
