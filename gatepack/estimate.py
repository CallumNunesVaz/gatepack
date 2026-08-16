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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

from gatepack import __version__
from gatepack.frontend.frontend import CompileResult, compile_design_file
from gatepack.frontend.model import CompiledDesign
from gatepack.liberty.generator import generate as generate_liberty
from gatepack.liberty.sim import generate as generate_sim
from gatepack.macros import load_models as load_m_cell_models
from gatepack.netlist import parse_mapped_json, resolve_parts
from gatepack.pack.packer import pack
from gatepack.parts import Part, load_parts
from gatepack.synth.base import SynthConfig
from gatepack.synth.synchronous import SynchronousBackend
from gatepack.toolchain import ToolchainRunner, yosys_command


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


@dataclass(frozen=True)
class OneHotInitCost:
    """The §6 cost of a one-hot initial state realised as set-via-feedback
    (M0-FINDINGS §6, option 2) instead of a set-capable flop."""

    mechanism: str
    nor_fanin: int
    nor_gate_upper_bound: int
    extra_or_inputs: int = 1


def one_hot_init_cost(compiled: CompiledDesign) -> OneHotInitCost | None:
    """Return the set-via-feedback cost, or ``None`` when the mechanism is unused.

    Only the one-hot encoding needs it, and a single state has a constant flop
    rather than a one-hot set (its ``set_feedback`` folds away).  The gate count
    is an *upper bound* assuming a tree of 2-input NOR gates; the real number is
    settled by mapping and reported in the package count when Yosys runs.
    """
    if compiled.encoding != "one_hot" or compiled.state_width <= 1:
        return None
    return OneHotInitCost(
        mechanism="set-via-feedback on a reset-to-0 flop (no set-capable part)",
        nor_fanin=compiled.state_width,
        nor_gate_upper_bound=compiled.state_width - 1,
    )


def run_estimate(
    design_path: str | Path,
    library_csv: str | Path,
    build_dir: str | Path = "build",
    thresholds: Thresholds | None = None,
    runner: ToolchainRunner | None = None,
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
    runner = runner or ToolchainRunner()
    yosys_ran = False
    if runner.available("yosys"):
        package_count = _run_yosys(runner, yosys_script, build_dir, parts)
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


def _run_yosys(
    runner: ToolchainRunner, script: str, build_dir: Path, parts: Sequence[Part]
) -> int | None:
    """Run Yosys and return the *packed* package count, or ``None`` on failure."""
    # No cwd override.  The script names its inputs as `str(build_dir / ...)`,
    # i.e. relative to the directory the CLI was invoked from — deliberately, so
    # that yosys.ys is reproducible and does not embed absolute paths.  The old
    # `cwd=build_dir.parent` was correct only for a single-segment build dir:
    # for `--build a/b/c` it made Yosys look for `a/b/a/b/c/generated.v`, fail,
    # and leave packageCount as a silent `None` beside a verdict computed
    # without it.
    result = runner.run(yosys_command(script), cwd=".")
    if result.returncode != 0:
        return None
    return _count_packages(build_dir / "mapped.json", parts)


def _count_packages(mapped_json: Path, parts: Sequence[Part]) -> int | None:
    """Pack the mapped netlist and return the physical package count.

    This is deliberately the same packer ``build`` runs, not an approximation of
    it: the §6 verdict classifies a number someone will plan a board around, so
    "green, ~18 packages" for a design that builds to 30 is worse than no
    verdict at all.  Any failure returns ``None`` (reported as unknown) rather
    than falling back to the gate count, which is the wrong number wearing the
    right label.
    """
    try:
        netlist = resolve_parts(parse_mapped_json(mapped_json.read_text()), list(parts))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if not netlist.cells:
        return 0
    try:
        return pack(netlist.cells, list(parts)).packed_stats.package_count
    except (KeyError, ValueError):
        return None


def _count_mapped_cells(mapped_json: Path) -> int | None:
    """The *gate* count — one per mapped cell.

    Kept because it is a distinct, meaningful quantity (and the two agree only
    for a one-gate-per-package library), but it is no longer what the package
    count metric reports.
    """
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
    one_hot_cost = one_hot_init_cost(compiled)
    manifest = {
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
    if one_hot_cost is not None:
        # §9.2-style explicit line item: the set-via-feedback initial state is
        # counted in the package count, never hidden inside it.
        manifest["one_hot_initial_state"] = {
            "mechanism": one_hot_cost.mechanism,
            "nor_fanin": one_hot_cost.nor_fanin,
            "nor_gate_upper_bound": one_hot_cost.nor_gate_upper_bound,
            "extra_or_inputs": one_hot_cost.extra_or_inputs,
        }
    return manifest


def _dump_json(data: dict) -> str:
    return json.dumps(data, indent=2, sort_keys=True) + "\n"
