"""Tests for single stuck-at fault analysis (gatepack.analysis.faults, §13.2).

All netlists are hand-written (no Yosys); the parser is exercised elsewhere.
The collapsed counts are the textbook equivalence+dominance figures, so a change
to the collapsing must fail one of these.
"""

from __future__ import annotations

from gatepack.analysis.faults import analyze_faults, enumerate_faults

from .cells import cell, netlist, part


def test_and2_collapses_to_three():
    and2 = part("AND2", function="A&B", inputs=2)
    nl = netlist(
        "top",
        [cell("g", and2, {"A": "a", "B": "b", "Y": "y"})],
        inputs=("a", "b"),
        outputs=("y",),
    )
    uncollapsed, collapsed = enumerate_faults(nl)
    # 3 nets + 3 pins, 2 faults each
    assert uncollapsed == 2 * (3 + 3)
    # AND2: input sa0 ≡ output sa0 (one rep), output sa1 dominated by input sa1
    assert len(collapsed) == 3


def test_xor2_does_not_collapse():
    xor2 = part("XOR2", function="A^B", inputs=2)
    nl = netlist(
        "top",
        [cell("g", xor2, {"A": "a", "B": "b", "Y": "y"})],
        inputs=("a", "b"),
        outputs=("y",),
    )
    _uncollapsed, collapsed = enumerate_faults(nl)
    # XOR has no equivalence or dominance: all six net faults survive.
    assert len(collapsed) == 6


def test_inverter_collapses_to_two():
    inv = part("INV", function="!A", inputs=1)
    nl = netlist(
        "top",
        [cell("g", inv, {"A": "a", "Y": "y"})],
        inputs=("a",),
        outputs=("y",),
    )
    _uncollapsed, collapsed = enumerate_faults(nl)
    # A sa0 ≡ Y sa1, A sa1 ≡ Y sa0 -> two collapsed faults.
    assert len(collapsed) == 2


def test_all_faults_detected_on_observable_and2():
    and2 = part("AND2", function="A&B", inputs=2)
    nl = netlist(
        "top",
        [cell("g", and2, {"A": "a", "B": "b", "Y": "y"})],
        inputs=("a", "b"),
        outputs=("y",),
    )
    r = analyze_faults(nl, None)
    assert r.exhaustive is True
    assert r.detected == 3
    assert r.redundant == 0
    assert r.untestable == 0


def test_dangling_net_faults_are_redundant():
    inv = part("INV", function="!A", inputs=1)
    nl = netlist(
        "top",
        [cell("g", inv, {"A": "x", "Y": "n1"})],
        inputs=("x",),
        outputs=(),
    )
    r = analyze_faults(nl, None)
    assert r.exhaustive is True
    assert r.detected == 0
    assert r.redundant == 2  # the two collapsed faults, both unobservable


def test_control_net_faults_are_untestable():
    dff = part("DFF_R", tier="F", function=None, inputs=3)
    nl = netlist(
        "top",
        [cell("f0", dff, {"D": "a", "CK": "clk", "RST_N": "rst_n", "Q": "y"})],
        inputs=("a", "clk", "rst_n"),
        outputs=("y",),
    )
    r = analyze_faults(nl, None)
    # clk and rst_n are control nets -> untestable (sa0 + sa1 each)
    assert r.untestable == 4
    # the data path (D and Q) faults are detected, not redundant/undetected
    assert r.detected == 4
    assert r.redundant == 0


def test_partial_vector_set_marks_undetected_not_redundant():
    and2 = part("AND2", function="A&B", inputs=2)
    nl = netlist(
        "top",
        [cell("g", and2, {"A": "a", "B": "b", "Y": "y"})],
        inputs=("a", "b"),
        outputs=("y",),
    )
    # cap of one vector: the single vector (a=0,b=0) detects nothing, and the
    # space is not exhausted, so the faults are *undetected*, never redundant.
    r = analyze_faults(nl, None, vector_cap=1)
    assert r.exhaustive is False
    assert r.undetected == 3
    assert r.redundant == 0
    assert r.detected == 0


def test_fanout_stem_is_not_collapsed_away():
    # a fans out to two gates (INV and AND2): a is a fanout stem, so its stem
    # faults must survive collapsing (the checkpoint rule).
    inv = part("INV", function="!A", inputs=1)
    and2 = part("AND2", function="A&B", inputs=2)
    nl = netlist(
        "top",
        [
            cell("g0", inv, {"A": "a", "Y": "b"}),
            cell("g1", and2, {"A": "a", "B": "c", "Y": "d"}),
        ],
        inputs=("a", "c"),
        outputs=("b", "d"),
    )
    _uncollapsed, collapsed = enumerate_faults(nl)
    sites = {(f.net, f.stuck, f.cell, f.pin) for f in collapsed}
    # the fanout stem faults survive (not folded into a gate output)
    assert ("a", 0, "", "") in sites
    assert ("a", 1, "", "") in sites
    # the fanout produced a branch at the AND2 sink; its sa1 branch survives
    # while the sa0 branch is equivalent to the AND output (correct collapse)
    assert ("a", 1, "g1", "A") in sites
    # the INV input branch collapsed into the INV output, so no branch survives
    # at g0 — this is the equivalence collapse working, not losing the stem
    assert not any(f.cell == "g0" for f in collapsed)


def test_wire_shape_is_the_four_classification_counts():
    and2 = part("AND2", function="A&B", inputs=2)
    nl = netlist(
        "top",
        [cell("g", and2, {"A": "a", "B": "b", "Y": "y"})],
        inputs=("a", "b"),
        outputs=("y",),
    )
    wire = analyze_faults(nl, None).to_wire()
    assert set(wire) == {"detected", "undetected", "redundant", "untestable"}
    assert all(isinstance(v, int) for v in wire.values())
