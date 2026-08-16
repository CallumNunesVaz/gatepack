"""Tests for SCOAP testability analysis (gatepack.analysis.scoap, §13.1).

All netlists are hand-written (no Yosys); the parser is exercised elsewhere.
The values pinned here are the standard SCOAP recurrences, so a change to the
recurrence (not just a refactor) must fail one of these.
"""

from __future__ import annotations

from gatepack.analysis.scoap import (
    UNOBSERVABLE,
    ScoapReport,
    analyze_scoap,
)

from .cells import cell, netlist, part


def _inv():
    return part("INV", function="!A", inputs=1)


def test_primary_inputs_have_unit_controllability():
    and2 = part("AND2", function="A&B", inputs=2)
    nl = netlist(
        "top",
        [cell("g", and2, {"A": "a", "B": "b", "Y": "y"})],
        inputs=("a", "b"),
        outputs=("y",),
    )
    r = analyze_scoap(nl)
    by_net = {n.net: n for n in r.nets}
    assert (by_net["a"].controllability0, by_net["a"].controllability1) == (1, 1)
    assert (by_net["b"].controllability0, by_net["b"].controllability1) == (1, 1)
    assert by_net["y"].observability == 0  # primary output


def test_gate_controllability_standard_recurrences():
    # (function, expected CC0, expected CC1) for a 2-input gate, output on y.
    cases = [
        ("A&B", 2, 3),
        ("A|B", 3, 2),
        ("!(A&B)", 3, 2),
        ("A^B", 3, 3),
    ]
    for func, cc0, cc1 in cases:
        gate = part("G", function=func, inputs=2)
        nl = netlist(
            "top",
            [cell("g", gate, {"A": "a", "B": "b", "Y": "y"})],
            inputs=("a", "b"),
            outputs=("y",),
        )
        by_net = {n.net: n for n in analyze_scoap(nl).nets}
        assert (by_net["y"].controllability0, by_net["y"].controllability1) == (
            cc0,
            cc1,
        ), func


def test_observability_propagates_backwards():
    and2 = part("AND2", function="A&B", inputs=2)
    nl = netlist(
        "top",
        [cell("g", and2, {"A": "a", "B": "b", "Y": "y"})],
        inputs=("a", "b"),
        outputs=("y",),
    )
    by_net = {n.net: n for n in analyze_scoap(nl).nets}
    # CO(a) = CO(y) + 1 + CC1(b) = 0 + 1 + 1 = 2
    assert by_net["a"].observability == 2
    assert by_net["b"].observability == 2


def test_dangling_net_is_unobservable():
    nl = netlist(
        "top",
        [cell("g", _inv(), {"A": "x", "Y": "n1"})],
        inputs=("x",),
        outputs=(),
    )
    r = analyze_scoap(nl)
    assert r.unobservable == ("n1", "x")
    assert all(n.observability is None for n in r.nets)


def test_delta_table_unobservable_first_and_wire_shape():
    # a -> y is observable; b -> n2 is dangling (unobservable).  The unobservable
    # branch must top the delta table, and the wire entries carry the api.ts keys.
    inv = _inv()
    nl = netlist(
        "top",
        [
            cell("g0", inv, {"A": "a", "Y": "y"}),
            cell("g1", inv, {"A": "b", "Y": "n2"}),
        ],
        inputs=("a", "b"),
        outputs=("y",),
    )
    r = analyze_scoap(nl)
    assert r.delta[0].net == "n2"
    assert r.unobservable == ("b", "n2")
    wire = r.to_wire()
    assert set(wire[0]) == {"net", "controllability0", "controllability1", "observability"}
    assert all(isinstance(e["observability"], int) for e in wire)
    assert wire[0]["observability"] == UNOBSERVABLE


def test_unobservable_wire_uses_sentinel_not_null():
    nl = netlist(
        "top",
        [cell("g", _inv(), {"A": "x", "Y": "n1"})],
        inputs=("x",),
        outputs=(),
    )
    r = analyze_scoap(nl)
    for entry in r.to_wire():
        assert entry["observability"] == UNOBSERVABLE


def test_sequential_controllability_for_flop():
    # DFF: SC0(Q) = SC1(Q) = 1 + CC1(CK) + CC0/1(D) = 1 + 1 + 1 = 3
    dff = part("DFF", tier="F", function=None, inputs=2)
    nl = netlist(
        "top",
        [cell("f0", dff, {"D": "a", "CK": "clk", "Q": "y"})],
        inputs=("a", "clk"),
        outputs=("y",),
    )
    r = analyze_scoap(nl)
    by_net = {n.net: n for n in r.nets}
    assert (by_net["y"].controllability0, by_net["y"].controllability1) == (3, 3)
    # SO(D) = CO(Q) + 1 + CC1(CK) = 0 + 1 + 1 = 2
    assert by_net["a"].observability == 2
    # the clock is a control signal: not listed as unobservable
    assert "clk" not in r.unobservable


def test_combinational_loop_terminates_and_is_marked():
    # Two inverters in a ring: a genuine combinational cycle.  The recurrence
    # must terminate (never recurse forever) and mark the loop nets unknown.
    inv = _inv()
    nl = netlist(
        "top",
        [
            cell("g1", inv, {"A": "n2", "Y": "n1"}),
            cell("g2", inv, {"A": "n1", "Y": "n2"}),
        ],
        inputs=(),
        outputs=("n1",),
    )
    r = analyze_scoap(nl)
    by_net = {n.net: n for n in r.nets}
    assert by_net["n1"].controllability0 is None
    assert by_net["n2"].controllability0 is None
