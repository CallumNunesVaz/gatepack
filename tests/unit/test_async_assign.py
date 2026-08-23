"""Tests for stage 3 — single-variable-change state assignment (z3).

The z3 binary is not installed in the development venv, so these tests inject a
fake runner that reads the generated SMT-LIB2 script and returns scripted
``sat``/``unsat`` output.  The real z3 run is covered by the toolchain layer.
"""

from __future__ import annotations

import pytest

from gatepack.frontend import model as model_mod
from gatepack.frontend import yaml_subset
from gatepack.frontend.errors import AsyncRefused
from gatepack.frontend.schema import Design
from gatepack.synth.async_ import smt
from gatepack.synth.async_.assign import assign_state_codes, build_script
from gatepack.synth.async_.flowtable import build_flow_table

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
output_logic: {}
fundamental_mode: {mutually_exclusive: [[req, ack]]}
"""

CYCLE = """
name: async_cycle
timing_model: asynchronous
reset: {signal: rst_n, active: low}
inputs: [{name: x, sync: false}]
states: [A, B, C]
initial: A
transitions:
  - {from: A, to: B, when: "x"}
  - {from: A, to: A, when: "!x"}
  - {from: B, to: C, when: "x"}
  - {from: B, to: B, when: "!x"}
  - {from: C, to: A, when: "x"}
  - {from: C, to: C, when: "!x"}
output_logic: {}
fundamental_mode: {mutually_exclusive: [[x]]}
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


class _FakeZ3:
    """A runner whose ``run`` reads the .smt2 script and returns scripted output."""

    def __init__(self, responder, available=True):
        self._responder = responder
        self._available = available
        self.calls: list[str] = []

    def available(self, name: str) -> bool:
        return name == "z3" and self._available

    def run(self, argv, cwd, timeout=600):
        self.calls.append(argv[2])
        script = open(argv[2]).read()
        return _Result(stdout=self._responder(script))


def test_build_script_is_byte_deterministic():
    states = ("A", "B", "C")
    transitions = (("A", "B"), ("B", "C"))
    assert build_script(states, transitions, 2) == build_script(states, transitions, 2)


def test_build_script_uses_fixed_seed_and_hamming_constraints():
    script = build_script(("A", "B"), (("A", "B"),), 2)
    assert ":smt.random_seed 0" in script
    assert "bvxor" in script
    assert "bvand" in script
    assert "(distinct s_A s_B)" in script


def test_parse_model_decodes_bitvectors():
    assert smt.parse_model("sat\n((s_A #b101)\n (s_B #x01))") == {"s_A": 5, "s_B": 1}


def test_assign_parses_sat_model():
    table = build_flow_table(_compile(LATCH))
    fake = _FakeZ3(
        lambda script: "sat\n((s_IDLE #b1)\n (s_BUSY #b0))"
    )
    assignment = assign_state_codes(table, fake, workdir=".gpout", design_name="latch")
    assert assignment.codes == {"IDLE": 1, "BUSY": 0}
    assert assignment.width == 1
    assert fake.calls  # z3 was actually invoked


def test_assign_refuses_on_persistent_unsat_naming_conflicts():
    table = build_flow_table(_compile(CYCLE))
    # A 3-cycle is unsatisfiable at every width, so the fake answers UNSAT only
    # when all three transition constraints are present and SAT otherwise —
    # the deletion-based MUS therefore keeps the whole cycle.
    fake = _FakeZ3(lambda script: "unsat" if script.count("bvxor") >= 3 else "sat")
    with pytest.raises(AsyncRefused, match="A->B") as excinfo:
        assign_state_codes(table, fake, workdir=".gpout", design_name="cycle")
    assert "B->C" in str(excinfo.value)
    assert "C->A" in str(excinfo.value)


def test_assign_refuses_when_z3_missing():
    table = build_flow_table(_compile(LATCH))
    fake = _FakeZ3(lambda script: "sat", available=False)
    with pytest.raises(AsyncRefused, match="z3 not found"):
        assign_state_codes(table, fake, workdir=".gpout", design_name="latch")


def test_single_state_trivial_assignment():
    yaml = """
name: async_one
timing_model: asynchronous
reset: {signal: rst_n, active: low}
inputs: [{name: x, sync: false}]
states: [S]
initial: S
transitions:
  - {from: S, to: S, when: "1"}
output_logic: {}
fundamental_mode: {mutually_exclusive: [[x]]}
"""
    table = build_flow_table(_compile(yaml))
    fake = _FakeZ3(lambda script: "sat\n((s_S #b0))")
    assignment = assign_state_codes(table, fake, workdir=".gpout", design_name="one")
    assert assignment.codes == {"S": 0}
    assert assignment.width == 1
