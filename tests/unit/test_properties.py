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
    "outputs:\n  - {name: a}\n  - {name: b}\n"
    "states: [A, B]\n"
    "initial: A\n"
    "transitions:\n"
    '  - {from: A, to: B, when: "x"}\n'
    '  - {from: A, to: A, when: "!x"}\n'
    '  - {from: B, to: A, when: "1"}\n'
    "output_logic:\n"
    '  a: "state == B"\n'
    '  b: "x"\n'
    "properties:\n"
    '  - {name: p1, kind: invariant, expr: "!x | (state == B)"}\n'
    '  - {name: m1, kind: mutex, expr: "!(a & b)"}\n'
    '  - {name: r1, kind: reachability, from: A, to: B}\n'
    '  - {name: l1, kind: liveness, to: B}\n'
)


def _compiled():
    return compile_design_text(_DESIGN).compiled


def test_default_depth_is_max_two_states_64():
    assert props.default_depth(3) == 64
    assert props.default_depth(100) == 200


def test_property_tasks_modes():
    tasks = props.property_tasks(_compiled())
    by_label = {t.label: t for t in tasks}
    # invariant + mutex -> prove assert + ONE cover task (vacuity guard)
    assert by_label["gp_assert_0"].mode == "prove"
    assert by_label["gp_assert_0"].role == "assert"
    # implication antecedent (p in p -> q) is a SINGLE cover at gp_cover_0
    assert by_label["gp_cover_0"].mode == "cover"
    assert by_label["gp_cover_0"].role == "cover"
    assert len(by_label["gp_cover_0"].covers) == 1
    assert "antecedent" in by_label["gp_cover_0"].covers[0].description
    assert by_label["gp_assert_1"].mode == "prove"
    # a mutex over a,b -> ONE cover task carrying both per-signal covers
    assert by_label["gp_cover_1"].kind == "mutex"
    assert [c.label for c in by_label["gp_cover_1"].covers] == [
        "gp_cover_1_0",
        "gp_cover_1_1",
    ]
    # reachability + liveness -> cover only (M6-FINDINGS §4: mode cover)
    assert by_label["gp_cover_2"].mode == "cover"
    assert by_label["gp_cover_3"].kind == "liveness"
    assert "gp_assert_2" not in by_label
    assert "gp_assert_3" not in by_label


def test_sby_file_structure():
    tasks = props.property_tasks(_compiled())
    assert_task = next(t for t in tasks if t.label == "gp_assert_0")
    text = props.build_sby_file(
        "t", "build/generated.v", "build/properties.sv", assert_task
    )
    # properties.sv is `include`d into the design module under GP_FORMAL, so it
    # is never read separately and the top is the DESIGN, not a wrapper. A
    # wrapper cannot see the design's signals: Yosys silently turns
    # `dut.<sig>` into an undriven wire (M6-FINDINGS §6).  The read command
    # uses the *basename*: sby runs it from the task's src/ dir, where the
    # [files] entries land under their basenames.
    assert "read_verilog -sv -formal -DGP_FORMAL -DGP_PROVE generated.v" in text
    assert "build/generated.v" in text  # the [files] entry, relative to cwd
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
    # the cover task compiles the assertions out (M6-FINDINGS §6 / `mode cover`
    # still checks asserts), so it reads with GP_COVER, not GP_PROVE.
    assert "-DGP_COVER" in text
    assert "-DGP_PROVE" not in text


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
    # measured format (M6-FINDINGS §4 / recorded logs): sby names the unreached
    # cover explicitly.
    stdout = (
        "SBY 12:00:00 [gp_cover_2] engine_0: ##   0:00:00  Unreached cover "
        "statement at gp_cover_2.\n"
        "SBY 12:00:00 [gp_cover_2] engine_0: Status: failed\n"
        "SBY 12:00:00 [gp_cover_2] DONE (FAIL, rc=2)\n"
    )
    result = props.parse_sby(stdout, _tasks())["gp_cover_2"]
    assert result.status == "failed"


