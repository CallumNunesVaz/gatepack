"""`gatepack build` orchestration (C5 packer + C6 emitters + C7 analysis + C8 report).

The heavy lifting is :func:`assemble`, a pure function from a resolved mapped
netlist to every downstream artefact (BOM, KiCad netlist, report, refdes map).
That keeps the whole M9/M10 pipeline unit-testable without Yosys: only the
*mapped netlist* is a Yosys product, and :func:`run_build` obtains it either
from an explicit ``--mapped`` JSON or by running Yosys when it is installed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

from gatepack.analysis.clock import timing_analysis
from gatepack.analysis.cpld import lint_cpld
from gatepack.analysis.faults import FaultReport, analyze_faults
from gatepack.analysis.power import (
    DynamicCurrent,
    StaticCurrent,
    dynamic_current_ua,
    spare_leakage_ua,
    static_current_by_tier,
)
from gatepack.analysis.scoap import ScoapReport, analyze_scoap
from gatepack.diagnostic import Diagnostic
from gatepack.emit.bom import collect_bom, emit_bom
from gatepack.emit.kicad import emit_netlist
from gatepack.emit.refdes import (
    RefdesDelta,
    assign_refdes,
    refdes_delta,
    refdes_map,
)
from gatepack.frontend.model import CompiledDesign
from gatepack.netlist import MappedNetlist, resolve_parts, stable_cell_names
from gatepack.pack.packer import (
    DEFAULT_SPARE_LEAKAGE_WEIGHT,
    PackerConfig,
    PackingStats,
    pack,
)
from gatepack.parts import Part
from gatepack.report.report import ReportInputs, emit_report


@dataclass(frozen=True)
class AssembleConfig:
    design_name: str = "design"
    timing_model: str = "synchronous"
    spare_leakage_weight: float = DEFAULT_SPARE_LEAKAGE_WEIGHT
    force_groups: tuple[tuple[str, ...], ...] = ()
    freq_hz: float | None = None
    vcc: float = 3.3


@dataclass
class BuildResult:
    bom: str
    netlist_text: str
    unpacked_netlist_text: str
    report: str
    refdes: dict[str, str]
    refdes_delta: RefdesDelta
    packed_stats: PackingStats
    unpacked_stats: PackingStats
    static_current: StaticCurrent
    dynamic_current: DynamicCurrent | None
    timing: TimingReport
    packages: list = field(default_factory=list)
    # Extra context carried for the ``--json`` payload and the report: the
    # resolved package/refdes list, the compiled design, the behavioural Verilog
    # text, the resolved netlist, and the §24.1 CPLD blocker lint result.
    assigned: list = field(default_factory=list)
    compiled: CompiledDesign | None = None
    verilog: str | None = None
    netlist: MappedNetlist | None = None
    scoap: ScoapReport | None = None
    faults: FaultReport | None = None
    cpld_blockers: list[Diagnostic] = field(default_factory=list)


def assemble(
    netlist: MappedNetlist,
    parts: Sequence[Part],
    config: AssembleConfig | None = None,
    previous_refdes: Mapping[str, str] | None = None,
    verilog_text: str | None = None,
    compiled: CompiledDesign | None = None,
) -> BuildResult:
    """Run C5 -> C6 -> C7 -> C8 on a resolved mapped netlist."""
    cfg = config or AssembleConfig()
    netlist = resolve_parts(netlist, parts)
    resolved_cells = [c for c in netlist.cells if c.part is not None]
    dropped = [c.name for c in netlist.cells if c.part is None]
    netlist = MappedNetlist(
        top=netlist.top,
        cells=tuple(resolved_cells),
        inputs=netlist.inputs,
        outputs=netlist.outputs,
    )
    names = stable_cell_names(netlist)

    packed = pack(
        netlist.cells,
        parts,
        PackerConfig(
            spare_leakage_weight=cfg.spare_leakage_weight,
            force_groups=cfg.force_groups,
        ),
        stable_names=names,
    )

    assigned = assign_refdes(packed.packed)
    current = refdes_map(assigned)
    delta = refdes_delta(dict(previous_refdes or {}), current)

    bom = emit_bom(assigned)
    net_text = emit_netlist(netlist, assigned, names)
    unpacked_assigned = assign_refdes(packed.unpacked)
    unpacked_net_text = emit_netlist(netlist, unpacked_assigned, names)

    static = static_current_by_tier(netlist.cells)
    spare_ua = spare_leakage_ua(packed.packed)
    dynamic = (
        dynamic_current_ua(netlist, cfg.freq_hz, cfg.vcc)
        if cfg.freq_hz is not None
        else None
    )
    timing = timing_analysis(netlist)
    cpld_blockers = lint_cpld(verilog_text or "", netlist)

    scoap = analyze_scoap(netlist)
    faults = analyze_faults(netlist, compiled)

    report = emit_report(
        ReportInputs(
            design=cfg.design_name,
            timing_model=cfg.timing_model,
            packed_stats=packed.packed_stats,
            unpacked_stats=packed.unpacked_stats,
            packed_bom=collect_bom(assigned),
            static_current=static,
            spare_leakage_ua=spare_ua,
            dynamic_current=dynamic,
            timing=timing,
            refdes_delta=delta,
            packages=[(ref, g.rationale) for ref, g in assigned],
            notes=_build_notes(cfg, dropped),
            cpld_blockers=cpld_blockers,
            scoap=scoap,
            faults=faults,
        )
    )

    return BuildResult(
        bom=bom,
        netlist_text=net_text,
        unpacked_netlist_text=unpacked_net_text,
        report=report,
        refdes=current,
        refdes_delta=delta,
        packed_stats=packed.packed_stats,
        unpacked_stats=packed.unpacked_stats,
        static_current=static,
        dynamic_current=dynamic,
        timing=timing,
        packages=list(packed.packed),
        assigned=list(assigned),
        netlist=netlist,
        scoap=scoap,
        faults=faults,
        cpld_blockers=cpld_blockers,
    )


def _build_notes(cfg: AssembleConfig, dropped: Sequence[str]) -> list[str]:
    notes = [
        "Packing is advisory (§12 C5): sharing a package forces physical "
        "adjacency; overrides persist in design.yaml.",
        f"Pack cost uses spare_leakage_weight = {cfg.spare_leakage_weight:g} "
        "in the same units as package area (§9.7).",
        "Dynamic current excludes inter-package routing capacitance and is not "
        "a budget.",
        "tPD excludes PCB parasitics and is not STA.",
        "Static current is the sum of the placeholder IQ values in parts.csv; "
        "no temperature derating is applied (the data model has no derating curve).",
        "Pin numbers in the netlist are assigned deterministically; real "
        "footprint pin numbers need footprint data (parts.csv has none).",
    ]
    if dropped:
        notes.append(
            f"{len(dropped)} mapped cell(s) had no library part and were "
            f"excluded from packing/analysis: {', '.join(sorted(dropped))}"
        )
    return notes


def write_build(out_dir: str | Path, result: BuildResult, previous_refdes: Mapping[str, str] | None = None) -> dict[str, Path]:
    """Write the build artefacts to ``out_dir`` and return their paths."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "bom": out / "bom.csv",
        "netlist": out / "netlist.net",
        "unpacked_netlist": out / "netlist.unpacked.net",
        "report": out / "report.md",
        "refdes": out / "refdes.json",
    }
    paths["bom"].write_text(result.bom)
    paths["netlist"].write_text(result.netlist_text)
    paths["unpacked_netlist"].write_text(result.unpacked_netlist_text)
    paths["report"].write_text(result.report)
    paths["refdes"].write_text(json.dumps(result.refdes, indent=2, sort_keys=True) + "\n")
    return paths


