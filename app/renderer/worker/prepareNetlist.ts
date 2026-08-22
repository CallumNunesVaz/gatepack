/**
 * Normalise a Yosys `write_json` mapped netlist for netlistsvg (§C12).
 *
 * `gatepack mapped-netlist` deliberately hands `mapped.json` through unchanged
 * ("the renderer must not be given a second, divergent representation of the
 * netlist"). That is the right contract, and it means the *renderer* has to
 * supply the two things netlistsvg needs and post-`abc` output does not carry:
 *
 *  1. **`port_directions`.** Yosys writes them for cells it knows; cells that
 *     come back through `blifparse` after technology mapping have none. Without
 *     them netlistsvg classifies zero ports, so it drew every gate as a bare
 *     type name with no pins and **no wires at all** — the schematic view was a
 *     column of labels. Directions come from `mapped/pins.ts`, the mirror of
 *     `gatepack/pins.py`, and only for types that table actually knows.
 *
 *  2. **Display attributes.** `gp_refdes` (from the packed view) and `gp_type`
 *     let the skin label a gate `U3 / NAND2` the way a schematic does, instead
 *     of `$abc$133$auto$blifparse.cc:386:parse_blif$137`.
 *
 * Nothing here invents electrical meaning. A cell type the pin table does not
 * know keeps whatever it had and is returned in `unresolvedTypes` so the view
 * can say so out loud; a cell that is in no package gets no refdes rather than
 * a plausible one.
 */

import { cellPinDirections } from '../mapped/pins';
import type { PackedView } from '../../shared/api';

export interface PreparedNetlist {
  /** The netlist to hand to netlistsvg. A copy; the input is never mutated. */
  netlist: unknown;
  /** Cell types with no entry in the pin table, sorted and de-duplicated. */
  unresolvedTypes: string[];
  /** Cells that got `port_directions` from the pin table. */
  resolvedCells: number;
  /** Cells whose `port_directions` the netlist already carried. */
  preResolvedCells: number;
}

function asRecord(v: unknown): Record<string, unknown> | null {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : null;
}

/** Instance cell name -> package refdes, from the §C13 packed view. */
export function refdesByInstance(packed: PackedView | null): Map<string, string> {
  const out = new Map<string, string>();
  if (packed === null) return out;
  for (const pkg of packed.packages) {
    for (const instance of pkg.instanceCells) out.set(instance, pkg.refdes);
  }
  return out;
}

export function prepareNetlist(
  netlist: unknown,
  packed: PackedView | null = null,
): PreparedNetlist {
  const unresolved = new Set<string>();
  let resolvedCells = 0;
  let preResolvedCells = 0;

  const root = asRecord(netlist);
  const modules = root ? asRecord(root['modules']) : null;
  if (root === null || modules === null) {
    return { netlist, unresolvedTypes: [], resolvedCells: 0, preResolvedCells: 0 };
  }

  const refdes = refdesByInstance(packed);

  // A structural copy: only the objects this function rewrites are cloned, so a
  // large netlist is not duplicated wholesale, and the caller's value — which
  // other views hold and parse — is never mutated.
  const nextModules: Record<string, unknown> = { ...modules };

  for (const [moduleName, moduleRaw] of Object.entries(modules)) {
    const mod = asRecord(moduleRaw);
    const cells = mod ? asRecord(mod['cells']) : null;
    if (mod === null || cells === null) continue;

    const nextCells: Record<string, unknown> = {};
    for (const [instance, cellRaw] of Object.entries(cells)) {
      const cell = asRecord(cellRaw);
      if (cell === null) {
        nextCells[instance] = cellRaw;
        continue;
      }
      const type = String(cell['type'] ?? '');
      const next: Record<string, unknown> = { ...cell };

      const existing = asRecord(cell['port_directions']);
      if (existing !== null && Object.keys(existing).length > 0) {
        preResolvedCells += 1;
      } else {
        const directions = cellPinDirections(type);
        if (directions === null) {
          unresolved.add(type);
        } else {
          // Only pins the cell actually connects: a direction for a pin that is
          // not in `connections` would put a port on the symbol with nothing on
          // the other end of it.
          const connections = asRecord(cell['connections']) ?? {};
          const applied: Record<string, string> = {};
          for (const pin of Object.keys(connections)) {
            const dir = directions[pin];
            if (dir !== undefined) applied[pin] = dir;
          }
          if (Object.keys(applied).length === Object.keys(connections).length) {
            next['port_directions'] = applied;
            resolvedCells += 1;
          } else {
            // A connected pin the table has no direction for. Routing the rest
            // would drop that pin's wire silently, so the cell is left for the
            // generic template and reported.
            unresolved.add(type);
          }
        }
      }

      const attributes = { ...(asRecord(cell['attributes']) ?? {}) };
      attributes['gp_type'] = type;
      const ref = refdes.get(instance);
      if (ref !== undefined) attributes['gp_refdes'] = ref;
      next['attributes'] = attributes;

      nextCells[instance] = next;
    }
    nextModules[moduleName] = { ...mod, cells: nextCells };
  }

  return {
    netlist: { ...root, modules: nextModules },
    unresolvedTypes: [...unresolved].sort(),
    resolvedCells,
    preResolvedCells,
  };
}
