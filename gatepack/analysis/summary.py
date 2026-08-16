"""`gatepack analyse` — standalone analysis over an existing build directory.

§17 lists ``gatepack analyse out/`` as a command whose job is "SCOAP + stuck-at,
standalone": run the §13.1 SCOAP and §13.2 stuck-at analyses over the mapped
netlist that a previous ``gatepack build`` already wrote to disk, without
re-running synthesis.  ``out/`` is self-describing for that purpose: ``build``
writes ``mapped.json`` (the resolved netlist), ``cells.lib`` (the generated
Liberty, which carries each G-cell's boolean function and each F-cell's pin
layout) and ``generated.v`` (for the §24.1 CPLD lint).

The payload is ``app/shared/api.ts``'s ``AnalysisSummary``.  Two builders exist:

* :func:`full_analysis_payload` — when a ``design.yaml`` and ``parts.csv`` are
  also supplied, re-run the exact C5..C7 assembly ``build`` performs (sharing
  ``gatepack.build.assemble``) so the summary is field-for-field identical to the
  ``analysis`` block of ``gatepack build --json``.
* :func:`dir_only_payload` — the §17 path (a directory, nothing else).  This is
  what the GUI calls.  It reconstructs the G/F parts from ``cells.lib`` and
  reports the measures that file can honestly support.

Degradation is explicit, never silent zeros:

* no ``mapped.json`` -> :class:`AnalysisUnavailableError` (an error envelope, not
  a summary full of zeros);
* no ``cells.lib`` -> the same, because SCOAP and stuck-at need each cell's
  boolean function.

``cells.lib`` carries the G/F functions but **not** ``gates_per_pkg``, ``iq_ua``
or ``tpd_ns`` — those live only in ``parts.csv``.  The dir-only path therefore
does **not** report package count, pack cost or static current.  Emitting those
from a reconstructed one-gate-per-package / zero-IQ assumption would be exactly
the fabricated number this project exists to prevent (a "green, ~18 packages"
verdict for a board that builds to 30).
"""

from __future__ import annotations

import re
from pathlib import Path

from gatepack.analysis.clock import flop_count, timing_analysis
from gatepack.analysis.cpld import lint_cpld
from gatepack.analysis.faults import analyze_faults
from gatepack.analysis.scoap import analyze_scoap
from gatepack.netlist import load_mapped_json, resolve_parts
from gatepack.parts import Part


class AnalysisUnavailableError(ValueError):
    """The directory cannot be analysed (missing mapped netlist or library)."""


# ---------------------------------------------------------------------------
# Liberty reconstruction
# ---------------------------------------------------------------------------

_CELL = re.compile(r"^\s*cell\s*\(\s*(\w+)\s*\)\s*\{", re.MULTILINE)
_AREA = re.compile(r"\barea\s*:\s*([0-9.eE+-]+)\s*;")
_PIN = re.compile(
    r"^\s*pin\s*\(\s*(\w+)\s*\)\s*\{"
    r"(?P<body>.*?)^\s*\}",
    re.MULTILINE | re.DOTALL,
)
_DIRECTION = re.compile(r"\bdirection\s*:\s*(input|output)\s*;")
_FUNCTION = re.compile(r'\bfunction\s*:\s*"([^"]*)"\s*;')
_FF_GROUP = re.compile(r"^\s*ff\s*\([^)]*\)\s*\{", re.MULTILINE)


def load_parts_from_liberty(liberty_text: str) -> list[Part]:
    """Reconstruct G/F :class:`Part` objects from a generated ``cells.lib``.

    The Liberty file carries cell name, ``area``, pin directions, the G-cell
    boolean ``function`` and the F-cell pin layout — enough to resolve the mapped
    netlist for SCOAP and stuck-at analysis.  The fields ``parts.csv`` owns
    (``gates_per_pkg``, ``iq_ua``, ``tpd_ns``, ``package``, ``mfrs``, ``vcc_*``)
    are not present and are left at honest placeholder values; callers must not
    use them to fabricate package-cost / static-current metrics.
    """
    parts: list[Part] = []
    for cell_match in _CELL.finditer(liberty_text):
        name = cell_match.group(1)
        block_start = cell_match.end()
        block = _cell_block_body(liberty_text, block_start)

        area_match = _AREA.search(block)
        area = float(area_match.group(1)) if area_match else 1.0

        is_ff = _FF_GROUP.search(block) is not None

        function: str | None = None
        inputs = 0
        for pin in _PIN.finditer(block):
            body = pin.group("body")
            if _DIRECTION.search(body) is None:
                continue
            direction = _DIRECTION.search(body).group(1)
            if direction == "input":
                inputs += 1
            else:
                func = _FUNCTION.search(body)
                if func is not None and func.group(1) != "IQ":
                    function = func.group(1)

        parts.append(
            Part(
                cell=name,
                tier="F" if is_ff else "G",
                family="",
                part_suffix="",
                equivalents=[],
                function=function,
                inputs=inputs,
                gates_per_pkg=1,
                package="",
                mfrs=[],
                vcc_min=0.0,
                vcc_max=0.0,
                area=area,
                tpd_ns=None,
                iq_ua=None,
            )
        )
    return parts