def load_previous_refdes(out_dir: str | Path) -> dict[str, str]:
    path = Path(out_dir) / "refdes.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def run_build(
    design_path: str | Path,
    library_csv: str | Path,
    out_dir: str | Path = "out",
    mapped_json: str | Path | None = None,
    spare_leakage_weight: float | None = None,
) -> tuple[BuildResult, dict[str, Path]]:
    """Full ``gatepack build``: front-end -> Liberty -> (Yosys|--mapped) -> C5..C8.

    Yosys is only invoked when no ``mapped_json`` is supplied and ``yosys`` is on
    ``PATH``; otherwise the mapped netlist is required.
    """
    from gatepack.frontend.frontend import compile_design_file
    from gatepack.liberty.generator import generate as generate_liberty
    from gatepack.netlist import load_mapped_json
    from gatepack.parts import load_parts
    from gatepack.estimate import check_vcc_compatibility, VccIncompatibleError

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    compiled_result = compile_design_file(design_path)
    compiled = compiled_result.compiled
    design = compiled.design

    parts = load_parts(library_csv)
    vcc = design.constraints.vcc
    vcc_errors = check_vcc_compatibility(compiled, parts, vcc)
    if vcc_errors:
        raise VccIncompatibleError("; ".join(vcc_errors))
    generate_liberty(parts, library_name="gatepack", project_vcc=vcc)

    (out / "generated.v").write_text(compiled_result.verilog)
    (out / "properties.sv").write_text(compiled_result.properties)

    if mapped_json is not None:
        netlist = load_mapped_json(mapped_json)
    else:
        netlist = _synthesize(compiled, parts, out)
        if netlist is None:
            raise RuntimeError(
                "synthesis unavailable: provide --mapped <mapped.json> or "
                "install yosys (never faked here)"
            )

    weight = spare_leakage_weight if spare_leakage_weight is not None else DEFAULT_SPARE_LEAKAGE_WEIGHT
    config = AssembleConfig(
        design_name=design.name,
        timing_model=design.timing_model,
        spare_leakage_weight=weight,
        freq_hz=design.clock.freq_hz if design.clock else None,
        vcc=vcc,
    )
    previous = load_previous_refdes(out)
    result = assemble(
        netlist,
        parts,
        config,
        previous,
        verilog_text=compiled_result.verilog,
        compiled=compiled,
    )
    result.compiled = compiled
    result.verilog = compiled_result.verilog
    paths = write_build(out, result, previous)
    return result, paths


