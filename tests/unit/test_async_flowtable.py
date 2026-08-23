"""Tests for stage 2 — primitive flow table and fundamental-mode admissibility."""

from __future__ import annotations

import pytest

from gatepack.frontend import model as model_mod
from gatepack.frontend import yaml_subset
from gatepack.frontend.errors import AsyncRefused
from gatepack.frontend.schema import Design
from gatepack.synth.async_.flowtable import build_flow_table, check_admissibility

LATCH = """
name: async_latch
timing_model: asynchronous
reset: {signal: rst_n, active: low}
inputs:
  - {name: req, sync: false}
  - {name: ack, sync: false}
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

TWO_INPUT = """
name: async_two_input
timing_model: asynchronous
reset: {signal: rst_n, active: low}
inputs:
  - {name: x, sync: false}
  - {name: y, sync: false}
states: [A, B, C]
initial: A
transitions:
  - {from: A, to: B, when: "x & y"}
  - {from: A, to: A, when: "!x & !y"}
  - {from: A, to: C, when: "x & !y"}
  - {from: A, to: C, when: "!x & y"}
  - {from: B, to: B, when: "1"}
  - {from: C, to: C, when: "1"}
output_logic: {}
fundamental_mode: {mutually_exclusive: [[x, y]]}
"""


def _compile(yaml_text: str):
    node = yaml_subset.parse(yaml_text)
    data = yaml_subset.to_python(node)
    design = Design.model_validate(data)
    return model_mod.compile_design(design, source_name="t.yaml", provenance={})


def test_flow_table_has_expected_transitions():
    table = build_flow_table(_compile(LATCH))
    assert table.states == ("IDLE", "BUSY")
    assert table.input_names == ("req", "ack")
    assert table.transitions == (("BUSY", "IDLE"), ("IDLE", "BUSY"))


def test_flow_table_marks_stable_entries():
    table = build_flow_table(_compile(LATCH))
    # combos (req, ack): (0,0),(0,1),(1,0),(1,1).  IDLE is stable when req == 0.
    assert table.stable_combos("IDLE") == (0, 1)
    assert table.stable_combos("BUSY") == (0, 2)


def test_flow_table_outputs_are_moore():
    table = build_flow_table(_compile(LATCH))
    idle = table.states.index("IDLE")
    for ci in range(len(table.combos)):
        assert dict(table.outputs[idle][ci]) == {"q": False}
    busy = table.states.index("BUSY")
    for ci in range(len(table.combos)):
        assert dict(table.outputs[busy][ci]) == {"q": True}


def test_latch_is_fundamental_mode_admissible():
    table = build_flow_table(_compile(LATCH))
    check_admissibility(_compile(LATCH), table)  # does not raise


def test_two_input_change_refused_naming_both_inputs():
    compiled = _compile(TWO_INPUT)
    table = build_flow_table(compiled)
    with pytest.raises(AsyncRefused, match="A -> B") as excinfo:
        check_admissibility(compiled, table)
    message = str(excinfo.value)
    assert "'x'" in message and "'y'" in message  # names BOTH inputs


def test_no_stable_state_refused():
    yaml = """
name: async_unstable
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
fundamental_mode: {mutually_exclusive: [[x]]}
"""
    # A is stable at !x, so this is admissible; build a genuinely unstable state
    # by removing the self-loop from B and making B transition on every input.
    yaml = yaml.replace('  - {from: B, to: B, when: "1"}\n',
                        '  - {from: B, to: A, when: "1"}\n')
    compiled = _compile(yaml)
    table = build_flow_table(compiled)
    with pytest.raises(AsyncRefused, match="no stable input"):
        check_admissibility(compiled, table)
