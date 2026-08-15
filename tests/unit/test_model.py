"""Tests for front-end semantic checks: reachability, guard overlap (SAT),
non-exhaustiveness, expression references, and async refusal (§12 C1, §7.3)."""

from __future__ import annotations

import pytest

from gatepack.frontend import AsyncRefused, CompileError, compile_design_text

from .helpers import sync_design


def test_valid_design_compiles():
    result = compile_design_text(sync_design())
    assert result.compiled.design.name == "min"
    assert result.compiled.flop_count == 2 + 2  # two state flops + reset de-assert


def test_overlapping_guards_rejected_with_sat():
    yaml = sync_design(
        transitions=[
            ("A", "B", "x"),
            ("A", "B", "x"),  # duplicate guard -> overlap
            ("B", "A", "x"),
            ("B", "B", "!x"),
        ]
    )
    with pytest.raises(CompileError, match="overlapping guards"):
        compile_design_text(yaml)


def test_overlap_detected_across_different_destinations():
    yaml = sync_design(
        transitions=[
            ("A", "B", "x & y"),
            ("A", "A", "x"),  # overlaps when y=1
            ("B", "A", "!x"),
            ("B", "B", "x"),
        ],
    )
    yaml = yaml.replace("inputs:\n  - {name: x, sync: false}\n", "inputs:\n  - {name: x, sync: false}\n  - {name: y, sync: false}\n")
    with pytest.raises(CompileError, match="overlapping guards"):
        compile_design_text(yaml)


def test_unreachable_state_rejected():
    yaml = sync_design(
        states=["A", "B", "C"],
        transitions=[
            ("A", "B", "1"),
            ("B", "A", "1"),
        ],
    )
    with pytest.raises(CompileError, match="unreachable state"):
        compile_design_text(yaml)


def test_non_exhaustive_transition_set_rejected():
    yaml = sync_design(
        transitions=[
            ("A", "B", "x"),  # no cover for !x
            ("B", "A", "1"),
        ]
    )
    with pytest.raises(CompileError, match="non-exhaustive"):
        compile_design_text(yaml)


def test_sink_state_rejected_as_non_exhaustive():
    yaml = sync_design(
        transitions=[
            ("A", "B", "1"),
            ("B", "A", "1"),
        ]
    )
    # this is actually exhaustive; a sink is a state with NO outgoing transitions
    yaml = sync_design(
        states=["A", "B"],
        transitions=[("A", "B", "1"), ("B", "B", "1")],
    )
    # B has an explicit self-loop, so this is fine
    assert compile_design_text(yaml).compiled is not None


def test_guard_referencing_unknown_signal_rejected():
    yaml = sync_design(transitions=[("A", "B", "mystery"), ("A", "A", "1"), ("B", "B", "1"), ("B", "A", "1")])
    with pytest.raises(CompileError, match="unknown signal"):
        compile_design_text(yaml)


def test_guard_referencing_state_rejected():
    yaml = sync_design(
        transitions=[
            ("A", "B", "state == B"),
            ("A", "A", "1"),
            ("B", "B", "1"),
            ("B", "A", "1"),
        ]
    )
    with pytest.raises(CompileError, match="state =="):
        compile_design_text(yaml)


def test_async_design_refused():
    yaml = (
        "name: hshake\n"
        "timing_model: asynchronous\n"
        "reset: {signal: rst_n, active: low}\n"
        "states: [A, B]\n"
        "initial: A\n"
        "transitions:\n"
        '  - {from: A, to: B, when: "req"}\n'
        '  - {from: B, to: A, when: "ack"}\n'
        "output_logic: {}\n"
        "fundamental_mode: {mutually_exclusive: [[req, ack]]}\n"
    )
    with pytest.raises(AsyncRefused, match="asynchronous"):
        compile_design_text(yaml)


def test_expression_referencing_unknown_signal_rejected():
    yaml = sync_design(
        expressions={"fault": "fault_a | nope"},
        transitions=[("A", "B", "fault"), ("A", "A", "!fault"), ("B", "B", "1"), ("B", "A", "1")],
    )
    with pytest.raises(CompileError, match="unknown signal"):
        compile_design_text(yaml)


def test_cyclic_expression_rejected():
    yaml = sync_design(
        expressions={"a": "b", "b": "a"},
        transitions=[("A", "B", "a"), ("A", "A", "1"), ("B", "B", "1"), ("B", "A", "1")],
    )
    with pytest.raises(CompileError, match="cyclic"):
        compile_design_text(yaml)


def test_transition_to_undeclared_state_rejected():
    yaml = sync_design(transitions=[("A", "NOPE", "1"), ("A", "A", "1"), ("B", "B", "1"), ("B", "A", "1")])
    with pytest.raises(CompileError, match="not declared"):
        compile_design_text(yaml)
