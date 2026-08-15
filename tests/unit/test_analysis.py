"""Tests for the C7 analysis (power and clock/timing)."""

from __future__ import annotations

from gatepack.analysis.clock import (
    clock_fanout,
    combinational_depth,
    cumulative_tpd_ns,
    flop_count,
    timing_analysis,
)
from gatepack.analysis.power import (
    dynamic_current_ua,
    spare_leakage_ua,
    static_current_by_tier,
)

from .cells import cell, netlist, part


def test_static_current_broken_out_by_tier():
    g = part("NOR2", function="!(A|B)", inputs=2, iq_ua=0.9)
    f = part("DFF_R", tier="F", function=None, inputs=3, iq_ua=0.9)
    s = part("SUPERVISOR", tier="S", function=None, inputs=1, iq_ua=0.15, part_suffix="TPS3839", family="-")
    cells = [
        cell("g0", g, {"A": "a", "B": "b", "Y": "n"}),
        cell("f0", f, {"D": "n", "CK": "clk", "RST_N": "rst_n", "Q": "q"}),
        cell("s0", s, {"RESET": "rst_n"}),
    ]
    sc = static_current_by_tier(cells)
    assert sc.g_ua == 0.9
    assert sc.f_ua == 0.9
    assert sc.s_ua == 0.15
    assert sc.m_ua == 0.0
    assert sc.total_ua == 0.9 + 0.9 + 0.15


def test_spare_leakage_penalty():
    from gatepack.pack.packer import pack

    nor2 = part("NOR2", function="!(A|B)", inputs=2, gates_per_pkg=2, iq_ua=0.9)
    cells = [cell("g0", nor2, {"A": "a", "B": "b", "Y": "n0"})]  # 1 gate -> 1 spare
    result = pack(cells, [nor2])
    assert spare_leakage_ua(result.packed) == 0.9  # one spare slot's IQ


def test_dynamic_current_flagged():
    inv = part("INV", function="!A", inputs=1)
    cells = [cell("g0", inv, {"A": "a", "Y": "y"})]
    nl = netlist("top", cells, inputs=("a",), outputs=("y",))
    d = dynamic_current_ua(nl, freq_hz=32768.0, vcc=3.3)
    assert d.excludes_routing_capacitance is True
    assert "not a budget" in d.note
    assert d.ua > 0


def test_combinational_depth_and_tpd():
    inv = part("INV", function="!A", inputs=1, tpd_ns=5.0)
    cells = [
        cell("g0", inv, {"A": "a", "Y": "n1"}),
        cell("g1", inv, {"A": "n1", "Y": "y"}),
    ]
    nl = netlist("top", cells, inputs=("a",), outputs=("y",))
    assert combinational_depth(nl) == 2
    assert cumulative_tpd_ns(nl) == 10.0
    t = timing_analysis(nl)
    assert t.cumulative_tpd_ns == 10.0
    assert "not static timing analysis" in t.note


def test_depth_ignores_flops():
    inv = part("INV", function="!A", inputs=1, tpd_ns=5.0)
    f = part("DFF_R", tier="F", function=None, inputs=3, tpd_ns=7.5)
    # a -> INV -> d, flop q -> INV -> y : two disjoint combinational cones of depth 1
    cells = [
        cell("g0", inv, {"A": "a", "Y": "d"}),
        cell("f0", f, {"D": "d", "CK": "clk", "RST_N": "rst_n", "Q": "q"}),
        cell("g1", inv, {"A": "q", "Y": "y"}),
    ]
    nl = netlist("top", cells, inputs=("a",), outputs=("y",))
    assert combinational_depth(nl) == 1
    assert flop_count(nl) == 1
    assert clock_fanout(nl) == 1
