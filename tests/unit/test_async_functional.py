"""The functional check: the asynchronous path now verifies *function*, not only hazards.

Package L closes the gap the injection probe measured (§7.3): a netlist that is
hazard-free but wrong used to ship green, because equivalence is not applicable
and the two hazard checks only asked whether outputs glitch.  This module pins
the new exhaustive fundamental-mode check against the flow table:

* it enumerates (never samples) every stable total state x single-input change,
* a wrong cover is a *failed* check naming the total state and input,
* too large to enumerate is *not applicable* (and never reads as a pass),
* and the pipeline gates the netlist on a passing functional check.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from gatepack.async_pipeline import (
    AsyncPipelineResult,
    HazardFailed,
    run_async_pipeline,
)
from gatepack.frontend import model as model_mod
from gatepack.frontend import yaml_subset
from gatepack.frontend.schema import Design
from gatepack.netlist import MappedCell, MappedNetlist
from gatepack.synth import asynchronous as backend
from gatepack.synth.async_.assign import Assignment
from gatepack.synth.async_.cover import CoverResult
from gatepack.synth.async_.emit import EmittedNetlist
from gatepack.synth.async_.flowtable import FlowTable, build_flow_table
from gatepack.verify.asynchronous import (
    ASYNC_FUNC_ENUM_CAP,
    FUNCTIONAL_CHECK_NAME,
    enumerate_functional_pairs,
    run_functional_check,
)
from gatepack.verify.base import CheckResult, CheckStatus, VerificationReport

LATCH = """
name: async_latch
timing_model: asynchronous
reset: {signal: rst_n, active: low}
inputs: [{name: req, sync: false}, {name: ack, sync: false}]
states: [IDLE, BUSY]
initial: IDLE
transitions:
  - {from: IDLE, to: BUSY, when: "req"}
  - {from: IDLE, to: IDLE, when: "!req"}
  - {from: BUSY, to: IDLE, when: "ack"}
  - {from: BUSY, to: BUSY, when: "!ack"}
outputs: [{name: q}]
output_logic: {q: "state == BUSY"}
fundamental_mode: {mutually_exclusive: [[req, ack]]}
"""

FUNCS = {"INV": "!A", "BUF": "A", "AND2": "A&B", "OR2": "A|B"}


CHAIN3 = """
name: chain3
timing_model: asynchronous
reset: {signal: rst_n, active: low}
inputs: [{name: x, sync: false}]
states: [A, B, C]
initial: A
transitions:
  - {from: A, to: B, when: "x"}
  - {from: A, to: A, when: "!x"}
  - {from: B, to: C, when: "x"}
  - {from: B, to: A, when: "!x"}
  - {from: C, to: C, when: "1"}
