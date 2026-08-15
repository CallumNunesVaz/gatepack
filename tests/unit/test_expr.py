"""Tests for the design.yaml expression language (gatepack.frontend.expr)."""

from __future__ import annotations

import pytest

from gatepack.frontend import expr


def test_parse_precedence():
    assert expr.parse("a | b & c") == expr.Bin("|", expr.Var("a"), expr.Bin("&", expr.Var("b"), expr.Var("c")))


def test_free_vars():
    ast = expr.parse("(a & !b) | c")
    assert expr.free_vars(ast) == {"a", "b", "c"}


def test_state_eq():
    ast = expr.parse("state == RUNNING")
    assert ast == expr.StateEq("RUNNING")
    assert expr.states_referenced(ast) == {"RUNNING"}
    assert expr.free_vars(ast) == set()


def test_evaluate_combinational():
    ast = expr.parse("a & !b")
    assert expr.evaluate(ast, {"a": True, "b": False}) is True
    assert expr.evaluate(ast, {"a": True, "b": True}) is False


def test_evaluate_constants():
    assert expr.evaluate(expr.parse("1"), {}) is True
    assert expr.evaluate(expr.parse("0"), {}) is False


def test_state_eq_has_no_combinational_value():
    with pytest.raises(expr.ExprError, match="combinational"):
        expr.evaluate(expr.parse("state == X"), {})


def test_expand_substitutes_named_expressions():
    defs = {"fault": expr.parse("a | b")}
    guard = expr.expand(expr.parse("fault & c"), defs)
    assert expr.evaluate(guard, {"a": True, "b": False, "c": True}) is True


def test_expand_detects_cycle():
    defs = {"a": expr.parse("b"), "b": expr.parse("a")}
    with pytest.raises(expr.ExprError, match="cyclic"):
        expr.expand(expr.parse("a"), defs)


def test_to_verilog_maps_signals():
    ast = expr.parse("arm & !fault")
    out = expr.to_verilog(ast, {"arm": "arm_i", "fault": "fault"}, {})
    assert out == "(arm_i & (~fault))"


def test_to_verilog_state_eq_one_hot():
    out = expr.to_verilog(expr.parse("state == RUNNING"), {}, {"RUNNING": "state_RUNNING"})
    assert out == "state_RUNNING"


@pytest.mark.parametrize(
    "bad",
    ["", "a &", "& a", "(a", "a)", "state == ", "state RUNNING", "a b", "a = b", "a == b"],
)
def test_parse_rejects(bad):
    with pytest.raises(expr.ExprError):
        expr.parse(bad)


def test_constant_must_be_binary():
    with pytest.raises(expr.ExprError, match="0 or 1"):
        expr.parse("2")
