"""Orchestration for ``gatepack verify`` (§17, §12 C4).

Runs the front-end (C1), Liberty + sim generation (C2), synthesis (C3, if Yosys
is present), then the C4 verification strategy plus the §9.5 S-cell checks, and
assembles a deterministic manifest.  Every check that needs a tool not present
here reports ``not run`` with an explicit reason — a result is never faked.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from gatepack import __version__
from gatepack.frontend.frontend import CompileResult, compile_design_file
from gatepack.frontend.model import CompiledDesign
from gatepack.infra import (
    SupervisorSpec,
    check_all_flops_reset_connected,
    check_supervisor,
    worst_flop_reset_recovery_ns,
)
from gatepack.liberty.generator import generate as generate_liberty
from gatepack.liberty.sim import generate as generate_sim
from gatepack.macros import load_models as load_m_cell_models
from gatepack.parts import Part, load_parts
from gatepack.synth.base import SynthConfig
from gatepack.synth.synchronous import SynchronousBackend
from gatepack.verify.base import (
    CheckResult,
    CheckStatus,
    SubprocessRunner,
    VerificationReport,
    VerifyConfig,
)
from gatepack.verify.synchronous import SynchronousVerify


@dataclass
class VerifyResult:
    report: VerificationReport
    compiled: CompiledDesign
    config: VerifyConfig
    manifest: dict
    yosys_script: str
    paths: dict[str, Path] = field(default_factory=dict)


def _strategy_check_result(
    name: str, status: CheckStatus, detail: str = "", bound: int | None = None
) -> CheckResult:
    return CheckResult(name=name, status=status, detail=detail, bound=bound)


def _infra_checks(
    compiled: CompiledDesign, parts: list[Part], verilog: str, vcc: float
) -> list[CheckResult]:
    checks: list[CheckResult] = []
    unreset = check_all_flops_reset_connected(verilog)
    if unreset:
        checks.append(
            CheckResult(
                "flop reset connectivity",
                CheckStatus.FAILED,
                "; ".join(unreset),
            )
        )
    else:
        checks.append(CheckResult("flop reset connectivity", CheckStatus.PASSED))

    if compiled.design.reset.source:
        findings = check_supervisor(
            SupervisorSpec(), vcc, worst_flop_reset_recovery_ns(parts)
        )
        if findings:
            checks.append(
                CheckResult("supervisor parameters", CheckStatus.FAILED, "; ".join(findings))
            )
        else:
            checks.append(CheckResult("supervisor parameters", CheckStatus.PASSED))
    return checks


def _manifest(
    compiled: CompiledDesign, report: VerificationReport
) -> dict:
    checks = []
    for check in report.checks:
        entry: dict = {"name": check.name, "status": check.status.value, "detail": check.detail}
        if check.bound is not None:
            entry["bound"] = check.bound
        checks.append(entry)
    mutations = [
        {"mutation": m.mutation, "detected": m.detected, "detail": m.detail}
        for m in report.mutations
    ]
    if report.has_failure:
        overall = "failed"
    elif report.has_not_run:
        overall = "not run"
    else:
        overall = "passed"
    return {
        "schema_version": 1,
        "tool": "gatepack",
        "tool_version": __version__,
        "design": compiled.design.name,
        "timing_model": compiled.design.timing_model,
        "verification": {
            "overall": overall,
            "checks": checks,
            "mutations": mutations,
        },
    }


def run_verify(
    design_path: str | Path,
    library_csv: str | Path,
    build_dir: str | Path = "build",
    runner: SubprocessRunner | None = None,
) -> VerifyResult:
    design_path = Path(design_path)
    build_dir = Path(build_dir)
    build_dir.mkdir(parents=True, exist_ok=True)

    compiled_result: CompileResult = compile_design_file(design_path)
    compiled = compiled_result.compiled

    parts = load_parts(library_csv)
    vcc = compiled.design.constraints.vcc
    liberty = generate_liberty(parts, library_name="gatepack", project_vcc=vcc)
    sim_text = generate_sim(parts, project_vcc=vcc) + "\n" + load_m_cell_models()

    generated_v = build_dir / "generated.v"
    properties_sv = build_dir / "properties.sv"
    cells_lib = build_dir / "cells.lib"
    cells_sim_v = build_dir / "cells_sim.v"
    premap_json = build_dir / "premap.json"
    mapped_json = build_dir / "mapped.json"
    mapped_v = build_dir / "mapped.v"
    golden_json = build_dir / "golden.json"
    testbench_v = build_dir / "exhaustive_tb.v"
    yosys_script_path = build_dir / "yosys.ys"

    generated_v.write_text(compiled_result.verilog)
    properties_sv.write_text(compiled_result.properties)
    cells_lib.write_text(liberty.text)
    cells_sim_v.write_text(sim_text)

    flop_cells = tuple(sorted(p.cell for p in parts if p.tier == "F" and p.cell in liberty.cells))
    synth_config = SynthConfig(
        top=compiled.design.name,
        generated_v=str(generated_v),
        cells_lib=str(cells_lib),
        premap_json=str(premap_json),
        mapped_json=str(mapped_json),
        mapped_v=str(mapped_v),
        flop_cells=flop_cells,
    )
    yosys_script = SynchronousBackend().generate_script(synth_config)
    yosys_script_path.write_text(yosys_script)

    runner = runner or SubprocessRunner()
    if runner.available("yosys"):
        runner.run(["yosys", "-p", yosys_script], cwd=str(build_dir.parent or "."))

    config = VerifyConfig(
        top=compiled.design.name,
        generated_v=str(generated_v),
        properties_sv=str(properties_sv),
        cells_lib=str(cells_lib),
        cells_sim_v=str(cells_sim_v),
        premap_json=str(premap_json),
        mapped_json=str(mapped_json),
        mapped_v=str(mapped_v),
        golden_json=str(golden_json),
        testbench_v=str(testbench_v),
        cwd=str(build_dir.parent or "."),
    )

    strategy = SynchronousVerify()
    report = strategy.verify(config, compiled, runner, liberty.text, sim_text)

    infra = _infra_checks(compiled, parts, compiled_result.verilog, vcc)
    report = VerificationReport(checks=report.checks + infra, mutations=report.mutations)

    manifest = _manifest(compiled, report)
    manifest_path = build_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    return VerifyResult(
        report=report,
        compiled=compiled,
        config=config,
        manifest=manifest,
        yosys_script=yosys_script,
        paths={
            "generated_v": generated_v,
            "properties_sv": properties_sv,
            "cells_lib": cells_lib,
            "cells_sim": cells_sim_v,
            "yosys_script": yosys_script_path,
            "manifest": manifest_path,
        },
    )