outputs: [{name: y}]
output_logic: {y: "state == C"}
fundamental_mode: {mutually_exclusive: [[x]]}
"""


def _compile(yaml_text: str):
    node = yaml_subset.parse(yaml_text)
    data = yaml_subset.to_python(node)
    design = Design.model_validate(data)
    return model_mod.compile_design(design, source_name="t.yaml", provenance={})


def _assignment() -> Assignment:
    return Assignment(codes={"IDLE": 1, "BUSY": 0}, width=1)


def _cell(name: str, cell: str, conns: dict[str, str]) -> MappedCell:
    directions = (
        {"A": "input", "Y": "output"}
        if cell == "INV" or cell == "BUF"
        else {"A": "input", "B": "input", "Y": "output"}
    )
    return MappedCell(name=name, cell=cell, tier="G", connections=conns, directions=directions)


def _correct_netlist() -> MappedNetlist:
    # next_0 = (s_0 & !req) | (!s_0 & ack), q = !s_0  (IDLE=1, BUSY=0).
    return MappedNetlist(
        top="async_latch",
        cells=(
            _cell("inv_req", "INV", {"A": "req", "Y": "nreq"}),
            _cell("inv_s0", "INV", {"A": "s_0", "Y": "ns0"}),
            _cell("and1", "AND2", {"A": "s_0", "B": "nreq", "Y": "t1"}),
            _cell("and2", "AND2", {"A": "ns0", "B": "ack", "Y": "t2"}),
            _cell("or1", "OR2", {"A": "t1", "B": "t2", "Y": "s_0"}),
            _cell("buf", "BUF", {"A": "ns0", "Y": "q"}),
        ),
        inputs=("req", "ack"),
        outputs=("q",),
    )


def _wrong_next_netlist() -> MappedNetlist:
    # next_0 = !s_0 (an inverter in feedback) — wrong everywhere the machine self-loops.
    return MappedNetlist(
        top="async_latch",
        cells=(
            _cell("inv_s0", "INV", {"A": "s_0", "Y": "ns0"}),
            _cell("buf", "BUF", {"A": "ns0", "Y": "s_0"}),
            _cell("bufq", "BUF", {"A": "ns0", "Y": "q"}),
        ),
        inputs=("req", "ack"),
        outputs=("q",),
    )


def test_enumerate_is_exhaustive_not_sampled():
    table = build_flow_table(_compile(LATCH))
    pairs = enumerate_functional_pairs(table)
    # 4 stable total states (IDLE@F,F; IDLE@F,T; BUSY@F,F; BUSY@T,F) x 2 inputs.
    assert len(pairs) == 8
    assert len(pairs) == len(set(pairs))  # no duplicates, no gaps


def test_functional_check_passes_and_reports_the_pair_count():
    table = build_flow_table(_compile(LATCH))
    result = run_functional_check(_correct_netlist(), FUNCS, table, _assignment())
    assert result.status is CheckStatus.PASSED
    assert result.name == FUNCTIONAL_CHECK_NAME
    assert "8 total-state/input-change pairs checked" in result.detail


def test_functional_check_fails_on_wrong_next_state_and_names_the_state():
    table = build_flow_table(_compile(LATCH))
    result = run_functional_check(_wrong_next_netlist(), FUNCS, table, _assignment())
    assert result.status is CheckStatus.FAILED
    assert result.name == FUNCTIONAL_CHECK_NAME
    # The failure names the total state and the input that changed.
    assert "IDLE" in result.detail
    assert "expected next" in result.detail and "got next" in result.detail


def test_functional_check_fails_on_wrong_output():
    # Keep the next-state correct, drive q from s_0 instead of !s_0.
    netlist = MappedNetlist(
        top="async_latch",
        cells=(
            _cell("inv_req", "INV", {"A": "req", "Y": "nreq"}),
            _cell("inv_s0", "INV", {"A": "s_0", "Y": "ns0"}),
            _cell("and1", "AND2", {"A": "s_0", "B": "nreq", "Y": "t1"}),
            _cell("and2", "AND2", {"A": "ns0", "B": "ack", "Y": "t2"}),
            _cell("or1", "OR2", {"A": "t1", "B": "t2", "Y": "s_0"}),
            _cell("buf", "BUF", {"A": "s_0", "Y": "q"}),
        ),
        inputs=("req", "ack"),
        outputs=("q",),
    )
    table = build_flow_table(_compile(LATCH))
    result = run_functional_check(netlist, FUNCS, table, _assignment())
    assert result.status is CheckStatus.FAILED
    assert "outputs" in result.detail


def test_too_large_reports_not_applicable_with_reason():
    table = build_flow_table(_compile(LATCH))
    # The cap is configurable for the test; 0 forces the not-applicable path.
    result = run_functional_check(
        _correct_netlist(), FUNCS, table, _assignment(), max_pairs=0
    )
    assert result.status is CheckStatus.NOT_APPLICABLE
    assert result.status is not CheckStatus.PASSED
    assert "exceed the enumeration cap" in result.detail
    assert "not exhaustively simulated" in result.detail


def test_not_applicable_never_reads_as_a_pass():
    report = VerificationReport(
        checks=[
            CheckResult("hazard (ternary)", CheckStatus.PASSED, kind="hazard"),
            CheckResult("hazard (glitch sim)", CheckStatus.PASSED, kind="hazard"),
            CheckResult(
                FUNCTIONAL_CHECK_NAME,
                CheckStatus.NOT_APPLICABLE,
                "10 pairs exceed the enumeration cap 9; not exhaustively simulated",
                kind="simulation",
            ),
        ]
    )
    result = AsyncPipelineResult(
        flow_table=build_flow_table(_compile(LATCH)),
        assignment=_assignment(),
        covers=CoverResult(width=1, input_names=("req", "ack"), state_names=("s_0",), covers=()),
        report=report,
        _emitted=EmittedNetlist(netlist=_correct_netlist(), verilog="", json=""),
    )
    assert result.hazard_passed is False
    with pytest.raises(HazardFailed, match="not applicable"):
        result.netlist()


def test_functional_check_generalises_to_multi_bit_state_codes():
    # A 3-state machine needs a width-2 SVC code (A=00, B=01, C=11); this pins
    # the multi-bit next-state comparison and the code->state reverse lookup,
    # which no committed 2-state design exercises.
    compiled = _compile(CHAIN3)
    table = build_flow_table(compiled)
    assignment = Assignment(codes={"A": 0, "B": 1, "C": 3}, width=2)
    netlist = MappedNetlist(
        top="chain3",
        cells=(
            _cell("i_s1", "INV", {"A": "s_1", "Y": "ns1"}),
            _cell("o_x", "OR2", {"A": "s_1", "B": "x", "Y": "s1_or_x"}),
            _cell("a1", "AND2", {"A": "s_0", "B": "s1_or_x", "Y": "s_1"}),
            _cell("a2", "AND2", {"A": "ns1", "B": "x", "Y": "t2"}),
            _cell("a3", "AND2", {"A": "s_1", "B": "s_0", "Y": "t3"}),
            _cell("o0", "OR2", {"A": "t2", "B": "t3", "Y": "s_0"}),
            _cell("a4", "AND2", {"A": "s_1", "B": "s_0", "Y": "y"}),
        ),
        inputs=("x",),
        outputs=("y",),
    )
    result = run_functional_check(netlist, FUNCS, table, assignment)
    assert result.status is CheckStatus.PASSED, result.detail
    assert "3 total-state/input-change pairs checked" in result.detail


def test_pipeline_injection_fails_functional_check_and_gates_netlist(monkeypatch):
    # A stage-4 bug that produces a wrong-but-hazard-free cover must now fail the
    # verification and yield no netlist — the acceptance criterion this package
    # exists for.  The fault is injected by zeroing the next-state cover (a
    # dropped-cube analogue that is deterministic under a fake solver).
    def _break_next_cover(original):
        def wrapper(*args, **kwargs):
            result = original(*args, **kwargs)
            covers = [
                replace(cover, cubes=()) if cover.kind == "next" else cover
                for cover in result.covers
            ]
            return replace(result, covers=tuple(covers))

        return wrapper

    monkeypatch.setattr(backend, "build_covers", _break_next_cover(backend.build_covers))

    compiled = _compile(LATCH)
    result = run_async_pipeline(
        compiled, _FakeZ3(), workdir=".gpout/async_func_inject", cell_functions=FUNCS
    )
    statuses = {c.name: c.status.value for c in result.hazard_checks}
    assert statuses[FUNCTIONAL_CHECK_NAME] == "failed", statuses
    assert result.hazard_passed is False
    with pytest.raises(HazardFailed, match="functional"):
        result.netlist()


class _Result:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class _FakeZ3:
    """Answers assignment (sat, IDLE=1/BUSY=0) and cover (sat, all candidates)."""

    def available(self, name: str) -> bool:
        return name == "z3"

    def run(self, argv, cwd, timeout=600):
        script = open(argv[2]).read()
        if "bvxor" in script:
            return _Result(stdout="sat\n((s_IDLE #b1)\n (s_BUSY #b0))")
        n = script.count("(declare-const x_")
        vals = " ".join(f"(x_{i} true)" for i in range(n))
        return _Result(stdout=f"sat\n(({vals}))")
