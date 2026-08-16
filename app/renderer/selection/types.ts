/**
 * §15.2 selection model. A selection is emitted by any view and reflected by
 * every view: the same token highlights the truth-table row, the FSM state/
 * transition, the spec line (via provenance pointers), the schematic net/cell
 * and the BOM card. Multi-select unions the highlight sets.
 */

import type { PackedView, ProvenanceMap, SimulationTable, VerifyResult } from '../../shared/api';
import type { DesignModel } from '../design/model';
import type { ParsedNetlist } from '../mapped/sim';

export type Selection =
  | { kind: 'state'; id: string }
  | { kind: 'minterm'; index: number }
  | { kind: 'input'; name: string }
  | { kind: 'cell'; name: string }
  | { kind: 'net'; name: string }
  | { kind: 'package'; refdes: string }
  | { kind: 'transition'; from: string; to: string }
  | { kind: 'property'; name: string }
  | { kind: 'cexStep'; property: string; cycle: number };

/** Provenance confidence for the selected spec construct. `none` = no link. */
export type LinkConfidence = 'exact' | 'inferred' | 'none';

export interface HighlightSet {
  /** Provenance pointers (§15.1 tokens) matching the selection. */
  pointers: string[];
  /** Schematic nets implicated (provenance + cone). */
  nets: string[];
  /** Schematic cells/gates implicated. */
  cells: string[];
  /** Truth-table rows implicated. */
  minterms: number[];
  /** FSM states implicated. */
  states: string[];
  /** FSM transition indices implicated. */
  transitions: number[];
  /** Package refdes implicated (a package card or a gate's containing package). */
  packages: string[];
  /** Provenance confidence of the *strongest* link (see `LinkConfidence`). */
  confidence: LinkConfidence;
}

export const EMPTY_HIGHLIGHTS: HighlightSet = {
  pointers: [],
  nets: [],
  cells: [],
  minterms: [],
  states: [],
  transitions: [],
  packages: [],
  confidence: 'none',
};

/** Everything `resolveSelection` needs to map a selection across views. */
export interface LinkContext {
  model: DesignModel;
  provenance: ProvenanceMap;
  netlist: ParsedNetlist | null;
  simulation: SimulationTable | null;
  /** §C12 packed layer — refdes -> cells, the cell<->package spine. */
  packed: PackedView | null;
  /** The last `verify()` result — counterexample pointers for property selections. */
  verify: VerifyResult | null;
}
