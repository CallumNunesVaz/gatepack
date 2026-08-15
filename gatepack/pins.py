"""Pin naming and directions for G-, F-, M- and S-cells (§9.1–§9.5).

G-cell input pins are ``A``, ``B``, ``C``, ... plus output ``Y`` (mirroring
``gatepack.liberty.boolean``).  F-cell pins follow the §9.2 [R4-3] flop layout —
``D``, ``CK`` and the optional async controls ``RST_N`` / ``SET_N``, output
``Q`` — so the netlist and the Liberty ``ff`` groups agree on pin names.

M- and S-cell pinouts are a **seam**: M-cell pins are defined in
``gatepack/macros`` and S-cell pins in ``gatepack/infra`` (concurrent milestones).
The S-cell table below is provisional (OSC, SUPERVISOR only) and exists so the
emitters are testable before those milestones land; it is *not* authoritative
pin data.
"""

from __future__ import annotations

from gatepack.liberty.boolean import pin_names as _g_input_pins
from gatepack.parts import Part

OUTPUT_PIN_G = "Y"
OUTPUT_PIN_F = "Q"

# F-cell pin layout (§9.2 [R4-3]); mirrors the Liberty ff groups in
# gatepack/liberty/generator.py so the two cannot disagree.
F_PIN_DIRECTIONS: dict[str, dict[str, str]] = {
    "DFF": {"D": "input", "CK": "input", "Q": "output"},
    "DFF_R": {"D": "input", "CK": "input", "RST_N": "input", "Q": "output"},
    "DFF_S": {"D": "input", "CK": "input", "SET_N": "input", "Q": "output"},
    "DFF_SR": {
        "D": "input",
        "CK": "input",
        "SET_N": "input",
        "RST_N": "input",
        "Q": "output",
    },
}

# Provisional S-cell signal pins (seam for gatepack/infra).  Power pins
# (VCC/GND) are added uniformly by the emitters, not listed here.
S_PIN_DIRECTIONS: dict[str, dict[str, str]] = {
    "OSC": {"OUT": "output"},
    "SUPERVISOR": {"RESET": "output"},
}

POWER_PINS = ("VCC", "GND")


def cell_pin_directions(part: Part) -> dict[str, str]:
    """Input/output pin directions for a cell, keyed by pin name.

    Power pins are deliberately absent; the emitters add ``VCC``/``GND`` to every
    component.  Raises ``KeyError`` for M-cells (their pinouts live in
    ``gatepack/macros``) and for unknown S-/F-cells.
    """
    if part.tier == "G":
        return {p: "input" for p in _g_input_pins(part.inputs)} | {OUTPUT_PIN_G: "output"}
    if part.tier == "F":
        spec = F_PIN_DIRECTIONS.get(part.cell)
        if spec is None:
            raise KeyError(f"unknown F-cell {part.cell!r}")
        return dict(spec)
    if part.tier == "S":
        spec = S_PIN_DIRECTIONS.get(part.cell)
        if spec is None:
            raise KeyError(f"unknown S-cell {part.cell!r}")
        return dict(spec)
    if part.tier == "M":
        raise KeyError(
            f"M-cell {part.cell!r} pinout is defined in gatepack/macros (not yet "
            f"available); no pin table here"
        )
    raise KeyError(f"unknown tier {part.tier!r} for cell {part.cell!r}")


def input_pins(part: Part) -> tuple[str, ...]:
    """Input pin names for a cell, in a deterministic order."""
    return tuple(
        sorted(p for p, d in cell_pin_directions(part).items() if d == "input")
    )


def output_pins(part: Part) -> tuple[str, ...]:
    """Output pin names for a cell, in a deterministic order."""
    return tuple(
        sorted(p for p, d in cell_pin_directions(part).items() if d == "output")
    )
