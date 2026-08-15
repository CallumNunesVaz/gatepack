"""Tests for the pydantic design.yaml schema (gatepack.frontend.schema)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from gatepack.frontend.schema import Design


def _design(**overrides) -> Design:
    base = dict(
        name="test",
        timing_model="synchronous",
        clock={"signal": "clk", "freq_hz": 1000, "source": "OSC"},
        reset={"signal": "rst_n", "active": "low"},
        states=["A", "B"],
        initial="A",
    )
    base.update(overrides)
    return Design.model_validate(base)


def test_minimal_valid():
    d = _design()
    assert d.constraints.vcc == 3.3
    assert d.encoding == "one_hot"


def test_default_vcc_is_3_3_not_1_8():
    # §21.1: the §10.2 example's `vcc: 1.8` is a known stale value.
    assert _design().constraints.vcc == 3.3


def test_initial_must_be_a_state():
    with pytest.raises(ValidationError, match="initial"):
        _design(initial="NOPE")


def test_duplicate_state_names_rejected():
    with pytest.raises(ValidationError, match="duplicate state"):
        _design(states=["A", "A"], initial="A")


def test_duplicate_input_names_rejected():
    with pytest.raises(ValidationError, match="duplicate input"):
        _design(inputs=[{"name": "x"}, {"name": "x"}])


def test_reserved_verilog_keyword_name_rejected():
    with pytest.raises(ValidationError, match="Verilog identifier"):
        _design(name="module")


def test_synchronous_requires_clock():
    with pytest.raises(ValidationError, match="clock"):
        _design(clock=None)


def test_unknown_top_level_key_rejected():
    with pytest.raises(ValidationError):
        _design(bogus="x")


def test_output_logic_must_be_declared_output():
    with pytest.raises(ValidationError, match="declared output"):
        _design(output_logic={"undeclared": "1"})


def test_safe_state_values_constrained():
    with pytest.raises(ValidationError, match="0, 1 or 'any'"):
        _design(
            outputs=[{"name": "o"}],
            safe_state={"o": "yes"},
        )


def test_bad_timing_model_rejected():
    with pytest.raises(ValidationError):
        _design(timing_model="mealy")


def test_bad_encoding_rejected():
    with pytest.raises(ValidationError):
        _design(encoding="grey")
