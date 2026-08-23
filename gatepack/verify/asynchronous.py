"""AsynchronousVerify — independent hazard verification (stage 5, §7.3).

The asynchronous verification strategy runs the two independent hazard checks
over the *mapped netlist* (the actual output): the ternary simulation (5a) and
the Icarus glitch simulation (5b).  The check itself lives in
:mod:`gatepack.verify.hazard`, which imports nothing from the synthesis stages.

The strategy re-derives the flow table and the single-variable-change assignment
from the compiled spec (they are deterministic functions of the spec), then
enumerates the fundamental-mode transition probes itself.  The one hard rule of
the package applies: a netlist that fails either check is refused — the check
results are honest ``FAILED`` checks, and the caller must not emit.
"""

from __future__ import annotations

import re
from pathlib import Path

from gatepack.frontend.model import CompiledDesign
from gatepack.netlist import MappedNetlist, parse_mapped_json
from gatepack.synth.async_.assign import Assignment
from gatepack.synth.async_.flowtable import FlowTable
from gatepack.verify import hazard
from gatepack.verify.base import (
    CheckResult,
    CheckStatus,
    ToolRunner,
    VerificationReport,
    VerificationStrategy,
    VerifyConfig,
)
from gatepack.toolchain import iverilog_command, vvp_command


def cell_functions_from_liberty(lib_text: str) -> dict[str, str]:
    """Extract the G-cell ``function`` strings from a Liberty file.

    The asynchronous netlist is mapped to the same G-cells the Liberty file
    describes (INV/AND2/OR2/…), so the function table the hazard checker needs is
    read from the actual library, not hard-coded.  F-cells' ``function`` values
    (``IQ``/``IQN``, the state-variable reference on the ``Q`` pin) are not
    boolean expressions over ``A``/``B``/``C`` and are excluded, because the
    asynchronous netlist never instantiates an F-cell and the hazard checker
    cannot evaluate a state variable.
    """
    pattern = re.compile(
        r'cell\s*\(\s*(\w+)\s*\)\s*\{.*?function\s*:\s*"([^"]+)"', re.DOTALL
    )
    return {
        cell: func
        for cell, func in pattern.findall(lib_text)
        if func not in ("IQ", "IQN")
    }


def build_transition_probes(
    table: FlowTable, assignment: Assignment
) -> list[hazard.TransitionProbe]:
    """The fundamental-mode transition probes: every single-input change from a
    stable total state, with the state bits held at their source values."""
    probes: list[hazard.TransitionProbe] = []
    for si, state in enumerate(table.states):
        for ci, combo in enumerate(table.combos):
            if table.next_state[si][ci] != state:
                continue  # only a settled (stable) total state starts a transition
            for d in range(len(table.input_names)):
                stable = {
                    name: combo[k]
                    for k, name in enumerate(table.input_names)
                    if k != d
                }
                fixed = {
                    f"s_{j}": assignment.bit(state, j) for j in range(assignment.width)
                }
                probes.append(
                    hazard.TransitionProbe(
                        changing_input=table.input_names[d],
                        stable_inputs=stable,
                        fixed_nets=fixed,
                        from_value=combo[d],
                    )
                )
    return probes


