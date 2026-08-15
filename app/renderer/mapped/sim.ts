/**
 * Client-side evaluation of a Yosys `write_json` mapped netlist, used to render
 * the truth-table "simulated outputs" column and the per-row divergence against
 * the live spec evaluation.
 *
 * This mirrors the *parsing* shape of `gatepack/netlist.py` /
 * `gatepack/provenance/capture.py` (single-bit cells, net indices resolved from
 * `netnames`) and the *function* table of `libraries/74aup.csv`. It is arithmetic
 * over the netlist — never synthesis, never a decision the core makes.
 *
 * Sequential (F/M) cell outputs are treated as unknown (`'x'`): the combinational
 * cone is evaluated, state is not clocked. Divergence is therefore reported only
 * where both sides are known, which is exactly the combinational case the
 * exhaustive equivalence check reduces to a truth table for.
 */

import { evaluateCell } from './cells';
import type { Bit } from '../design/expr';

export interface NetlistCell {
  name: string;
  type: string;
  /** pin -> resolved connection: a net name or a constant '0'|'1'|'x'. */
  connections: Record<string, string>;
  directions: Record<string, 'input' | 'output' | 'inout'>;
}

export interface ParsedNetlist {
  top: string;
  inputs: string[];
  outputs: string[];
  cells: NetlistCell[];
}

export type UnknownJson = Record<string, unknown>;

function asRecord(v: unknown): UnknownJson | null {
  return typeof v === 'object' && v !== null && !Array.isArray(v) ? (v as UnknownJson) : null;
}

function asArray(v: unknown): unknown[] | null {
  return Array.isArray(v) ? v : null;
}

/** Resolve a single connection bit (int index or constant string) to a net/constant. */
function resolveBit(bit: unknown, bitToNet: Map<number, string>): string {
  if (typeof bit === 'string') {
    if (bit === '0' || bit === '1' || bit === 'x' || bit === 'z') return bit;
    return 'x';
  }
  if (typeof bit === 'number') {
    return bitToNet.get(bit) ?? 'x';
  }
  return 'x';
}

export function parseWriteJson(data: unknown): ParsedNetlist {
  const root = asRecord(data);
  const modules = root ? asRecord(root['modules']) : null;
  if (!modules || Object.keys(modules).length === 0) {
    return { top: '', inputs: [], outputs: [], cells: [] };
  }

  // Choose the flattened top: the module with the most cells.
  let top = '';
  let bestCount = -1;
  for (const [name, modRaw] of Object.entries(modules)) {
    const mod = asRecord(modRaw);
    const cells = mod ? asRecord(mod['cells']) : null;
    const count = cells ? Object.keys(cells).length : 0;
    if (count > bestCount) {
      top = name;
      bestCount = count;
    }
  }

  const mod = asRecord(modules[top]);
  if (!mod) return { top, inputs: [], outputs: [], cells: [] };

  const bitToNet = new Map<number, string>();
  const netnames = asRecord(mod['netnames']) ?? {};
  for (const [net, infoRaw] of Object.entries(netnames)) {
    const info = asRecord(infoRaw);
    const bits = asArray(info?.['bits']) ?? [];
    for (const bit of bits) {
      if (typeof bit === 'number') bitToNet.set(bit, net);
    }
  }

  const inputs: string[] = [];
  const outputs: string[] = [];
  const ports = asRecord(mod['ports']) ?? {};
  for (const [name, infoRaw] of Object.entries(ports)) {
    const info = asRecord(infoRaw);
    const direction = info?.['direction'];
    if (direction === 'input') inputs.push(name);
    else if (direction === 'output') outputs.push(name);
  }

  const cells: NetlistCell[] = [];
  const rawCells = asRecord(mod['cells']) ?? {};
  for (const [name, infoRaw] of Object.entries(rawCells)) {
    const info = asRecord(infoRaw);
    if (!info) continue;
    const directions: Record<string, 'input' | 'output' | 'inout'> = {};
    const dirsRaw = asRecord(info['port_directions']) ?? {};
    for (const [pin, dir] of Object.entries(dirsRaw)) {
      if (dir === 'input' || dir === 'output' || dir === 'inout') directions[pin] = dir;
    }
    const connections: Record<string, string> = {};
    const connRaw = asRecord(info['connections']) ?? {};
    for (const [pin, bitsRaw] of Object.entries(connRaw)) {
      const bits = asArray(bitsRaw) ?? [];
      connections[pin] = resolveBit(bits[0], bitToNet);
    }
    cells.push({ name, type: String(info['type'] ?? ''), connections, directions });
  }

  cells.sort((a, b) => a.name.localeCompare(b.name));
  return { top, inputs, outputs, cells };
}

/** Net name -> Bit. Constants '0'/'1' map to themselves; anything unknown is 'x'. */
export type NetValues = Record<string, Bit>;

function constantBit(v: string): Bit {
  return v === '0' || v === '1' ? v : 'x';
}

/**
 * Evaluate the combinational cone of the netlist under an input assignment.
 * Returns output-port name -> Bit. Unknown/sequential signals are `'x'`.
 */
export function simulateCombinational(
  netlist: ParsedNetlist,
  inputs: Record<string, Bit>,
): Record<string, Bit> {
  const values: NetValues = {};
  for (const name of netlist.inputs) {
    values[name] = inputs[name] ?? 'x';
  }

  // Iterate to a fixpoint: the mapped netlist is acyclic combinational, so a
  // bounded number of passes over the (sorted) cells converges.
  const passes = Math.max(1, netlist.cells.length + 1);
  for (let p = 0; p < passes; p += 1) {
    let changed = false;
    for (const cell of netlist.cells) {
      const inputBits: Record<string, Bit> = {};
      for (const [pin, conn] of Object.entries(cell.connections)) {
        if (cell.directions[pin] !== 'output') {
          inputBits[pin] = conn in values ? values[conn] : constantBit(conn);
        }
      }
      const result = evaluateCell(cell.type, inputBits);
      if (result === null) continue; // unmodelled (sequential/S/M): leave unknown
      for (const [pin, conn] of Object.entries(cell.connections)) {
        if (cell.directions[pin] === 'output' && conn !== '0' && conn !== '1' && conn !== 'x' && conn !== 'z') {
          if (values[conn] !== result) {
            values[conn] = result;
            changed = true;
          }
        }
      }
    }
    if (!changed) break;
  }

  const out: Record<string, Bit> = {};
  for (const name of netlist.outputs) {
    out[name] = name in values ? values[name] : 'x';
  }
  return out;
}
