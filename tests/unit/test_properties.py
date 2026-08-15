"""Tests for M6 (§11) — property discharge via SymbiYosys.

``sby`` is not installed in this environment, so the ``.sby`` generation, output
parsing, VCD extraction and check assembly are tested as pure functions against
**hand-written** sby output fixtures.  The fixture *format* follows the measured
sby output recorded in ``docs/M6-FINDINGS.md`` (§3–4); the fixtures themselves
are hand-written, not recorded runs.  The end-to-end discharge is not exercised;
a missing ``sby`` reports every property check as ``not_run`` with
``skippedReason: "sby not found on PATH"``.
"""

from __future__ import annotations

from pathlib import Path

from gatepack.frontend import compile_design_text
from gatepack.verify import properties as props
from gatepack.verify.base import CheckStatus, VerifyConfig

_DESIGN = (
    "name: t\n"
    "timing_model: synchronous\n"
    "clock: {signal: clk, freq_hz: 1000, source: OSC}\n"
    "reset: {signal: rst_n, active: low, source: SUPERVISOR}\n"
    "inputs:\n  - {name: x, sync: false}\n"
    "states: [A, B]\n"
    "initial: A\n"
    "transitions:\n"
    '  - {from: A, to: B, when: "x"}\n'
    '  - {from: A, to: A, when: "!x"}\n'
    '  - {from: B, to: A, when: "1"}\n'
    "output_logic: {}\n"
    "properties:\n"
    '  - {name: p1, kind: invariant, expr: "1"}\n'
    '  - {name: m1, kind: mutex, expr: "1"}\n'
    '  - {name: r1, kind: reachability, from: A, to: B}\n'
    '  - {name: l1, kind: liveness, expr: "1"}\n'
)


def _compiled():
    return compile_design_text(_DESIGN).compiled


def test_default_depth_is_max_two_states_64():
    assert props.default_depth(3) == 64
    assert props.default_depth(100) == 200


def test_property_tasks_modes():
    tasks = props.property_tasks(_compiled())
    by_label = {t.label: t for t in tasks}
    # invariant + mutex -> prove assert + cover (vacuity guard)
    assert by_label["gp_assert_0"].mode == "prove"
    assert by_label["gp_assert_0"].role == "assert"
    assert by_label["gp_cover_0"].mode == "cover"
    assert by_label["gp_cover_0"].role == "cover"
    assert by_label["gp_assert_1"].mode == "prove"
    # reachability + liveness -> cover only (M6-FINDINGS §4: mode cover)
    assert by_label["gp_cover_2"].mode == "cover"
    assert by_label["gp_cover_3"].kind == "liveness"
    assert "gp_assert_2" not in by_label


def test_sby_file_structure():
    tasks = props.property_tasks(_compiled())
    assert_task = next(t for t in tasks if t.label == "gp_assert_0")
    text = props.build_sby_file(
        "t", "build/generated.v", "build/properties.sv", assert_task
    )
    # properties.sv is `include`d into the design module under GP_FORMAL, so it
    # is never read separately and the top is the DESIGN, not a wrapper. A
    # wrapper cannot see the design's signals: Yosys silently turns
    # `dut.<sig>` into an undriven wire (M6-FINDINGS §6).
    assert "read_verilog -sv -formal -DGP_FORMAL build/generated.v" in text
    assert "read_verilog -sv build/properties.sv" not in text
    assert "prep -top t" in text
    assert "_properties" not in text
    # smtbmc cannot model the async reset of §9.3; without this the reset is
    # ignored and every property fails from a state that never resets.
    assert "async2sync" in text
    assert "smtbmc z3" in text
    assert "mode prove" in text
    # one task per file — this one is the assertion, not its cover
    assert "mode cover" not in text
    # the properties are checked against the behavioural source, never mapped.v
    assert "mapped.v" not in text


def test_sby_cover_task_uses_cover_mode():
    tasks = props.property_tasks(_compiled())
    cover_task = next(t for t in tasks if t.label == "gp_cover_0")
    text = props.build_sby_file(
        "t", "build/generated.v", "build/properties.sv", cover_task
    )
    assert "mode cover" in text
    assert "mode prove" not in text


# ---------------------------------------------------------------------------
# Output parsing — hand-written fixtures in the measured format (M6-FINDINGS §3)
# ---------------------------------------------------------------------------


def _tasks():
    return props.property_tasks(_compiled())


