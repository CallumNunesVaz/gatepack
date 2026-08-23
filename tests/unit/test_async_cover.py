"""Tests for stage 4 — hazard-free cover and the ≤3-literal limit."""

from __future__ import annotations

import pytest

from gatepack.frontend import model as model_mod
from gatepack.frontend import yaml_subset
from gatepack.frontend.errors import AsyncRefused
from gatepack.frontend.schema import Design
from gatepack.synth.async_.assign import Assignment
from gatepack.synth.async_.cover import (
    _candidate_implicants,
    _solve_cover,
    build_covers,
)
from gatepack.synth.async_.flowtable import build_flow_table

FOUR_LITERAL = """
name: async_4literal
timing_model: asynchronous
reset: {signal: rst_n, active: low}
inputs: [{name: a, sync: false}, {name: b, sync: false}, {name: c, sync: false}, {name: d, sync: false}]
states: [S0, S1]
initial: S0
transitions:
  - {from: S0, to: S1, when: "a"}
  - {from: S0, to: S0, when: "!a"}
  - {from: S1, to: S0, when: "!a"}
  - {from: S1, to: S1, when: "a"}
outputs: [{name: q}]
output_logic: {q: "a & b & c & d"}
fundamental_mode: {mutually_exclusive: [[a, b], [c, d]]}
"""


def _compile(yaml_text: str):
    node = yaml_subset.parse(yaml_text)
    data = yaml_subset.to_python(node)
    design = Design.model_validate(data)
    return model_mod.compile_design(design, source_name="t.yaml", provenance={})


class _Result:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class _BoomRunner:
    """A runner that fails the test if z3 is ever invoked."""

    def __init__(self):
        self.calls: list[str] = []

    def available(self, name: str) -> bool:
        return name == "z3"

    def run(self, argv, cwd, timeout=600):
        self.calls.append(argv[2])
        raise AssertionError("z3 should not be needed for the 4-literal refusal")


class _CoverZ3:
    """Unsatisfiable at k=1, satisfiable (all candidates) at k=2."""

    def __init__(self):
        self.calls: list[str] = []
        self._n = 0

    def available(self, name: str) -> bool:
        return name == "z3"

    def run(self, argv, cwd, timeout=600):
        self.calls.append(argv[2])
        self._n += 1
        if self._n == 1:
            return _Result(stdout="unsat")
        script = open(argv[2]).read()
        n = script.count("(declare-const x_")
        vals = " ".join(f"(x_{i} true)" for i in range(n))
        return _Result(stdout=f"sat\n(({vals}))")


def test_candidate_implicants_for_and_gate():
    # f = A & B over two variables; ON = {11}, OFF = {00, 01, 10}.
    candidates = _candidate_implicants(2, {(1, 1)}, {(0, 0), (0, 1), (1, 0)})
    assert candidates == [(1, 1)]


def test_four_literal_term_refused_naming_term_and_function():
    compiled = _compile(FOUR_LITERAL)
    table = build_flow_table(compiled)
    assignment = Assignment(codes={"S0": 0, "S1": 1}, width=1)
    runner = _BoomRunner()
    with pytest.raises(AsyncRefused, match="function 'q'") as excinfo:
        build_covers(compiled, table, assignment, runner, workdir=".gpout")
    message = str(excinfo.value)
    assert "a & b & c & d" in message  # names the offending term
    assert "more than 3 literals" in message
    assert runner.calls == []  # refused before any solver call


def test_solve_cover_iterates_cardinality_bound():
    # Two ON minterms each covered by a distinct candidate -> k=1 unsat, k=2 sat.
    candidates = [(1, -1), (-1, 1)]
    on = {(1, 0), (0, 1)}
    runner = _CoverZ3()
    selected = _solve_cover(candidates, on, set(), runner, ".gpout", "cover_test")
    assert selected == (0, 1)
    assert len(runner.calls) == 2


def test_solve_cover_empty_on_set_needs_no_solver():
    runner = _CoverZ3()
    assert _solve_cover([], set(), set(), runner, ".gpout", "empty") == ()
    assert runner.calls == []


def test_solve_cover_refuses_uncoverable_minterm():
    # A candidate that cannot cover one of the ON minterms must be refused
    # without invoking the solver (or silently dropping the constraint).
    candidates = [(1, -1, -1)]  # covers only minterms with var0 == 1
    on = {(1, 0, 0), (0, 1, 0)}  # (0, 1, 0) is uncoverable
    runner = _CoverZ3()
    assert _solve_cover(candidates, on, set(), runner, ".gpout", "uncov") is None
    assert runner.calls == []
