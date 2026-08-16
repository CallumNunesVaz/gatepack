"""Parser tests against RECORDED sby output, not hand-written fixtures.

The distinction matters and is the reason this file exists. The original
parser was unit-tested against hand-written fixtures using the bare SVA label
(``[gp_assert_0]``); real sby brackets the *task name*, which is the ``.sby``
file's stem (``[properties_gp_assert_0]``). Every check silently degraded to
``not_run`` on the first real run, and the hand-written tests all passed.

These logs were captured from real sby (pinned commit, see Dockerfile.probe)
running the scripts gatepack itself generates. Regenerate them by running the
`.sby` files that `build_sby_file` emits inside the toolchain image.
"""

from __future__ import annotations

from pathlib import Path

from gatepack.frontend import compile_design_file
from gatepack.verify import properties as props

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "sby"
DESIGNS = Path(__file__).resolve().parents[1] / "golden" / "designs"


def _parse(design: str):
    result = compile_design_file(DESIGNS / f"{design}.yaml")
    tasks = props.property_tasks(result.compiled)
    log = (FIXTURES / f"{design}.recorded.log").read_text()
    return result, props.parse_sby(log, tasks)


def test_traffic_light_property_proves_and_is_not_vacuous():
    result, parsed = _parse("traffic_light")
    # a complete proof: `mode prove` with both basecase and induction passing
    assert parsed["gp_assert_0"].status == "passed"
    # the mutex antecedent is genuinely reachable: every one of red/green/amber
    # can individually be asserted, so the pass is not vacuous.
    for label in ("gp_cover_0_0", "gp_cover_0_1", "gp_cover_0_2"):
        assert parsed[label].status == "bounded", (label, parsed[label].detail)
    checks = props.checks_from_sby(
        result.compiled, props.property_tasks(result.compiled), parsed
    )
    check = next(c for c in checks if c.name == "property one_light_only")
    from gatepack.verify.base import CheckStatus

    assert check.status is CheckStatus.PASSED


def test_property_violating_golden_fails_with_a_reachable_antecedent():
    result, parsed = _parse("property_violating")
    assert parsed["gp_assert_0"].status == "failed"
    # the covers being reached is what makes the failure meaningful rather than
    # an artefact of an unreachable precondition: enable and fault can each be
    # asserted, and the assertion still fails.
    assert parsed["gp_cover_0_0"].status == "bounded"
    assert parsed["gp_cover_0_1"].status == "bounded"


def test_liveness_is_bounded_never_passed():
    result, parsed = _parse("liveness")
    # a bounded liveness result: the target is reachable, but the check is
    # bounded, so it reports BOUNDED_PASS with the §21.5 default depth — never
    # passed.
    assert parsed["gp_cover_0"].status == "bounded"
    from gatepack.verify.base import CheckStatus

    checks = props.checks_from_sby(
        result.compiled, props.property_tasks(result.compiled), parsed
    )
    check = next(c for c in checks if c.name == "property eventually_done")
    assert check.status is CheckStatus.BOUNDED_PASS
    assert check.bound == props.default_depth(len(result.compiled.state_order))


def test_liveness_unreachable_target_fails():
    result, parsed = _parse("liveness_violating")
    assert parsed["gp_cover_0"].status == "failed"
    from gatepack.verify.base import CheckStatus

    checks = props.checks_from_sby(
        result.compiled, props.property_tasks(result.compiled), parsed
    )
    check = next(c for c in checks if c.name == "property eventually_done")
    assert check.status is CheckStatus.FAILED


def test_vacuous_mutex_is_reported_as_failure_not_a_pass():
    # the assertion proves (the mutex always holds), but one of its signals can
    # never be asserted — so the pass is vacuous and must be a FAILURE.
    result, parsed = _parse("vacuous_mutex")
    assert parsed["gp_assert_0"].status == "passed"
    assert parsed["gp_cover_0_0"].status == "bounded"  # 'a' can be asserted
    assert parsed["gp_cover_0_1"].status == "failed"  # 'b' never can
    from gatepack.verify.base import CheckStatus

    checks = props.checks_from_sby(
        result.compiled, props.property_tasks(result.compiled), parsed
    )
    check = next(c for c in checks if c.name == "property never_both")
    assert check.status is CheckStatus.FAILED
    assert "vacuous" in check.detail
    assert "b" in check.detail  # names the signal whose cover failed


def test_no_check_silently_degrades_to_not_run():
    # the regression that motivated this file: a task-name mismatch made every
    # status `not_run` while the hand-written fixtures still passed
    for design in (
        "traffic_light",
        "property_violating",
        "liveness",
        "liveness_violating",
        "vacuous_mutex",
    ):
        _result, parsed = _parse(design)
        for label, result in parsed.items():
            assert result.status != "not_run", f"{design}/{label}: {result.detail}"