def _cell_block_body(text: str, start: int) -> str:
    """Return the ``{...}`` body of a ``cell`` block beginning at ``start``.

    Blocks nest (a ``pin`` group and an ``ff`` group sit inside the cell block),
    so a plain substring is not enough; track brace depth from ``start``.  The
    cell's own opening ``{`` was consumed by the regex, so depth starts at 1 and
    the cell's matching ``}`` is the first close that returns it to 0.
    """
    depth = 1
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i]
    return text[start:]


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def load_build_netlist(build_dir: str | Path) -> tuple:
    """Return ``(netlist, parts)`` resolved from a build directory's artefacts.

    Raises :class:`AnalysisUnavailableError` with an explicit reason when the
    netlist or the library is missing — never a fabricated empty result.
    """
    out = Path(build_dir)
    mapped = out / "mapped.json"
    cells_lib = out / "cells.lib"

    if not mapped.exists():
        raise AnalysisUnavailableError(
            f"no mapped netlist at {mapped}: run `gatepack build` first "
            "(an analysis is never reported as zeros when synthesis has not run)"
        )
    if not cells_lib.exists():
        raise AnalysisUnavailableError(
            f"no generated library at {cells_lib}: SCOAP and stuck-at analysis "
            "need each cell's boolean function, which only cells.lib carries"
        )

    netlist = load_mapped_json(mapped)
    parts = load_parts_from_liberty(cells_lib.read_text())
    resolved = resolve_parts(netlist, parts)
    return resolved, parts


def dir_only_payload(build_dir: str | Path) -> dict:
    """The §17 ``analyse <dir>`` summary: SCOAP + stuck-at + the honest metrics.

    Package count, pack cost and static current are deliberately absent — see the
    module docstring.  The faults analysis is run without a compiled design, so
    every primary input is treated as a data input (the documented approximation
    for sequential designs); clock/reset faults are still classified
    ``untestable``, not simulated.
    """
    netlist, _parts = load_build_netlist(build_dir)

    scoap = analyze_scoap(netlist)
    faults = analyze_faults(netlist, compiled=None)
    timing = timing_analysis(netlist)

    out = Path(build_dir)
    generated_v = out / "generated.v"
    verilog_text = generated_v.read_text() if generated_v.exists() else ""
    blockers = lint_cpld(verilog_text, netlist)

    return {
        "metrics": [
            _metric("flop count", flop_count(netlist), "flops", None),
            _metric("combinational depth", timing.combinational_depth, "levels", None),
        ],
        "scoap": scoap.to_wire(),
        "faults": faults.to_wire(),
        "cpldBlockers": [d.to_dict() for d in blockers],
    }


def full_analysis_payload(
    build_dir: str | Path,
    design_path: str | Path,
    library_csv: str | Path,
) -> dict:
    """The full summary, identical to ``build --json``'s ``analysis`` block.

    Re-runs the C5..C8 assembly against the existing ``mapped.json`` (sharing
    ``gatepack.build.assemble`` so the two can never drift).  Requires the design
    and library because package cost, static current and the exact flop count
    only exist there.
    """
    from gatepack import api as api_mod
    from gatepack.build import AssembleConfig, assemble, load_previous_refdes
    from gatepack.estimate import VccIncompatibleError, check_vcc_compatibility
    from gatepack.frontend.frontend import compile_design_file
    from gatepack.liberty.generator import generate as generate_liberty
    from gatepack.parts import load_parts

    out = Path(build_dir)
    mapped = out / "mapped.json"
    if not mapped.exists():
        raise AnalysisUnavailableError(
            f"no mapped netlist at {mapped}: run `gatepack build` first"
        )

    compiled_result = compile_design_file(design_path)
    compiled = compiled_result.compiled
    design = compiled.design

    parts = load_parts(library_csv)
    vcc = design.constraints.vcc
    vcc_errors = check_vcc_compatibility(compiled, parts, vcc)
    if vcc_errors:
        raise VccIncompatibleError("; ".join(vcc_errors))
    generate_liberty(parts, library_name="gatepack", project_vcc=vcc)

    netlist = load_mapped_json(mapped)

    config = AssembleConfig(
        design_name=design.name,
        force_groups=tuple(tuple(g) for g in design.packing.force_groups),
        timing_model=design.timing_model,
        freq_hz=design.clock.freq_hz if design.clock else None,
        vcc=vcc,
    )
    result = assemble(
        netlist,
        parts,
        config,
        previous_refdes=load_previous_refdes(out),
        verilog_text=compiled_result.verilog,
        compiled=compiled,
        build_dir=out,
    )
    return api_mod.analysis_summary(compiled, result, result.cpld_blockers)


def _metric(name: str, value, unit: str, limit) -> dict:
    violated = limit is not None and value is not None and value > limit
    return {
        "name": name,
        "value": value,
        "unit": unit,
        "limit": limit,
        "violated": violated,
    }


__all__ = [
    "AnalysisUnavailableError",
    "dir_only_payload",
    "full_analysis_payload",
    "load_build_netlist",
    "load_parts_from_liberty",
]
