"""Tests for the C8 report generator."""

from __future__ import annotations

from gatepack.emit.bom import BomRow
from gatepack.pack.packer import PackingStats
from gatepack.report.report import ReportInputs, emit_report


def _stats(**overrides) -> PackingStats:
    base = dict(package_count=3, spare_count=0, package_cost=3.0, pack_cost=3.0)
    base.update(overrides)
    return PackingStats(**base)


def test_report_carries_assumptions_inline():
    from gatepack.analysis.clock import TimingReport
    from gatepack.analysis.power import DynamicCurrent, StaticCurrent

    inp = ReportInputs(
        design="demo",
        timing_model="synchronous",
        packed_stats=_stats(),
        unpacked_stats=_stats(package_count=4, package_cost=4.0, pack_cost=4.0),
        static_current=StaticCurrent(g_ua=0.9, f_ua=0.0, m_ua=0.0, s_ua=0.0),
        dynamic_current=DynamicCurrent(ua=1.2, excludes_routing_capacitance=True, note="not a budget"),
        timing=TimingReport(combinational_depth=2, cumulative_tpd_ns=10.0, worst_path=(), note="not STA"),
    )
    text = emit_report(inp)
    assert "# demo — build report" in text
    assert "not a budget" in text
    assert "not STA" in text
    assert "no temperature derating" in text


def test_report_is_deterministic():
    a = ReportInputs(design="x", timing_model="synchronous",
                     packed_stats=_stats(), unpacked_stats=_stats())
    assert emit_report(a) == emit_report(ReportInputs(
        design="x", timing_model="synchronous",
        packed_stats=_stats(), unpacked_stats=_stats(),
    ))


def test_report_bom_rows_rendered():
    inp = ReportInputs(
        design="demo",
        timing_model="synchronous",
        packed_stats=_stats(),
        unpacked_stats=_stats(),
        packed_bom=[BomRow("74AUP1G00", "TI;Nexperia", "", "SOT-353", 2, ("U1", "U2"), "G")],
    )
    text = emit_report(inp)
    assert "74AUP1G00" in text
    assert "U1;U2" in text
