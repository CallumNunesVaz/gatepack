"""Tests for C4 verification (gatepack.verify) — script generation, result
parsing, the mutation engine, and strategy dispatch.  No Yosys/Icarus/sby is
needed here: command construction, parsing and the mutation engine are pure
functions exercised with synthetic tool output.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gatepack.frontend import compile_design_file
from gatepack.verify import equivalence, mutation, simulation
from gatepack.verify.base import (
    CheckStatus,
    SubprocessRunner,
    VerifyConfig,
)
from gatepack.verify.synchronous import SynchronousVerify

DESIGNS = Path(__file__).resolve().parents[1] / "golden" / "designs"


def _config(**overrides) -> VerifyConfig:
    base = dict(top="mytop")
    base.update(overrides)
    return VerifyConfig(**base)


# --- equivalence --------------------------------------------------------------


def test_golden_prep_is_the_shared_frontend():
    from gatepack import yosys

    config = _config()
    golden = equivalence.golden_prep(config)
    expected = yosys.common_frontend("mytop", config.generated_v, config.golden_json)
    assert golden == expected
    # the golden side stops before dfflegalize/dfflibmap/abc (those are C3's)
    assert "dfflegalize" not in golden
    assert "dfflibmap" not in golden
    assert "abc " not in golden


def test_equivalence_script_commands_in_order():
    script = equivalence.build_equivalence_script(_config())
    assert script.index("equiv_make golden mapped equiv") < script.index("equiv_induct")
    assert script.index("equiv_induct") < script.index("equiv_status -assert")


def test_equivalence_recipe_reads_cells_sim_v():
    # M0 §6: cells_sim.v is mandatory; without the behavioural models equiv_make
    # dies with "Module '\INV' ... is not part of the design".
    script = equivalence.build_equivalence_script(_config())
    assert "cells_sim.v" in script
    gate_read = script.index("read_verilog build/mapped.v build/cells_sim.v")
    assert gate_read > script.index("design -reset")


def test_equivalence_recipe_runs_async2sync_on_both_sides():
    # M0 §6: async-reset flops are $adff with no SAT model; async2sync must run
    # on both sides or induction cannot close.
    script = equivalence.build_equivalence_script(_config())
    assert script.count("async2sync") == 2


def test_equivalence_recipe_reprocs_after_roundtrip():
    # M0 §6: re-`proc` after every Verilog round-trip, or the module "contains
    # memories or processes".
    script = equivalence.build_equivalence_script(_config())
    lines = [ln.strip() for ln in script.splitlines() if ln.strip()]
    assert "write_verilog -noattr build/gold.v" in lines
    assert "proc; opt; async2sync; opt" in lines
    assert "proc; flatten; opt; async2sync; opt" in lines
    assert "design -stash goldstash" in lines
    assert "design -stash gatestash" in lines


def test_equivalence_recipe_copies_stashes_back_before_equiv_make():
    # M0-FINDINGS §6 correction: `design -stash` saves the design *and clears
    # it*, and `equiv_make` takes module names in the current design, not stash
    # names.  The stashes must be copied back in and renamed first.
    script = equivalence.build_equivalence_script(_config())
    lines = [ln.strip() for ln in script.splitlines() if ln.strip()]
    copy_gold = "design -copy-from goldstash -as golden mytop"
    copy_gate = "design -copy-from gatestash -as mapped mytop"
    assert copy_gold in lines
    assert copy_gate in lines
    # copy-from precedes equiv_make, which is the command that would otherwise
    # fail with "Can't find gold module golden".
    assert script.index(copy_gold) < script.index("equiv_make golden mapped equiv")


def test_equivalence_fallback_ladder():
    ladder = equivalence.induction_ladder(3)
    assert ladder[0] == (equivalence.EquivStep.EQUIV_SIMPLE, None)
    assert ladder[1] == (equivalence.EquivStep.EQUIV_INDUCT, 64)
    # N is raised between induction rungs
    assert ladder[2][1] == 2 * ladder[1][1]
    assert ladder[-1] == (equivalence.EquivStep.SBY_MITER, None)


def test_default_induction_steps_is_max_two_states_64():
    assert equivalence.default_induction_steps(3) == 64
    assert equivalence.default_induction_steps(100) == 200


def test_parse_equiv_status_success_and_failure():
    assert equivalence.parse_equiv_status(
        "Equivalence successfully proven!"
    ).status is CheckStatus.PASSED
    assert equivalence.parse_equiv_status(
        "ERROR: Equivalence check failed!"
    ).status is CheckStatus.FAILED


def test_sby_bmc_is_bounded_not_passed():
    outcome = equivalence.parse_sby_bmc("SUMMARY: PASS", bound=10)
    assert outcome.status is CheckStatus.BOUNDED_PASS
    assert outcome.bound == 10


def test_sby_bmc_failure():
    outcome = equivalence.parse_sby_bmc("counterexample found", bound=10)
    assert outcome.status is CheckStatus.FAILED


# --- exhaustive simulation ----------------------------------------------------


def test_vector_count_and_feasibility():
    assert simulation.exhaustive_vector_count(2, 1) == 4
    assert simulation.exhaustive_vector_count(2, 3) == 12
    assert simulation.is_feasible(4, 3, 1 << 10)
    assert not simulation.is_feasible(25, 1, 1 << 24)


def test_decide_above_cap_is_not_applicable_not_failed():
    outcome = simulation.decide(25, 1, cap=1 << 10)
    assert outcome.status is CheckStatus.NOT_APPLICABLE
    assert "equivalence" in outcome.detail


def test_parse_run_pass_and_fail():
    assert simulation.parse_run("EXHAUSTIVE_SIM_PASS").status is CheckStatus.PASSED
    assert simulation.parse_run("EXHAUSTIVE_SIM_FAIL (3)").status is CheckStatus.FAILED


def test_combinational_testbench_exhaustive():
    compiled = compile_design_file(DESIGNS / "xor2.yaml").compiled
    tb = simulation.build_testbench(compiled, _config(top="xor2"))
    assert "xor2 dut (" in tb
    assert tb.count("if (y !==") == 4  # 2 inputs -> 2^2 vectors
    assert "EXHAUSTIVE_SIM_PASS" in tb
    assert "$random" not in tb
    assert "$urandom" not in tb
    assert "$coverage" not in tb


def test_sequential_testbench_drives_every_transition():
    compiled = compile_design_file(DESIGNS / "traffic_light.yaml").compiled
    tb = simulation.build_testbench(compiled, _config(top="traffic_light"))
    assert "traffic_light dut (" in tb
    assert "EXHAUSTIVE_SIM_PASS" in tb
    assert "$random" not in tb


# --- mutation -----------------------------------------------------------------


def _artefacts() -> tuple[str, str]:
    from gatepack.liberty.generator import generate as generate_liberty
    from gatepack.liberty.sim import generate as generate_sim
    from gatepack.parts import load_parts

    parts = load_parts(Path(__file__).resolve().parents[2] / "libraries" / "74aup.csv")
    return generate_liberty(parts, library_name="t").text, generate_sim(parts)


def test_mutations_all_change_both_artefacts():
    lib, sim = _artefacts()
    for m in mutation.MUTATIONS:
        lib2, sim2 = m.mutate(lib, sim)
        assert lib2 != lib or sim2 != sim, m.name


def test_nand_to_and_mutation():
    lib, sim = _artefacts()
    m = mutation.MUTATIONS[0]
    assert m.name == "nand_to_and"
    lib2, sim2 = m.mutate(lib, sim)
    assert 'function : "(A & B)";' in lib2
    assert "assign Y = (A & B);" in sim2


def test_flop_d_invert_mutation():
    lib, sim = _artefacts()
    m = mutation.MUTATIONS[1]
    lib2, sim2 = m.mutate(lib, sim)
    assert 'next_state : "(!D)";' in lib2
    assert "Q <= (~D);" in sim2


def test_reset_polarity_mutation():
    lib, sim = _artefacts()
    m = mutation.MUTATIONS[2]
    lib2, sim2 = m.mutate(lib, sim)
    assert 'clear : "RST_N";' in lib2
    assert "if (RST_N) Q <= 1'b0;" in sim2


def test_mutation_detected_only_when_both_checks_fail():
    assert mutation.is_detected(CheckStatus.FAILED, CheckStatus.FAILED) is True
    assert mutation.is_detected(CheckStatus.PASSED, CheckStatus.FAILED) is False
    assert mutation.is_detected(CheckStatus.FAILED, CheckStatus.PASSED) is False
    assert mutation.is_detected(CheckStatus.PASSED, CheckStatus.PASSED) is False


def test_run_mutation_suite_vacuous_pass_is_not_detected():
    lib, sim = _artefacts()
    vacuous_equiv = lambda _text: CheckStatus.PASSED
    vacuous_sim = lambda _text: CheckStatus.PASSED
    outcomes = mutation.run_mutation_suite(
        mutation.MUTATIONS, lib, sim, vacuous_equiv, vacuous_sim
    )
    assert all(not o.detected for o in outcomes)


def test_run_mutation_suite_real_fault_is_detected():
    lib, sim = _artefacts()

    def failing_equiv(_text):
        return CheckStatus.FAILED

    def failing_sim(_text):
        return CheckStatus.FAILED

    outcomes = mutation.run_mutation_suite(
        mutation.MUTATIONS, lib, sim, failing_equiv, failing_sim
    )
    assert all(o.detected for o in outcomes)


def test_used_cells_extracts_cell_types():
    mapped = (
        "module t;\n"
        "  NAND2 _0_ (.A(a), .B(b), .Y(y));\n"
        "  DFF_R _1_ (.D(d), .CK(clk), .Q(q), .RST_N(r));\n"
        "endmodule\n"
    )
    assert mutation.used_cells(mapped) == {"NAND2", "DFF_R"}


def test_is_applicable_depends_on_instantiated_cells():
    combinational = "module t;\n  XOR2 _0_ (.A(a), .B(b), .Y(y));\nendmodule\n"
    nand = mutation.MUTATIONS[0]
    flop = mutation.MUTATIONS[1]
    assert nand.name == "nand_to_and"
    assert not mutation.is_applicable(nand, combinational)
    assert not mutation.is_applicable(flop, combinational)
    sequential = "module t;\n  NAND2 _0_ (.A(a), .B(b), .Y(y));\n  DFF_R _1_ (.D(d), .CK(clk), .Q(q), .RST_N(r));\nendmodule\n"
    assert mutation.is_applicable(nand, sequential)
    assert mutation.is_applicable(flop, sequential)


def test_run_mutation_suite_marks_inapplicable_separately():
    # A combinational netlist (no NAND2, no flops): every mutation is
    # not_applicable, none runs a check, and none counts as a vacuity failure.
    lib, sim = _artefacts()
    combinational = "module t;\n  XOR2 _0_ (.A(a), .B(b), .Y(y));\nendmodule\n"
    calls = []

    def run_equiv(_text):
        calls.append("equiv")
        return CheckStatus.PASSED

    def run_sim(_text):
        calls.append("sim")
        return CheckStatus.PASSED

    outcomes = mutation.run_mutation_suite(
        mutation.MUTATIONS, lib, sim, run_equiv, run_sim, combinational
    )
    assert all(not o.detected and not o.applicable for o in outcomes)
    assert calls == []  # no check ran for an inapplicable mutation


def test_run_mutation_suite_applicable_undetected_is_a_failure():
    # A sequential netlist uses the mutated cells, so an undetected fault is a
    # genuine vacuity failure, not a category error.
    from gatepack.verify.base import VerificationReport

    lib, sim = _artefacts()
    sequential = "module t;\n  NAND2 _0_ (.A(a), .B(b), .Y(y));\n  DFF_R _1_ (.D(d), .CK(clk), .Q(q), .RST_N(r));\nendmodule\n"

    def vacuous_equiv(_text):
        return CheckStatus.PASSED

    def vacuous_sim(_text):
        return CheckStatus.PASSED

    outcomes = mutation.run_mutation_suite(
        mutation.MUTATIONS, lib, sim, vacuous_equiv, vacuous_sim, sequential
    )
    assert all(o.applicable for o in outcomes)
    assert all(not o.detected for o in outcomes)
    report = VerificationReport(checks=[], mutations=outcomes)
    assert report.has_failure  # applicable-but-undetected is a hard failure


def test_not_applicable_mutations_do_not_fail_the_report():
    from gatepack.verify.base import MutationOutcome, VerificationReport

    report = VerificationReport(
        checks=[],
        mutations=[MutationOutcome("nand_to_and", False, "n/a", applicable=False)],
    )
    assert not report.has_failure


# --- strategy dispatch --------------------------------------------------------


class FakeRunner:
    def __init__(self, available=(), stdout_by_tool=None):
        self._available = set(available)
        self._stdout = stdout_by_tool or {}

    def available(self, name):
        return name in self._available

    def run(self, argv, cwd, timeout=600):
        from gatepack.verify.base import ToolResult

        tool = argv[0]
        return ToolResult(0, self._stdout.get(tool, ""), "")


def _compiled():
    return compile_design_file(DESIGNS / "traffic_light.yaml").compiled


def _strategy_report(runner, config=None, lib_text="l", sim_text="s"):
    strategy = SynchronousVerify()
    return strategy.verify(
        config or _config(), _compiled(), runner, lib_text, sim_text
    )


def test_strategy_reports_not_run_without_tools():
    report = _strategy_report(FakeRunner())
    statuses = {c.name: c.status for c in report.checks}
    assert statuses["equivalence"] is CheckStatus.NOT_RUN
    assert statuses["exhaustive simulation"] is CheckStatus.NOT_RUN
    assert statuses["mutation"] is CheckStatus.NOT_RUN
    assert report.has_not_run
    assert not report.ok


def test_strategy_equivalence_parses_real_output():
    runner = FakeRunner(
        available=("yosys",), stdout_by_tool={"yosys": "Equivalence successfully proven!"}
    )
    report = _strategy_report(runner)
    statuses = {c.name: c.status for c in report.checks}
    assert statuses["equivalence"] is CheckStatus.PASSED
    assert statuses["exhaustive simulation"] is CheckStatus.NOT_RUN


def test_strategy_simulation_passes_on_iverilog_output():
    runner = FakeRunner(
        available=("iverilog",),
        stdout_by_tool={"iverilog": "EXHAUSTIVE_SIM_PASS", "vvp": "EXHAUSTIVE_SIM_PASS"},
    )
    report = _strategy_report(runner)
    statuses = {c.name: c.status for c in report.checks}
    assert statuses["exhaustive simulation"] is CheckStatus.PASSED
