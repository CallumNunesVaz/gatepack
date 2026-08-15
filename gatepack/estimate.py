"""`gatepack estimate` — the §6 viability verdict.

The verdict logic (:func:`assess`) is a pure function so it is unit-testable
without Yosys.  ``run_estimate`` runs the front-end, generates the C2 Liberty
file and the C3 Yosys script, and — only if Yosys is installed — executes it and
folds the mapped gate count into the package-count metric.  Metrics that need a
synthesis run (package count, combinational depth, static current) are reported
as ``None`` when Yosys is unavailable, never fabricated.

§6 thresholds (green/amber/red) and default bands:

* package count:      green <= 25, amber <= 50, red > 50
* flop count:         green <= 8,  amber <= 15, red > 15
* clock net fanout:   green <= 8,  amber <= 15, red > 15
* combinational depth: green <= 6, amber <= 10, red > 10
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from gatepack import __version__
from gatepack.frontend.frontend import CompileResult, compile_design_file
from gatepack.frontend.model import CompiledDesign
from gatepack.liberty.generator import generate as generate_liberty
from gatepack.liberty.sim import generate as generate_sim
from gatepack.macros import load_models as load_m_cell_models
from gatepack.parts import Part, load_parts
from gatepack.synth.base import SynthConfig
from gatepack.synth.synchronous import SynchronousBackend


class VccIncompatibleError(ValueError):
    """An M- or S-cell in the design cannot operate at the project VCC (§9.4 [R4-8])."""


def check_vcc_compatibility(
    compiled: CompiledDesign, parts: list[Part], vcc: float
) -> list[str]:
    """Return error strings for M-/S-cells whose supply range excludes ``vcc``."""
    by_cell = {p.cell: p for p in parts}
    errors: list[str] = []
    for macro in compiled.design.macros:
        part = by_cell.get(macro.cell)
        if part is not None and not part.vcc_compatible(vcc):
            errors.append(
                f"macro {macro.instance!r} uses {macro.cell!r} (supply "
                f"{part.vcc_min}..{part.vcc_max} V) which does not operate at "
                f"{vcc} V"
            )
    for name, cell in _s_cells(compiled):
        part = by_cell.get(cell)
        if part is not None and not part.vcc_compatible(vcc):
            errors.append(
                f"S-cell {name!r} ({cell}) supply {part.vcc_min}..{part.vcc_max} V "
                f"does not operate at {vcc} V"
            )
    return errors


def _s_cells(compiled: CompiledDesign) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    design = compiled.design
    if design.clock is not None and design.clock.source:
        out.append(("clock", design.clock.source))
    if design.reset.source:
        out.append(("reset", design.reset.source))
    return out


@dataclass(frozen=True)
class Thresholds:
    package_green: float = 25
    package_amber: float = 50
    flop_green: float = 8
    flop_amber: float = 15
    fanout_green: float = 8
    fanout_amber: float = 15
    depth_green: float = 6
    depth_amber: float = 10


@dataclass(frozen=True)
class Metric:
    value: float | None
    status: str  # "green" | "amber" | "red" | "unknown"


@dataclass(frozen=True)
class Verdict:
    overall: str  # "green" | "amber" | "red"
    metrics: Mapping[str, Metric]
    binding: str | None
    message: str


def _band(value: float | None, green_max: float, amber_max: float) -> str:
    if value is None:
        return "unknown"
    if value <= green_max:
        return "green"
    if value <= amber_max:
        return "amber"
    return "red"


def assess(
    package_count: float | None,
    flop_count: float | None,
    clock_fanout: float | None,
    depth: float | None,
    thresholds: Thresholds | None = None,
) -> Verdict:
    """Classify the four §6 metrics into a viability verdict."""
    t = thresholds or Thresholds()
    metrics: dict[str, Metric] = {
        "package count": Metric(package_count, _band(package_count, t.package_green, t.package_amber)),
        "flop count": Metric(flop_count, _band(flop_count, t.flop_green, t.flop_amber)),
        "clock net fanout": Metric(clock_fanout, _band(clock_fanout, t.fanout_green, t.fanout_amber)),
        "combinational depth": Metric(depth, _band(depth, t.depth_green, t.depth_amber)),
    }

    reds = [name for name, m in metrics.items() if m.status == "red"]
    ambers = [name for name, m in metrics.items() if m.status == "amber"]
    if reds:
        overall = "red"
        binding = reds[0]
        message = (
            f"recommend against discrete implementation: binding metric "
            f"{binding!r} ({_fmt(metrics[binding].value)}). Consider a flash CPLD "
            f"such as MAX V driven by portable inferred Verilog, or a mixed-signal "
            f"PLD where the design is supervisory (§6)."
        )
    elif ambers:
        overall = "amber"
        binding = ambers[0]
        message = (
            f"marginal: {', '.join(ambers)} are in the amber band. Consider "
            f"input-space collapse (§6.1) and re-measure before committing."
        )
    else:
        overall = "green"
        binding = None
        message = "discrete implementation is viable within all §6 thresholds."

    return Verdict(overall=overall, metrics=metrics, binding=binding, message=message)


def _fmt(value: float | None) -> str:
    return "unknown" if value is None else f"{value:g}"


@dataclass
class EstimateResult:
    verdict: Verdict
    compiled: CompiledDesign
    manifest: dict
    yosys_script: str
    yosys_ran: bool = False
    paths: dict[str, Path] = field(default_factory=dict)


def frontend_metrics(compiled: CompiledDesign) -> dict[str, float | None]:
    """Metrics computable without synthesis (flop count + clock fanout)."""
    return {
        "package_count": None,
        "flop_count": float(compiled.flop_count),
        "clock_fanout": float(compiled.clock_fanout),
        "depth": None,
    }


def run_estimate(
    design_path: str | Path,
    library_csv: str | Path,
    build_dir: str | Path = "build",
    thresholds: Thresholds | None = None,
) -> EstimateResult:
    design_path = Path(design_path)
    build_dir = Path(build_dir)
    build_dir.mkdir(parents=True, exist_ok=True)

    compiled_result: CompileResult = compile_design_file(design_path)
    compiled = compiled_result.compiled

    parts = load_parts(library_csv)
    vcc = compiled.design.constraints.vcc
    vcc_errors = check_vcc_compatibility(compiled, parts, vcc)
    if vcc_errors:
        raise VccIncompatibleError("; ".join(vcc_errors))
    liberty = generate_liberty(parts, library_name="gatepack", project_vcc=vcc)
    cells_sim = generate_sim(parts, project_vcc=vcc) + "\n" + load_m_cell_models()

    generated_v = build_dir / "generated.v"
    properties_sv = build_dir / "properties.sv"
    cells_lib = build_dir / "cells.lib"
    cells_sim_v = build_dir / "cells_sim.v"
    yosys_script_path = build_dir / "yosys.ys"
    mapped_json = build_dir / "mapped.json"
    mapped_v = build_dir / "mapped.v"
    premap_json = build_dir / "premap.json"
    manifest_path = build_dir / "manifest.json"

    generated_v.write_text(compiled_result.verilog)
    properties_sv.write_text(compiled_result.properties)
    cells_lib.write_text(liberty.text)
    cells_sim_v.write_text(cells_sim)

    flop_cells = tuple(sorted(p.cell for p in parts if p.tier == "F" and p.cell in liberty.cells))
    config = SynthConfig(
        top=compiled.design.name,
        generated_v=str(generated_v),
        cells_lib=str(cells_lib),
        premap_json=str(premap_json),
        mapped_json=str(mapped_json),
        mapped_v=str(mapped_v),
        flop_cells=flop_cells,
    )
    yosys_script = SynchronousBackend().generate_script(config)
    yosys_script_path.write_text(yosys_script)

    metrics = frontend_metrics(compiled)
    yosys_ran = False
    if shutil.which("yosys"):
        package_count = _run_yosys(yosys_script, build_dir)
        if package_count is not None:
            metrics["package_count"] = float(package_count)
            yosys_ran = True

    verdict = assess(
        metrics["package_count"],
        metrics["flop_count"],
        metrics["clock_fanout"],
        metrics["depth"],
        thresholds,
    )

    manifest = _manifest(compiled, verdict, metrics, yosys_ran)
    manifest_path.write_text(_dump_json(manifest))

    return EstimateResult(
        verdict=verdict,
        compiled=compiled,
        manifest=manifest,
        yosys_script=yosys_script,
        yosys_ran=yosys_ran,
        paths={
            "generated_v": generated_v,
            "properties_sv": properties_sv,
            "cells_lib": cells_lib,
            "cells_sim": cells_sim_v,
            "yosys_script": yosys_script_path,
            "manifest": manifest_path,
        },
    )


def _run_yosys(script: str, build_dir: Path) -> int | None:
    """Run Yosys and return the mapped cell count, or ``None`` on any failure."""
    try:
        proc = subprocess.run(
            ["yosys", "-p", script],
            cwd=str(build_dir.parent or "."),
            capture_output=True,
            text=True,
            timeout=600,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return _count_mapped_cells(build_dir / "mapped.json")


def _count_mapped_cells(mapped_json: Path) -> int | None:
    try:
        data = json.loads(mapped_json.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    count = 0
    for module in data.get("modules", {}).values():
        cells = module.get("cells", {})
        for cell in cells.values():
            if cell.get("type", "").startswith("$"):
                continue
            count += 1
    return count


def _manifest(
    compiled: CompiledDesign,
    verdict: Verdict,
    metrics: Mapping[str, float | None],
    yosys_ran: bool,
) -> dict:
    metric_blocks = {
        name: {"value": metrics.get(key), "status": verdict.metrics[name].status}
        for name, key in [
            ("package count", "package_count"),
            ("flop count", "flop_count"),
            ("clock net fanout", "clock_fanout"),
            ("combinational depth", "depth"),
        ]
    }
    return {
        "schema_version": 1,
        "tool": "gatepack",
        "tool_version": __version__,
        "design": compiled.design.name,
        "timing_model": compiled.design.timing_model,
        "encoding": compiled.design.encoding,
        "yosys": "ran" if yosys_ran else "unavailable",
        "verdict": {
            "overall": verdict.overall,
            "binding": verdict.binding,
            "message": verdict.message,
            "metrics": metric_blocks,
        },
    }


def _dump_json(data: dict) -> str:
    return json.dumps(data, indent=2, sort_keys=True) + "\n"
