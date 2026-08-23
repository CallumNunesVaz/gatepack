"""Tests for stage 5 — independent hazard verification.

Acceptance-critical: the hand-built hazardous netlist is refused by the ternary
check (5a), the test fails if the X-propagation is weakened, and
``gatepack/verify/hazard.py`` imports nothing from ``gatepack.synth.async_``.
"""

from __future__ import annotations

import ast

from gatepack.netlist import MappedCell, MappedNetlist
from gatepack.verify import hazard
from gatepack.verify.hazard import (
    HazardFinding,
    TransitionProbe,
    _X,
    _ZERO,
    _ONE,
    _Function,
    check_static_hazards,
    evaluate_fixed_point,
)

FUNCS = {"INV": "!A", "AND2": "A&B", "OR2": "A|B"}


def _cell(name, cell, conns):
    directions = (
        {"A": "input", "Y": "output"}
        if cell == "INV"
        else {"A": "input", "B": "input", "Y": "output"}
    )
    return MappedCell(name=name, cell=cell, tier="G", connections=conns, directions=directions)


def _hazardous_netlist() -> MappedNetlist:
    # The classic static-1 hazard: Y = A&B | !A&C with B=C=1.
    return MappedNetlist(
        top="top",
        cells=(
            _cell("inv1", "INV", {"A": "A", "Y": "an"}),
            _cell("and1", "AND2", {"A": "A", "B": "B", "Y": "t1"}),
            _cell("and2", "AND2", {"A": "an", "B": "C", "Y": "t2"}),
            _cell("or1", "OR2", {"A": "t1", "B": "t2", "Y": "Y"}),
        ),
        inputs=("A", "B", "C"),
        outputs=("Y",),
    )


def _probe() -> TransitionProbe:
    return TransitionProbe(changing_input="A", stable_inputs={"B": True, "C": True})


def test_hazard_module_imports_nothing_from_async_synth():
    """Acceptance: the verifier must not share the synthesiser's data structures."""
    source = open("gatepack/verify/hazard.py").read()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "async_" not in alias.name
        elif isinstance(node, ast.ImportFrom):
            assert node.module is None or "async_" not in node.module


def test_hazardous_netlist_refused_by_ternary_check():
    findings = check_static_hazards(_hazardous_netlist(), FUNCS, [_probe()])
    assert len(findings) == 1
    finding = findings[0]
    assert finding.output == "Y"
    assert finding.changing_input == "A"
    assert finding.kind == "static-1"


def test_consensus_term_eliminates_hazard():
    # Adding the consensus term B&C makes the cover hazard-free.
    netlist = MappedNetlist(
        top="top",
        cells=(
            _cell("inv1", "INV", {"A": "A", "Y": "an"}),
            _cell("and1", "AND2", {"A": "A", "B": "B", "Y": "t1"}),
            _cell("and2", "AND2", {"A": "an", "B": "C", "Y": "t2"}),
            _cell("and3", "AND2", {"A": "B", "B": "C", "Y": "t3"}),
            _cell("or1", "OR2", {"A": "t1", "B": "t2", "Y": "o1"}),
            _cell("or2", "OR2", {"A": "o1", "B": "t3", "Y": "Y"}),
        ),
        inputs=("A", "B", "C"),
        outputs=("Y",),
    )
    assert check_static_hazards(netlist, FUNCS, [_probe()]) == ()


def test_x_propagation_is_pessimistic_not_optimistic():
    """Acceptance: weakening X-propagation must fail this test.

    A static hazard is only visible when X propagates pessimistically: X & 1 = X
    and X | X = X.  If someone "fixes" the ternary tables to resolve X optimistically
    (X & 1 = 1), the hazardous netlist above stops being detected.
    """
    and_fn = _Function("A&B")
    assert and_fn.eval_ternary((_X, _ONE)) == _X
    assert and_fn.eval_ternary((_X, _ZERO)) == _ZERO
    assert and_fn.eval_ternary((_ONE, _ONE)) == _ONE
    or_fn = _Function("A|B")
    assert or_fn.eval_ternary((_X, _X)) == _X
    assert or_fn.eval_ternary((_X, _ONE)) == _ONE


def test_binary_evaluation_is_two_valued():
    netlist = _hazardous_netlist()
    v0 = evaluate_fixed_point(netlist, FUNCS, {"A": 0, "B": 1, "C": 1}, ternary=False)
    v1 = evaluate_fixed_point(netlist, FUNCS, {"A": 1, "B": 1, "C": 1}, ternary=False)
    assert v0["Y"] == _ONE and v1["Y"] == _ONE


def test_held_nets_are_not_overwritten():
    # A feedback net listed in the input values must stay held (the loop is cut),
    # not be recomputed by its own driver.
    netlist = MappedNetlist(
        top="top",
        cells=(
            _cell("or1", "OR2", {"A": "A", "B": "s0", "Y": "s0"}),
        ),
        inputs=("A",),
        outputs=(),
    )
    values = evaluate_fixed_point(netlist, FUNCS, {"A": 0, "s0": 0}, ternary=False)
    assert values["s0"] == 0  # held, not driven back to whatever the OR computes


def test_finding_names_output_and_transition():
    finding = HazardFinding(output="Y", changing_input="A", stable_value=1, transition={"A": _X, "B": 1, "C": 1})
    assert finding.output == "Y"
    assert finding.kind == "static-1"
