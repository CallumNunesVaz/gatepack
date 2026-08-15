"""C2 — Liberty generator (§12 C2).  ``parts.csv`` -> Liberty text.

Emits ``cell`` blocks with ``area``, pin directions and ``function`` for G-cells,
and ``ff`` groups for F-cells following the §9.2 [R4-3] table exactly:

* ``DFF``    — ``next_state``, ``clocked_on``
* ``DFF_R``  — above + ``clear``
* ``DFF_S``  — above + ``preset``
* ``DFF_SR`` — above + ``clear`` and ``preset``, plus ``clear_preset_var1``/``var2``
  fixing set-vs-reset dominance to match ``$_DFFSR_*`` semantics (reset/clear
  dominates, so ``var1="L"``, ``var2="H"``).

Timing arcs (``tpd_ns``) and leakage (``iq_ua``) are carried in the data model but
are *not* emitted here; per [R4-11] they are primarily for the C7 delay report
and are a later milestone (see BUILD-NOTES).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from gatepack import parts as parts_mod
from gatepack.liberty import boolean
from gatepack.liberty.validate import LibertyError, validate_library
from gatepack.parts import Exclusion, Part

OUTPUT_PIN = "Y"

# Flop pin layout, clock and asynchronous control expressions, keyed by cell
# name.  The F-cell's `function` column is empty; the ff group is derived here.
_FLOP_SPECS: dict[str, dict[str, object]] = {
    "DFF": {"pins": ["D", "CK"], "clock": "CK", "next_state": "D"},
    "DFF_R": {
        "pins": ["D", "CK", "RST_N"],
        "clock": "CK",
        "next_state": "D",
        "clear": "!RST_N",
    },
    "DFF_S": {
        "pins": ["D", "CK", "SET_N"],
        "clock": "CK",
        "next_state": "D",
        "preset": "!SET_N",
    },
    "DFF_SR": {
        "pins": ["D", "CK", "SET_N", "RST_N"],
        "clock": "CK",
        "next_state": "D",
        "clear": "!RST_N",
        "preset": "!SET_N",
        "clear_preset_var1": "L",
        "clear_preset_var2": "H",
    },
}


@dataclass(frozen=True)
class LibraryResult:
    text: str
    cells: list[str]
    library_name: str
    excluded: list[Exclusion]


def flop_ff_requirements(
    specs: dict[str, dict[str, object]] | None = None,
) -> dict[str, set[str]]:
    """Derive the ``ff`` attributes each F-cell *must* carry, from ``_FLOP_SPECS``.

    This is the C2 self-check's independent view of §9.2 [R4-3]: the generator
    emits ``ff`` groups from the same spec, but the validator re-derives the
    requirement from the spec itself rather than trusting the emitter.  A
    generator bug that drops ``clear`` from ``DFF_R`` is therefore caught by the
    validator instead of silently shared (§19 R1).
    """
    specs = specs if specs is not None else _FLOP_SPECS
    out: dict[str, set[str]] = {}
    for cell, spec in specs.items():
        attrs = {"next_state", "clocked_on"}
        for key in ("clear", "preset", "clear_preset_var1", "clear_preset_var2"):
            if key in spec:
                attrs.add(key)
        out[cell] = attrs
    return out


def sanitize_library_name(name: str) -> str:
    """Return a Liberty-safe identifier for ``name`` (e.g. a CSV stem)."""
    name = name.strip()
    if not name:
        return "gatepack"
    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
        return name
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if not re.match(r"^[A-Za-z_]", cleaned):
        cleaned = "lib_" + cleaned
    return cleaned


def generate(
    parts: Sequence[Part],
    library_name: str = "gatepack",
    project_vcc: float = parts_mod.DEFAULT_VCC,
    allow_single_source: bool = False,
) -> LibraryResult:
    """Select eligible cells, emit the Liberty file, and self-check it."""
    included, excluded = parts_mod.select_for_liberty(
        parts, project_vcc=project_vcc, allow_single_source=allow_single_source
    )
    if not included:
        raise LibertyError("no cells eligible for the Liberty file")

    blocks = [_cell_block(part) for part in included]
    text = _library_text(library_name, blocks)

    cell_names = [p.cell for p in included]
    validate_library(
        text, cell_names, flop_requirements=flop_ff_requirements()
    )  # C2 self-check (R1)

    return LibraryResult(
        text=text, cells=cell_names, library_name=library_name, excluded=excluded
    )


def _cell_block(part: Part) -> str:
    if part.tier == "G":
        return _g_cell_block(part)
    if part.tier == "F":
        return _f_cell_block(part)
    raise LibertyError(f"{part.cell}: tier {part.tier!r} is not writable to Liberty")


def _g_cell_block(part: Part) -> str:
    if not part.function:
        raise LibertyError(f"{part.cell}: G-cell has no function")
    try:
        func = boolean.translate(part.function, part.inputs)
    except boolean.BooleanError as exc:
        raise LibertyError(f"{part.cell}: {exc}") from exc

    pins = boolean.pin_names(part.inputs)
    lines = [f"cell ({part.cell}) {{", f"  area : {part.area};"]
    for name in pins:
        lines.append(f"  pin({name}) {{")
        lines.append("    direction : input;")
        lines.append("    capacitance : 0.0;")
        lines.append("  }")
    lines.append(f"  pin({OUTPUT_PIN}) {{")
    lines.append("    direction : output;")
    lines.append(f'    function : "{func}";')
    lines.append("  }")
    lines.append("}")
    return "\n".join(lines)


def _f_cell_block(part: Part) -> str:
    spec = _FLOP_SPECS.get(part.cell)
    if spec is None:
        raise LibertyError(
            f"{part.cell}: unsupported F-cell "
            f"(supported: {sorted(_FLOP_SPECS)})"
        )
    pins = spec["pins"]  # type: list[str]
    if len(pins) != part.inputs:
        raise LibertyError(
            f"{part.cell}: inputs column is {part.inputs}, but the flop layout "
            f"requires {len(pins)} pins ({pins})"
        )

    lines = [f"cell ({part.cell}) {{", f"  area : {part.area};"]
    lines.append("  ff (IQ, IQN) {")
    lines.append(f'    next_state : "{spec["next_state"]}";')
    lines.append(f'    clocked_on : "{spec["clock"]}";')
    for key in ("clear", "preset"):
        if key in spec:
            lines.append(f'    {key} : "{spec[key]}";')
    if "clear_preset_var1" in spec:
        lines.append(f'    clear_preset_var1 : "{spec["clear_preset_var1"]}";')
        lines.append(f'    clear_preset_var2 : "{spec["clear_preset_var2"]}";')
    lines.append("  }")

    clock = spec["clock"]
    for name in pins:
        lines.append(f"  pin({name}) {{")
        lines.append("    direction : input;")
        if name == clock:
            lines.append("    clock : true;")
        lines.append("  }")
    lines.append("  pin(Q) {")
    lines.append("    direction : output;")
    lines.append('    function : "IQ";')
    lines.append("  }")
    lines.append("}")
    return "\n".join(lines)


def _library_text(library_name: str, blocks: Sequence[str]) -> str:
    lines = [
        "/* Generated by gatepack (C2). Electrical values are placeholders unless",
        "   verified against a datasheet; see the companion refs file. */",
        f"library ({library_name}) {{",
    ]
    for block in blocks:
        for line in block.splitlines():
            lines.append("  " + line)
    lines.append("}")
    lines.append("")
    return "\n".join(lines)
