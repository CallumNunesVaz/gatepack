"""Tests for Johnson-counter topology detection (gatepack.frontend.johnson)."""

from __future__ import annotations

from gatepack.frontend import johnson


def test_simple_cycle_suggested():
    transitions = [("A", "B"), ("B", "C"), ("C", "A")]
    suggestion = johnson.suggest_johnson(["A", "B", "C"], transitions, "A")
    assert suggestion is not None
    assert "A -> B -> C -> A" in suggestion
    assert "JOHN10" in suggestion


def test_branching_not_suggested():
    transitions = [("A", "B"), ("A", "C"), ("B", "A"), ("C", "A")]
    assert johnson.suggest_johnson(["A", "B", "C"], transitions, "A") is None


def test_state_with_no_outgoing_not_suggested():
    transitions = [("A", "B"), ("B", "A")]
    assert johnson.suggest_johnson(["A", "B", "C"], transitions, "A") is None


def test_empty_transitions_not_suggested():
    assert johnson.suggest_johnson(["A"], [], "A") is None
