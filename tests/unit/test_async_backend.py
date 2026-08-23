"""Tests for the asynchronous backend and verify-strategy orchestration."""

from __future__ import annotations

import pytest

from gatepack.frontend import model as model_mod
from gatepack.frontend import yaml_subset
from gatepack.frontend.errors import AsyncRefused
from gatepack.frontend.schema import Design
from gatepack.synth.asynchronous import AsynchronousBackend
from gatepack.synth.async_.assign import Assignment
from gatepack.synth.async_.flowtable import build_flow_table
from gatepack.synth.base import SynthConfig
from gatepack.verify.asynchronous import build_transition_probes, cell_functions_from_liberty

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

NO_FUNDAMENTAL_MODE = """
name: async_bad
timing_model: asynchronous
reset: {signal: rst_n, active: low}
inputs: [{name: x, sync: false}]
states: [A, B]
initial: A
transitions:
  - {from: A, to: B, when: "x"}
  - {from: A, to: A, when: "!x"}
  - {from: B, to: B, when: "1"}
output_logic: {}
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


class _NeverCalledRunner:
    def available(self, name: str) -> bool:
        return name == "z3"

    def run(self, argv, cwd, timeout=600):
        raise AssertionError("z3 must not be reached before admission")


def test_generate_script_still_refuses_with_v0_1_0():
    backend = AsynchronousBackend()
    config = SynthConfig(top="t")
    with pytest.raises(AsyncRefused, match="v0.1.0"):
        backend.generate_script(config)


def test_synthesize_refuses_at_admission_before_any_solver_call():
    compiled = _compile(NO_FUNDAMENTAL_MODE)
    backend = AsynchronousBackend()
    with pytest.raises(AsyncRefused, match="fundamental_mode"):
        backend._synthesize(compiled, _NeverCalledRunner(), workdir=".gpout")


def test_build_transition_probes_from_stable_states_only():
    table = build_flow_table(_compile(LATCH))
    assignment = Assignment(codes={"IDLE": 1, "BUSY": 0}, width=1)
    probes = build_transition_probes(table, assignment)
    # 2 states x 2 stable combos x 2 changing inputs == 8 fundamental-mode probes
    assert len(probes) == 8
    for probe in probes:
        assert probe.changing_input in ("req", "ack")
        assert set(probe.fixed_nets) == {"s_0"}
        assert set(probe.stable_inputs) == {"req", "ack"} - {probe.changing_input}


def test_cell_functions_parsed_from_liberty():
    lib = (
        "library (t) {\n"
        "  cell (INV) {\n"
        "    area : 1.0;\n"
        '    pin(Y) { direction : output; function : "(!A)"; }\n'
        "  }\n"
        "  cell (AND2) {\n"
        "    area : 1.0;\n"
        '    pin(Y) { direction : output; function : "(A & B)"; }\n'
        "  }\n"
        "}\n"
    )
    assert cell_functions_from_liberty(lib) == {"INV": "(!A)", "AND2": "(A & B)"}
