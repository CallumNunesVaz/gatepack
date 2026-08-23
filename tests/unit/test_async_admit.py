"""Tests for stage 1 — asynchronous admission (refusals before any work).

Every refusal path is exercised and asserted to *name the specific construct* at
fault, not a generic message (§7.3: refusals are the deliverable as much as the
synthesis is).
"""

from __future__ import annotations

import pytest

from gatepack.frontend.errors import AsyncRefused
from gatepack.frontend.schema import Design
from gatepack.synth.async_.admit import ASYNC_STATE_CAP, admit


def _design(**overrides) -> Design:
    base = {
        "name": "admit_test",
        "timing_model": "asynchronous",
        "reset": {"signal": "rst_n", "active": "low"},
        "states": ["A", "B"],
        "initial": "A",
        "transitions": [
            {"from": "A", "to": "B", "when": "x"},
            {"from": "A", "to": "A", "when": "!x"},
            {"from": "B", "to": "A", "when": "!x"},
            {"from": "B", "to": "B", "when": "x"},
        ],
        "inputs": [{"name": "x", "sync": False}],
        "fundamental_mode": {"mutually_exclusive": [["x"]]},
    }
    base.update(overrides)
    return Design.model_validate(base)


def test_missing_fundamental_mode_refused():
    design = _design()
    design.fundamental_mode = None
    with pytest.raises(AsyncRefused, match="fundamental_mode"):
        admit(design)


def test_empty_mutually_exclusive_refused():
    design = _design(fundamental_mode={"mutually_exclusive": []})
    with pytest.raises(AsyncRefused, match="mutually_exclusive"):
        admit(design)


def test_clock_block_refused_names_signal():
    design = _design(clock={"signal": "clk", "freq_hz": 1, "source": "OSC"})
    with pytest.raises(AsyncRefused, match="clk"):
        admit(design)


def test_state_count_above_cap_refused():
    states = [f"S{i}" for i in range(ASYNC_STATE_CAP + 1)]
    design = _design(
        states=states,
        initial="S0",
        transitions=[
            {"from": s, "to": s, "when": "1"} for s in states
        ],
    )
    with pytest.raises(AsyncRefused, match=f"{ASYNC_STATE_CAP + 1} states"):
        admit(design)


def test_uncovered_input_refused_names_input():
    design = _design(
        inputs=[{"name": "x", "sync": False}, {"name": "y", "sync": False}],
        fundamental_mode={"mutually_exclusive": [["x"]]},
    )
    with pytest.raises(AsyncRefused, match="'y'"):
        admit(design)


def test_group_naming_undeclared_input_refused():
    design = _design(
        inputs=[{"name": "x", "sync": False}],
        fundamental_mode={"mutually_exclusive": [["x", "mystery"]]},
    )
    with pytest.raises(AsyncRefused, match="mystery"):
        admit(design)


def test_valid_async_design_admitted():
    # A design that passes admission is not refused here (the front-end's later
    # generic refusal is a separate concern).
    admit(_design())


def test_refusal_message_carries_design_name():
    design = _design(name="named_design")
    design.fundamental_mode = None
    with pytest.raises(AsyncRefused, match="named_design"):
        admit(design)