def _synthesize(compiled, parts, out: Path) -> MappedNetlist | None:
    """Run Yosys if available and return the mapped netlist, else ``None``."""
    import shutil
    import subprocess

    from gatepack.liberty.generator import generate as generate_liberty
    from gatepack.netlist import load_mapped_json
    from gatepack.synth.base import SynthConfig
    from gatepack.synth.synchronous import SynchronousBackend

    if not shutil.which("yosys"):
        return None

    vcc = compiled.design.constraints.vcc
    liberty = generate_liberty(parts, library_name="gatepack", project_vcc=vcc)
    cells_lib = out / "cells.lib"
    cells_lib.write_text(liberty.text)
    premap = out / "premap.json"
    mapped = out / "mapped.json"
    mapped_v = out / "mapped.v"
    flop_cells = tuple(sorted(p.cell for p in parts if p.tier == "F" and p.cell in liberty.cells))
    script = SynchronousBackend().generate_script(
        SynthConfig(
            top=compiled.design.name,
            generated_v=str(out / "generated.v"),
            cells_lib=str(cells_lib),
            premap_json=str(premap),
            mapped_json=str(mapped),
            mapped_v=str(mapped_v),
            flop_cells=flop_cells,
        )
    )
    (out / "yosys.ys").write_text(script)
    try:
        proc = subprocess.run(
            ["yosys", "-p", script],
            cwd=str(out.parent or "."),
            capture_output=True,
            text=True,
            timeout=600,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not mapped.exists():
        return None
    return load_mapped_json(mapped)

