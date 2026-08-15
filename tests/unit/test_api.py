"""Tests for the ``--json`` payload builders (gatepack.api).

The envelope shape is pinned by ``tests/contract/test_json_contract.py``; these
tests pin the *semantics* the GUI depends on: the four-way check status, the
vacuous-pass guard (a bounded check never renders as ``passed``), the §C13
single-source marker, and the §C14 violated metric.
"""

from __future__ import annotations

from gatepack import api
from gatepack.diagnostic import Diagnostic, GP_CPLD_BLOCKER
from gatepack.emit.bom import BomRow
from gatepack.verify.base import CheckResult, CheckStatus, Counterexample


def test_check_status_mapping_never_folds_bounded_into_passed():
    # §C15 [R4-25]: a bounded pass is a distinct state, never a green tick.
    bounded = CheckResult("eq", CheckStatus.BOUNDED_PASS, "bmc to depth", bound=10)
    payload = api.check_payload(bounded)
    assert payload["status"] == "bounded"
    assert payload["bound"] == 10

    passed = api.check_payload(CheckResult("eq", CheckStatus.PASSED))
    assert passed["status"] == "passed"
    assert "bound" not in passed

    not_run = api.check_payload(CheckResult("eq", CheckStatus.NOT_RUN, "sby not found on PATH"))
    assert not_run["status"] == "not_run"
    assert not_run["skippedReason"] == "sby not found on PATH"

    # NOT_APPLICABLE (sim above the §21.4 cap) is an honest non-verdict.
    na = api.check_payload(CheckResult("sim", CheckStatus.NOT_APPLICABLE, "above cap"))
    assert na["status"] == "not_run"


def test_verify_allPassed_requires_every_check_passed():
    from types import SimpleNamespace

    report = SimpleNamespace(
        checks=[
            CheckResult("a", CheckStatus.PASSED),
            CheckResult("b", CheckStatus.BOUNDED_PASS, bound=8),
        ]
    )
    assert api.verify_payload(report)["allPassed"] is False

    report2 = SimpleNamespace(checks=[CheckResult("a", CheckStatus.PASSED)])
    assert api.verify_payload(report2)["allPassed"] is True


def test_counterexample_serialization():
    ce = Counterexample(
        steps=({"clk": "0", "x": "1"}, {"clk": "1", "x": "0"}),
        pointers=("design.yaml:12:transitions[0]",),
    )
    payload = api.check_payload(
        CheckResult("p", CheckStatus.FAILED, kind="property", counterexample=ce)
    )
    assert payload["counterexample"] == {
        "steps": [{"clk": "0", "x": "1"}, {"clk": "1", "x": "0"}],
        "pointers": ["design.yaml:12:transitions[0]"],
    }


def test_bomline_single_sourced_is_fewer_than_two_manufacturers():
    dual = BomRow("74AUP1G00", "TI;Nexperia", "", "SOT-353", 2, ("U1", "U2"), "G")
    single = BomRow("74AUP1G00", "TI", "", "SOT-353", 1, ("U1",), "G")
    assert api.bomline(dual)["singleSourced"] is False
    assert api.bomline(dual)["manufacturers"] == ["TI", "Nexperia"]
    assert api.bomline(single)["singleSourced"] is True


def test_metric_violated_only_when_limit_exists_and_exceeded():
    assert api.metric("x", 5, "n", 10)["violated"] is False
    assert api.metric("x", 15, "n", 10)["violated"] is True
    # no limit -> never violated, even for a large value
    assert api.metric("x", 1000, "n", None)["violated"] is False
    # unknown value -> never violated
    assert api.metric("x", None, "n", 10)["violated"] is False


def test_estimate_reasons_list_amber_and_red():
    class Metric:
        def __init__(self, value, status):
            self.value = value
            self.status = status

    class Verdict:
        overall = "red"
        metrics = {
            "package count": Metric(60, "red"),
            "flop count": Metric(4, "green"),
        }

    reasons = api._estimate_reasons(Verdict)
    assert any("package count" in r and "red" in r for r in reasons)


def test_estimate_payload_red_populates_alternative():
    from types import SimpleNamespace

    class Metric:
        def __init__(self, value, status):
            self.value = value
            self.status = status

    verdict = SimpleNamespace(
        overall="red",
        metrics={
            "package count": Metric(60, "red"),
            "flop count": Metric(4, "green"),
            "clock net fanout": Metric(4, "green"),
            "combinational depth": Metric(3, "green"),
        },
    )
    compiled = SimpleNamespace(flop_count=4)
    result = SimpleNamespace(verdict=verdict, compiled=compiled)
    payload = api.estimate_payload(result)
    assert payload["verdict"] == "red"
    assert payload["alternative"] is not None
    assert "CPLD" in payload["alternative"]


def test_analysis_summary_cpld_blockers_serialized():
    class Timing:
        combinational_depth = 3

    class Static:
        total_ua = 1.2

    class Stats:
        package_count = 2
        pack_cost = 2.0

    class Constraints:
        max_packages = None
        max_flops = None
        max_static_ua = None

    class Design:
        constraints = Constraints()

    class Compiled:
        flop_count = 5
        design = Design()

    class Result:
        packed_stats = Stats()
        static_current = Static()
        timing = Timing()

    summary = api.analysis_summary(
        Compiled(),
        Result(),
        [Diagnostic("warning", GP_CPLD_BLOCKER, "a memory blocks CPLD", path="mapped.json")],
    )
    assert summary["scoap"] == []
    assert summary["faults"] == {"detected": 0, "undetected": 0, "redundant": 0, "untestable": 0}
    assert len(summary["cpldBlockers"]) == 1
    assert summary["cpldBlockers"][0]["code"] == GP_CPLD_BLOCKER
