/**
 * Combinational G-cell function table, mirrored from `libraries/74aup.csv` /
 * `gatepack/liberty/boolean.py`. The renderer uses this only to *evaluate* a
 * mapped netlist for the truth-table divergence column — arithmetic over data
 * the core already produced, never synthesis.
 */

import { parse, evaluate, type Bit } from '../design/expr';

export interface GateSpec {
  inputs: string[];
  func: string;
}

const G_CELLS: Record<string, GateSpec> = {
  INV: { inputs: ['A'], func: '!A' },
  BUF: { inputs: ['A'], func: 'A' },
  NAND2: { inputs: ['A', 'B'], func: '!(A&B)' },
  NAND3: { inputs: ['A', 'B', 'C'], func: '!(A&B&C)' },
  NOR2: { inputs: ['A', 'B'], func: '!(A|B)' },
  NOR3: { inputs: ['A', 'B', 'C'], func: '!(A|B|C)' },
  AND2: { inputs: ['A', 'B'], func: 'A&B' },
  AND3: { inputs: ['A', 'B', 'C'], func: 'A&B&C' },
  OR2: { inputs: ['A', 'B'], func: 'A|B' },
  XOR2: { inputs: ['A', 'B'], func: 'A^B' },
  XNOR2: { inputs: ['A', 'B'], func: '!(A^B)' },
};

/** Post-`techmap` internal cells Yosys may emit before `abc` (for robustness). */
const INTERNAL_CELLS: Record<string, GateSpec> = {
  $_NOT_: { inputs: ['A'], func: '!A' },
  $_BUF_: { inputs: ['A'], func: 'A' },
  $_AND_: { inputs: ['A', 'B'], func: 'A&B' },
  $_NAND_: { inputs: ['A', 'B'], func: '!(A&B)' },
  $_OR_: { inputs: ['A', 'B'], func: 'A|B' },
  $_NOR_: { inputs: ['A', 'B'], func: '!(A|B)' },
  $_XOR_: { inputs: ['A', 'B'], func: 'A^B' },
  $_XNOR_: { inputs: ['A', 'B'], func: '!(A^B)' },
};

/** Sequential (F) cells — their Q output is unknown without a clocking model. */
const SEQUENTIAL_CELLS = new Set(['DFF', 'DFF_R', 'DFF_S', 'DFF_SR', '$_DFF_P_', '$_DFF_N_']);

export function isCombinationalCell(type: string): boolean {
  return type in G_CELLS || type in INTERNAL_CELLS;
}

export function isSequentialCell(type: string): boolean {
  return SEQUENTIAL_CELLS.has(type);
}

/**
 * Evaluate a cell's output pins under an input-bit environment. Returns null for
 * cells whose function we do not model (sequential cells, macro/S cells).
 */
export function evaluateCell(
  type: string,
  inputBits: Record<string, Bit>,
): Bit | null {
  const spec = G_CELLS[type] ?? INTERNAL_CELLS[type];
  if (!spec) return null;
  const env: Record<string, Bit> = {};
  for (const pin of spec.inputs) env[pin] = inputBits[pin] ?? 'x';
  try {
    return evaluate(parse(spec.func), env);
  } catch {
    return 'x';
  }
}
