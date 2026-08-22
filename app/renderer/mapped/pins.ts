/**
 * Pin directions for library cells, mirrored from `gatepack/pins.py`.
 *
 * Yosys's post-`abc` `write_json` carries **no** `port_directions` — the cells
 * come back through `blifparse` with connections and nothing else. Every
 * consumer therefore has to resolve pin directions against the library, and
 * `gatepack/simulate.py::load_mapped` records what happens when one forgets:
 * every net evaluates to `x` and the check reports a status while measuring
 * nothing.
 *
 * The schematic hits the same wall in a more visible way. netlistsvg classifies
 * a cell's connections into input and output ports; with no directions to go on
 * it classifies none of them, drops every port, and routes no wires at all.
 *
 * This is a *mirror*, in the same sense `cells.ts` mirrors the G-cell function
 * table: G-cell input pins are `A`, `B`, `C`, ... with output `Y`
 * (`liberty/boolean.py::pin_names`), and the F-cell layout is §9.2 [R4-3].
 * Unknown types return `null` — never a guess, because a fabricated direction
 * would silently reroute a wire to the wrong pin, which looks like a schematic
 * and is not one.
 */

/** F-cell pin layout (§9.2 [R4-3]), mirroring `pins.py::F_PIN_DIRECTIONS`. */
const F_PIN_DIRECTIONS: Record<string, Record<string, 'input' | 'output'>> = {
  DFF: { D: 'input', CK: 'input', Q: 'output' },
  DFF_R: { D: 'input', CK: 'input', RST_N: 'input', Q: 'output' },
  DFF_S: { D: 'input', CK: 'input', SET_N: 'input', Q: 'output' },
  DFF_SR: { D: 'input', CK: 'input', SET_N: 'input', RST_N: 'input', Q: 'output' },
};

/** Provisional S-cell signal pins, mirroring `pins.py::S_PIN_DIRECTIONS`. */
const S_PIN_DIRECTIONS: Record<string, Record<string, 'input' | 'output'>> = {
  OSC: { OUT: 'output' },
  SUPERVISOR: { RESET: 'output' },
};

/** G-cell input counts from `libraries/74aup.csv`; output is always `Y`. */
const G_CELL_INPUTS: Record<string, number> = {
  INV: 1,
  BUF: 1,
  AND2: 2,
  AND3: 3,
  NAND2: 2,
  NAND3: 3,
  OR2: 2,
  OR3: 3,
  NOR2: 2,
  NOR3: 3,
  XOR2: 2,
  XNOR2: 2,
  MUX2: 3,
};

/** Yosys internal cells that can survive techmap; same A/B/C + Y convention. */
const INTERNAL_CELL_INPUTS: Record<string, number> = {
  $_NOT_: 1,
  $_BUF_: 1,
  $_AND_: 2,
  $_NAND_: 2,
  $_OR_: 2,
  $_NOR_: 2,
  $_XOR_: 2,
  $_XNOR_: 2,
};

const INTERNAL_FLOPS: Record<string, Record<string, 'input' | 'output'>> = {
  $_DFF_P_: { D: 'input', C: 'input', Q: 'output' },
  $_DFF_N_: { D: 'input', C: 'input', Q: 'output' },
};

/** `A`, `B`, `C`, ... — `liberty/boolean.py::pin_names`. */
function inputPinNames(count: number): string[] {
  return Array.from({ length: count }, (_, i) => String.fromCharCode(65 + i));
}

/**
 * Pin directions for a cell type, or `null` when this table does not know it.
 *
 * Power pins are deliberately absent, exactly as in `pins.py`: the emitters add
 * `VCC`/`GND` to every component and the netlist never carries them.
 */
export function cellPinDirections(
  type: string,
): Record<string, 'input' | 'output'> | null {
  const gInputs = G_CELL_INPUTS[type] ?? INTERNAL_CELL_INPUTS[type];
  if (gInputs !== undefined) {
    const out: Record<string, 'input' | 'output'> = {};
    for (const pin of inputPinNames(gInputs)) out[pin] = 'input';
    out.Y = 'output';
    return out;
  }
  return F_PIN_DIRECTIONS[type] ?? S_PIN_DIRECTIONS[type] ?? INTERNAL_FLOPS[type] ?? null;
}

/** Output pin names for a known cell type; empty for an unknown one. */
export function outputPins(type: string): string[] {
  const dirs = cellPinDirections(type);
  if (dirs === null) return [];
  return Object.keys(dirs)
    .filter((p) => dirs[p] === 'output')
    .sort();
}

/** True for the F-cells the clocked evaluator in `netSim.ts` models. */
export function isFlopType(type: string): boolean {
  return type in F_PIN_DIRECTIONS || type in INTERNAL_FLOPS;
}

/** The clock pin of a flop type (`CK` for F-cells, `C` for Yosys internals). */
export function clockPin(type: string): string | null {
  if (type in F_PIN_DIRECTIONS) return 'CK';
  if (type in INTERNAL_FLOPS) return 'C';
  return null;
}