def test_parse_sby_prove_pass():
    stdout = (
        "SBY 12:00:00 [gp_assert_0] engine_0: ##   0:00:00  returned pass for basecase\n"
        "SBY 12:00:00 [gp_assert_0] engine_0: ##   0:00:00  returned pass for induction\n"
        "SBY 12:00:00 [gp_assert_0] DONE (PASS, rc=0)\n"
    )
    assert props.parse_sby(stdout, _tasks())["gp_assert_0"].status == "passed"


def test_parse_sby_prove_fail_counterexample():
    stdout = (
        "SBY 12:00:00 [gp_assert_0] engine_0: ##   0:00:00  Assert failed in "
        "t_properties: gp_assert_0\n"
        "SBY 12:00:00 [gp_assert_0] DONE (FAIL, rc=2)\n"
    )
    result = props.parse_sby(stdout, _tasks())["gp_assert_0"]
    assert result.status == "failed"


def test_parse_sby_basecase_pass_induction_fail_is_bounded():
    # §21.5 / M6-FINDINGS §3.1: BMC passed to depth k, induction did not close ->
    # bounded with bound k, never passed and never failed.
    stdout = (
        "SBY 12:00:00 [gp_assert_0] engine_0: ##   0:00:00  returned pass for basecase\n"
        "SBY 12:00:00 [gp_assert_0] engine_0: ##   0:00:00  returned fail for induction\n"
        "SBY 12:00:00 [gp_assert_0] DONE (FAIL, rc=2)\n"
    )
    result = props.parse_sby(stdout, _tasks())["gp_assert_0"]
    assert result.status == "bounded"
    assert result.bound == 64


def test_parse_sby_induction_pass_basecase_fail_is_not_bounded():
    # M6-FINDINGS §2: induction pass + basecase fail is the missing-reset
    # signature — a spurious failure, never a bounded pass.
    stdout = (
        "SBY 12:00:00 [gp_assert_0] engine_0: ##   0:00:00  returned fail for basecase\n"
        "SBY 12:00:00 [gp_assert_0] engine_0: ##   0:00:00  returned pass for induction\n"
        "SBY 12:00:00 [gp_assert_0] DONE (FAIL, rc=2)\n"
    )
    result = props.parse_sby(stdout, _tasks())["gp_assert_0"]
    assert result.status == "failed"
    assert "reset" in result.detail


def test_parse_sby_cover_reached_is_bounded():
    stdout = (
        "SBY 12:00:00 [gp_cover_2] engine_0: ##   0:00:00  Reached cover statement "
        "at gp_cover_2 in step 7\n"
        "SBY 12:00:00 [gp_cover_2] DONE (PASS, rc=0)\n"
    )
    result = props.parse_sby(stdout, _tasks())["gp_cover_2"]
    assert result.status == "bounded"
    assert result.bound == 7


def test_parse_sby_cover_unreached_is_failed():
    stdout = (
        "SBY 12:00:00 [gp_cover_2] DONE (FAIL, rc=2)\n"
    )
    result = props.parse_sby(stdout, _tasks())["gp_cover_2"]
    assert result.status == "failed"


def test_parse_sby_no_status_line_is_not_run():
    assert props.parse_sby("", _tasks())["gp_assert_0"].status == "not_run"


# ---------------------------------------------------------------------------
# Vacuity guard (§11) — the single most important behaviour
# ---------------------------------------------------------------------------


def _results_for(labels: dict[str, str]):
    out = {}
    for label, status in labels.items():
        bound = 7 if status == "bounded" else None
        out[label] = props.TaskResult(status=status, bound=bound)
    return out


def test_vacuous_pass_is_reported_as_failure():
    # assertion passed, but the antecedent cover failed -> the property is
    # vacuous and must NOT be reported as a pass.
    results = _results_for({"gp_assert_0": "passed", "gp_cover_0": "failed"})
    checks = props.checks_from_sby(_compiled(), _tasks(), results)
    p1 = next(c for c in checks if c.name == "property p1")
    assert p1.status is CheckStatus.FAILED
    assert "vacuous" in p1.detail


def test_assert_and_cover_pass_is_passed():
    results = _results_for({"gp_assert_0": "passed", "gp_cover_0": "bounded"})
    checks = props.checks_from_sby(_compiled(), _tasks(), results)
    p1 = next(c for c in checks if c.name == "property p1")
    assert p1.status is CheckStatus.PASSED


def test_bounded_assert_is_bounded():
    results = _results_for({"gp_assert_0": "bounded", "gp_cover_0": "bounded"})
    checks = props.checks_from_sby(_compiled(), _tasks(), results)
    p1 = next(c for c in checks if c.name == "property p1")
    assert p1.status is CheckStatus.BOUNDED_PASS
    assert p1.bound == 7


