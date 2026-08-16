/**
 * Pure mapping from a §15.2 highlight set to the netlistsvg element IDs/classes
 * the schematic should mark as selected.
 *
 * The rendered netlist is keyed by *instance* names: netlistsvg wraps each cell
 * in `<g id="cell_<instance>">` and tags each wire with a `net_<bits>` class.
 * `HighlightSet.cells` are instance names and `HighlightSet.nets` are net names,
 * so the only translation here is net name -> bit indices (from the same helper
 * the overlay markers use). Kept pure so it is testable without a DOM.
 */

import type { HighlightSet } from '../selection/types';
import { netBitIndices } from '../worker/schematicOverlay';

export interface SvgSelectionTargets {
  /** `id` attribute values to match (`cell_<instance>`). */
  cellIds: string[];
  /** `net_<bits>` class tokens to match. */
  netClasses: string[];
}

export function selectionSvgTargets(
  netlist: unknown,
  highlights: HighlightSet,
): SvgSelectionTargets {
  const cellIds = highlights.cells.map((c) => `cell_${c}`).sort();
  const bitsByName = netBitIndices(netlist);
  const netClasses: string[] = [];
  for (const net of [...new Set(highlights.nets)].sort()) {
    const bits = bitsByName.get(net);
    if (bits && bits.length > 0) netClasses.push(`net_${bits.join(',')}`);
  }
  return { cellIds, netClasses };
}
