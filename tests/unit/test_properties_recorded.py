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
    return props.parse_sby(log, tasks)


def test_traffic_light_property_proves_and_is_not_vacuous():
    parsed = _parse("traffic_light")
    # a complete proof: `mode prove` with both basecase and induction passing
    assert parsed["gp_assert_0"].status == "passed"
    # and the antecedent is genuinely reachable, so the pass is not vacuous
    assert parsed["gp_cover_0"].status == "bounded"
    assert parsed["gp_cover_0"].bound == 5


def test_property_violating_golden_fails_with_a_reachable_antecedent():
    parsed = _parse("property_violating")
    assert parsed["gp_assert_0"].status == "failed"
    # the cover being reached is what makes the failure meaningful rather than
    # an artefact of an unreachable precondition
    assert parsed["gp_cover_0"].status == "bounded"


def test_no_check_silently_degrades_to_not_run():
    # the regression that motivated this file: a task-name mismatch made every
    # status `not_run` while the hand-written fixtures still passed
    for design in ("traffic_light", "property_violating"):
        for label, result in _parse(design).items():
            assert result.status != "not_run", f"{design}/{label}: {result.detail}"