def test_reachability_is_bounded_not_passed():
    results = _results_for({"gp_cover_2": "bounded"})
    checks = props.checks_from_sby(_compiled(), _tasks(), results)
    r1 = next(c for c in checks if c.name == "property r1")
    assert r1.status is CheckStatus.BOUNDED_PASS
    assert r1.bound == 7


def test_reachability_unreachable_is_failed():
    results = _results_for({"gp_cover_2": "failed"})
    checks = props.checks_from_sby(_compiled(), _tasks(), results)
    r1 = next(c for c in checks if c.name == "property r1")
    assert r1.status is CheckStatus.FAILED


# ---------------------------------------------------------------------------
# VCD parsing (hand-written fixture)
# ---------------------------------------------------------------------------

_VCD = (
    "$timescale 1ns $end\n"
    "$scope module top $end\n"
    "$var wire 1 ! clk $end\n"
    '$var wire 1 " rst_n $end\n'
    "$var wire 1 # state_A $end\n"
    "$upscope $end\n"
    "$enddefinitions $end\n"
    "$dumpvars\n"
    "1!\n"
    '1"\n'
    "0#\n"
    "$end\n"
    "#1\n"
    "0!\n"
    "#2\n"
    "1!\n"
    "0#\n"
    "#3\n"
    "0!\n"
    "1#\n"
    "$end\n"
)


def test_parse_vcd_extracts_steps():
    steps = props.parse_vcd(_VCD)
    assert steps == [
        {"clk": "1", "rst_n": "1", "state_A": "0"},
        {"clk": "0", "rst_n": "1", "state_A": "0"},
        {"clk": "1", "rst_n": "1", "state_A": "0"},
        {"clk": "0", "rst_n": "1", "state_A": "1"},
    ]


# ---------------------------------------------------------------------------
# run_properties: tool absence is visible, never silent
# ---------------------------------------------------------------------------


class FakeRunner:
    def __init__(self, available=(), stdout=""):
        self._available = set(available)
        self.stdout = stdout
        self.argv = None

    def available(self, name):
        return name in self._available

    def run(self, argv, cwd, timeout=600):
        self.argv = argv
        from gatepack.verify.base import ToolResult

        return ToolResult(0, self.stdout, "")


def test_run_properties_without_sby_is_not_run(tmp_path):
    compiled = _compiled()
    config = VerifyConfig(
        top=compiled.design.name,
        generated_v=str(tmp_path / "generated.v"),
        properties_sv=str(tmp_path / "properties.sv"),
        cwd=str(tmp_path),
    )
    checks = props.run_properties(compiled, config, FakeRunner())
    assert [c.name for c in checks] == [
        "property p1", "property m1", "property r1", "property l1",
    ]
    for check in checks:
        assert check.status is CheckStatus.NOT_RUN
        assert check.detail == "sby not found on PATH"
        assert check.kind == "property"


def test_run_properties_with_sby_present_passes(tmp_path):
    compiled = _compiled()
    config = VerifyConfig(
        top=compiled.design.name,
        generated_v=str(tmp_path / "generated.v"),
        properties_sv=str(tmp_path / "properties.sv"),
        cwd=str(tmp_path),
    )
    tasks = props.property_tasks(compiled)
    lines = []
    for t in tasks:
        lines.append(f"SBY 12:00:00 [{t.label}] engine_0: starting process")
        if t.role == "assert":
            lines.append(f"SBY 12:00:00 [{t.label}] engine_0: returned pass for basecase")
            lines.append(f"SBY 12:00:00 [{t.label}] engine_0: returned pass for induction")
        else:
            lines.append(
                f"SBY 12:00:00 [{t.label}] engine_0: Reached cover statement "
                f"at {t.label} in step 3"
            )
        lines.append(f"SBY 12:00:00 [{t.label}] DONE (PASS, rc=0)")
    runner = FakeRunner(available=("sby",), stdout="\n".join(lines))
    checks = props.run_properties(compiled, config, runner)
    # one sby invocation per task; argv records the last of them
    assert runner.argv[0:2] == ["sby", "-f"]
    assert runner.argv[2].startswith(str(tmp_path / "properties_gp_"))
    assert runner.argv[2].endswith(".sby")
    by_name = {c.name: c for c in checks}
    # invariant/mutex pass (assert proved, cover reached); reachability/liveness
    # are bounded (cover-only).
    assert by_name["property p1"].status is CheckStatus.PASSED
    assert by_name["property m1"].status is CheckStatus.PASSED
    assert by_name["property r1"].status is CheckStatus.BOUNDED_PASS
    assert by_name["property l1"].status is CheckStatus.BOUNDED_PASS