class AsynchronousVerify(VerificationStrategy):
    """Runs stage 5a (ternary) and stage 5b (Icarus glitch) over the mapped netlist."""

    def verify(
        self,
        config: VerifyConfig,
        compiled: CompiledDesign,
        runner: ToolRunner,
        lib_text: str,
        sim_text: str,
    ) -> VerificationReport:
        mapped_path = Path(config.mapped_json)
        if not mapped_path.exists():
            return VerificationReport(
                checks=[
                    CheckResult(
                        "hazard (ternary)",
                        CheckStatus.NOT_RUN,
                        f"no mapped netlist at {mapped_path} (synthesis not run)",
                        kind="hazard",
                    )
                ]
            )

        netlist = parse_mapped_json(mapped_path.read_text())
        cell_functions = cell_functions_from_liberty(lib_text)
        return self.verify_netlist(netlist, cell_functions, compiled, runner, config)

    def verify_netlist(
        self,
        netlist: MappedNetlist,
        cell_functions: dict[str, str],
        compiled: CompiledDesign,
        runner: ToolRunner,
        config: VerifyConfig,
    ) -> VerificationReport:
        """Run both hazard checks against a parsed mapped netlist."""
        from gatepack.synth.async_ import assign_state_codes, build_flow_table

        table = build_flow_table(compiled)
        assignment = assign_state_codes(
            table,
            runner,
            workdir=str(Path(config.mapped_json).parent),
            design_name=compiled.design.name,
        )
        probes = build_transition_probes(table, assignment)
        checks = [
            self._ternary_check(netlist, cell_functions, probes),
            self._glitch_check(
                netlist, cell_functions, probes, runner, config
            ),
        ]
        return VerificationReport(checks=checks)

    def _ternary_check(
        self,
        netlist: MappedNetlist,
        cell_functions: dict[str, str],
        probes: list[hazard.TransitionProbe],
    ) -> CheckResult:
        findings = hazard.check_static_hazards(netlist, cell_functions, probes)
        if findings:
            detail = "; ".join(
                f"{f.output} ({f.kind}, changing {f.changing_input})" for f in findings
            )
            return CheckResult(
                "hazard (ternary)",
                CheckStatus.FAILED,
                "potential static hazard: " + detail,
                kind="hazard",
            )
        return CheckResult(
            "hazard (ternary)",
            CheckStatus.PASSED,
            f"{len(probes)} fundamental-mode transition(s) checked, no potential "
            "static hazard",
            kind="hazard",
        )

    def _glitch_check(
        self,
        netlist: MappedNetlist,
        cell_functions: dict[str, str],
        probes: list[hazard.TransitionProbe],
        runner: ToolRunner,
        config: VerifyConfig,
    ) -> CheckResult:
        if not runner.available("iverilog"):
            return CheckResult(
                "hazard (glitch sim)",
                CheckStatus.NOT_RUN,
                "iverilog not installed (Icarus — glitch simulation)",
                kind="hazard",
            )
        top = netlist.top
        inputs = list(netlist.inputs)
        outputs = list(netlist.outputs)

        scratch = Path(config.mapped_v).parent
        scratch.mkdir(parents=True, exist_ok=True)
        cells_path = scratch / "async_unit_delay_cells.v"
        tb_path = scratch / "async_glitch_tb.v"
        vvp = str(scratch / "async_glitch.vvp")

        failures: list[str] = []
        for seed in range(3):
            cells_path.write_text(hazard.unit_delay_cells(cell_functions, seed=seed))
            tb_path.write_text(
                hazard.build_glitch_testbench(top, inputs, outputs, probes)
            )
            compile_result = runner.run(
                iverilog_command(
                    vvp, [config.mapped_v, str(cells_path), str(tb_path)]
                ),
                cwd=config.cwd,
            )
            if compile_result.returncode != 0:
                return CheckResult(
                    "hazard (glitch sim)",
                    CheckStatus.NOT_RUN,
                    "iverilog compile failed: "
                    + (compile_result.stderr or "").strip(),
                    kind="hazard",
                )
            run_result = runner.run(vvp_command(vvp), cwd=config.cwd)
            if "GLITCH_FAIL" in run_result.stdout or "STABLE_FAIL" in run_result.stdout:
                failures.append(f"seed {seed}: " + _glitch_detail(run_result.stdout))
            elif "GLITCH_PASS" not in run_result.stdout:
                return CheckResult(
                    "hazard (glitch sim)",
                    CheckStatus.NOT_RUN,
                    "unrecognized glitch-simulation output",
                    kind="hazard",
                )

        if failures:
            return CheckResult(
                "hazard (glitch sim)",
                CheckStatus.FAILED,
                "; ".join(failures),
                kind="hazard",
            )
        return CheckResult(
            "hazard (glitch sim)",
            CheckStatus.PASSED,
            "no output glitch observed across 3 delay-perturbation seeds",
            kind="hazard",
        )


def _glitch_detail(stdout: str) -> str:
    for line in stdout.splitlines():
        if "GLITCH" in line or "STABLE_FAIL" in line:
            return line.strip()
    return "glitch observed"