def test_parse_sby_cover_fail_without_unreached_line_is_failed():
    # a cover task that FAILs without an explicit "Unreached ..." line is still
    # a failure, never a pass.
    stdout = "SBY 12:00:00 [gp_cover_2] DONE (FAIL, rc=2)\n"
    result = props.parse_sby(stdout, _tasks())["gp_cover_2"]
    assert result.status == "failed"


def test_parse_sby_multi_cover_reaches_each_and_names_the_unreached():
    # one `mode cover` run reaches every cover; an unreached signal is reported
    # per-label, so the vacuity failure can name the exact signal.
    stdout = (
        "SBY 12:00:00 [gp_cover_1] engine_0: Reached cover statement at "
        "gp_cover_1_0 in step 4\n"
        "SBY 12:00:00 [gp_cover_1] engine_0: Unreached cover statement at "
        "gp_cover_1_1.\n"
        "SBY 12:00:00 [gp_cover_1] DONE (FAIL, rc=2)\n"
    )
    parsed = props.parse_sby(stdout, _tasks())
    assert parsed["gp_cover_1_0"].status == "bounded"
    assert parsed["gp_cover_1_1"].status == "failed"


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


def test_mutex_one_unreached_signal_cover_is_vacuous_failure():
    # the mutex assertion proved, but ONE of its signals can never be asserted:
    # the mutex is vacuously true for that signal and must be a failure.
    results = _results_for(
        {
            "gp_assert_1": "passed",
            "gp_cover_1_0": "bounded",
            "gp_cover_1_1": "failed",
        }
    )
    checks = props.checks_from_sby(_compiled(), _tasks(), results)
    m1 = next(c for c in checks if c.name == "property m1")
    assert m1.status is CheckStatus.FAILED
    assert "vacuous" in m1.detail.lower() or "vacuity" in m1.detail.lower()
    assert "b" in m1.detail  # names the signal whose cover failed


def test_mutex_all_signal_covers_reached_is_passed():
    results = _results_for(
        {
            "gp_assert_1": "passed",
            "gp_cover_1_0": "bounded",
            "gp_cover_1_1": "bounded",
        }
    )
    checks = props.checks_from_sby(_compiled(), _tasks(), results)
    m1 = next(c for c in checks if c.name == "property m1")
    assert m1.status is CheckStatus.PASSED


def test_liveness_is_bounded_with_default_depth_not_reached_step():
    # §21.5: a liveness result is bounded with the default depth, never the
    # reached step and never a plain pass.
    results = _results_for({"gp_cover_3": "bounded"})
    checks = props.checks_from_sby(_compiled(), _tasks(), results)
    l1 = next(c for c in checks if c.name == "property l1")
    assert l1.status is CheckStatus.BOUNDED_PASS
    assert l1.bound == props.default_depth(2) == 64


def test_liveness_unreachable_is_failed():
    results = _results_for({"gp_cover_3": "failed"})
    checks = props.checks_from_sby(_compiled(), _tasks(), results)
    l1 = next(c for c in checks if c.name == "property l1")
    assert l1.status is CheckStatus.FAILED


def test_invariant_with_no_referenced_signals_is_not_run():
    # an invariant with no antecedent and no signals has no vacuity guard to run;
    # reporting it as passed would be a silent vacuous pass.
    design = _DESIGN.replace(
        '  - {name: p1, kind: invariant, expr: "!x | (state == B)"}\n',
        '  - {name: p1, kind: invariant, expr: "1"}\n',
    )
    compiled = compile_design_text(design).compiled
    tasks = props.property_tasks(compiled)
    results = _results_for({"gp_assert_0": "passed"})
    checks = props.checks_from_sby(compiled, tasks, results)
    p1 = next(c for c in checks if c.name == "property p1")
    assert p1.status is CheckStatus.NOT_RUN
    assert "no signals" in p1.detail


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
            for spec in t.covers:
                lines.append(
                    f"SBY 12:00:00 [{t.label}] engine_0: Reached cover statement "
                    f"at {spec.label} in step 3"
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
