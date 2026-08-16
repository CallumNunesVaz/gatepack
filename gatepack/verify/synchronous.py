"""SynchronousVerify (§12 C4, §7) — equivalence + exhaustive sim + mutation.

The primary equivalence method is k-induction (``equiv_induct``); the fallback
ladder (``equiv_simple`` -> ``equiv_induct -seq N`` raised -> sby BMC miter) is
exposed for escalation.  Every check that needs a real binary reports
``NOT_RUN`` with an explicit reason naming the missing tool; nothing here fakes
a result.
"""

from __future__ import annotations

from pathlib import Path

from gatepack.frontend.model import CompiledDesign
from gatepack.toolchain import yosys_command
from gatepack.verify import equivalence as equiv_mod
from gatepack.verify import mutation as mutation_mod
from gatepack.verify import simulation as sim_mod
from gatepack.verify.base import (
    CheckResult,
    CheckStatus,
    ToolRunner,
    VerificationReport,
    VerificationStrategy,
    VerifyConfig,
)


class SynchronousVerify(VerificationStrategy):
    def verify(
        self,
        config: VerifyConfig,
        compiled: CompiledDesign,
        runner: ToolRunner,
        lib_text: str,
        sim_text: str,
    ) -> VerificationReport:
        checks = [
            self._equivalence(config, runner, len(compiled.state_order)),
            self._simulation(config, compiled, runner),
        ]
        mutation_check, mutations = self._mutation(config, compiled, runner, lib_text, sim_text)
        checks.append(mutation_check)
        return VerificationReport(checks=checks, mutations=mutations)

    # -- equivalence ----------------------------------------------------------

    def _equivalence(self, config: VerifyConfig, runner: ToolRunner, state_count: int) -> CheckResult:
        if not runner.available("yosys"):
            return CheckResult(
                "equivalence", CheckStatus.NOT_RUN, "yosys not installed", kind="equivalence"
            )
        # Primary run: the measured M0 recipe (equiv_simple + equiv_induct, bare).
        script = equiv_mod.build_equivalence_script(config)
        result = runner.run(yosys_command(script), cwd=config.cwd)
        if result.returncode != 0:
            return CheckResult(
                "equivalence",
                CheckStatus.FAILED,
                (result.stderr or result.stdout or "yosys failed").strip(),
                kind="equivalence",
            )
        outcome = equiv_mod.parse_equiv_status(result.stdout)
        return CheckResult(
            "equivalence", outcome.status, outcome.detail, outcome.bound, kind="equivalence"
        )

    # -- exhaustive simulation ------------------------------------------------

    def _simulation(self, config: VerifyConfig, compiled: CompiledDesign, runner: ToolRunner) -> CheckResult:
        decision = sim_mod.decide(
            len(compiled.input_names), len(compiled.state_order), config.exhaustive_cap
        )
        if decision.status is CheckStatus.NOT_APPLICABLE:
            return CheckResult(
                "exhaustive simulation", decision.status, decision.detail, kind="simulation"
            )
        if not runner.available("iverilog"):
            return CheckResult(
                "exhaustive simulation",
                CheckStatus.NOT_RUN,
                "iverilog not installed",
                kind="simulation",
            )

        tb = sim_mod.build_testbench(compiled, config)
        Path(config.testbench_v).parent.mkdir(parents=True, exist_ok=True)
        Path(config.testbench_v).write_text(tb)
        vvp = str(Path(config.testbench_v).with_suffix(".vvp"))
        compile_result = runner.run(sim_mod.build_compile_command(config, vvp), cwd=config.cwd)
        if compile_result.returncode != 0:
            return CheckResult(
                "exhaustive simulation",
                CheckStatus.FAILED,
                (compile_result.stderr or "iverilog compile failed").strip(),
                kind="simulation",
            )
        run_result = runner.run(sim_mod.build_run_command(vvp), cwd=config.cwd)
        outcome = sim_mod.parse_run(run_result.stdout)
        return CheckResult(
            "exhaustive simulation", outcome.status, outcome.detail, kind="simulation"
        )

    # -- mutation -------------------------------------------------------------

    def _mutation(
        self,
        config: VerifyConfig,
        compiled: CompiledDesign,
        runner: ToolRunner,
        lib_text: str,
        sim_text: str,
    ) -> tuple[CheckResult, list]:
        from gatepack.verify.base import MutationOutcome

        if not (runner.available("yosys") and runner.available("iverilog")):
            return (
                CheckResult(
                    "mutation",
                    CheckStatus.NOT_RUN,
                    "yosys + iverilog required",
                    kind="mutation",
                ),
                [],
            )

        def run_equivalence(mutated_sim: str) -> CheckStatus:
            # Both checks read cells_sim.v as the behavioural model, so the
            # mutated model (not the Liberty file) is what a correct check must
            # see.  Writing the mutated Liberty would change nothing: the
            # equivalence script never reads cells.lib.
            sim_path = Path(config.cells_sim_v)
            original = sim_path.read_text()
            sim_path.write_text(mutated_sim)
            try:
                result = runner.run(
                    yosys_command(equiv_mod.build_equivalence_script(config)),
                    cwd=config.cwd,
                )
                if result.returncode != 0:
                    return CheckStatus.FAILED
                return equiv_mod.parse_equiv_status(result.stdout).status
            finally:
                sim_path.write_text(original)

        def run_simulation(mutated_sim: str) -> CheckStatus:
            sim_path = Path(config.cells_sim_v)
            original = sim_path.read_text()
            sim_path.write_text(mutated_sim)
            try:
                tb = sim_mod.build_testbench(compiled, config)
                Path(config.testbench_v).parent.mkdir(parents=True, exist_ok=True)
                Path(config.testbench_v).write_text(tb)
                vvp = str(Path(config.testbench_v).with_suffix(".vvp"))
                compiled_ok = runner.run(
                    sim_mod.build_compile_command(config, vvp), cwd=config.cwd
                )
                if compiled_ok.returncode != 0:
                    return CheckStatus.FAILED
                ran = runner.run(sim_mod.build_run_command(vvp), cwd=config.cwd)
                return sim_mod.parse_run(ran.stdout).status
            finally:
                sim_path.write_text(original)

        mapped_v = ""
        mapped_v_path = Path(config.mapped_v)
        if mapped_v_path.exists():
            mapped_v = mapped_v_path.read_text()

        outcomes = mutation_mod.run_mutation_suite(
            mutation_mod.MUTATIONS,
            lib_text,
            sim_text,
            run_equivalence,
            run_simulation,
            mapped_v or None,
        )
        undetected = [o.mutation for o in outcomes if o.applicable and not o.detected]
        status = CheckStatus.FAILED if undetected else CheckStatus.PASSED
        detail = (
            "one or more mutations NOT detected: " + ", ".join(undetected)
            if undetected
            else "all applicable mutations detected"
        )
        return CheckResult("mutation", status, detail, kind="mutation"), outcomes
