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


def test_report_renders_scoap_and_fault_sections():
    from gatepack.analysis.faults import FaultReport
    from gatepack.analysis.scoap import ScoapNet, ScoapReport

    scoap = ScoapReport(
        nets=(ScoapNet("n", 2, 3, None),),
        unobservable=("n",),
        delta=(ScoapNet("n", 2, 3, None),),
        note="absolute costs are not directly comparable",
    )
    faults = FaultReport(
        uncollapsed=8, collapsed=4, detected=3, undetected=0,
        redundant=1, untestable=0, exhaustive=True,
        vectors_applied=4, vectors_total=4, note="single stuck-at",
    )
    inp = ReportInputs(
        design="demo",
        timing_model="synchronous",
        packed_stats=_stats(),
        unpacked_stats=_stats(),
        scoap=scoap,
        faults=faults,
    )
    text = emit_report(inp)
    assert "## Testability (SCOAP, §13.1)" in text
    assert "Unobservable nets" in text
    assert "## Fault analysis (§13.2)" in text
    assert "collapsed faults" in text
    assert "redundant: 1" in text
    assert "exhaustive (4 vectors)" in text


def test_report_degrades_honestly_without_netlist():
    inp = ReportInputs(
        design="demo",
        timing_model="synchronous",
        packed_stats=_stats(),
        unpacked_stats=_stats(),
    )
    text = emit_report(inp)
    assert "SCOAP not computed (no mapped netlist)" in text
    assert "fault analysis not computed (no mapped netlist)" in text
    # never zeros presented as a measurement
    assert "detected: 0" not in text


def test_report_renders_provenance_section():
    from pathlib import Path

    from gatepack.provenance.capture import read_netlist_json
    from gatepack.provenance.coverage import measure_coverage

    fix = Path(__file__).resolve().parents[1] / "fixtures" / "provenance" / "traffic_light"
    report = measure_coverage(
        read_netlist_json(fix / "premap.json"),
        read_netlist_json(fix / "mapped.json"),
    )
    inp = ReportInputs(
        design="traffic_light",
        timing_model="synchronous",
        packed_stats=_stats(),
        unpacked_stats=_stats(),
        provenance=report,
    )
    text = emit_report(inp)
    assert "## Provenance (§15.1, M11b)" in text
    # carrier split, exact/inferred/absent, never a bare number
    assert "| net | 22 | 16 | 0 | 6 |" in text
    # construct-kind split names the weak axis
    assert "| transitions | 5 | 2 | 0 | 3 |" in text
    assert "| output_logic | 3 | 3 | 0 | 0 |" in text
    # the unlinked constructs are named, not a percentage
    assert "transitions[0]" in text
    assert "transitions[3]" in text
    # the assumption is stated inline
    assert "survives into the final netlist" in text


def test_report_provenance_degrades_honestly():
    inp = ReportInputs(
        design="demo",
        timing_model="synchronous",
        packed_stats=_stats(),
        unpacked_stats=_stats(),
    )
    text = emit_report(inp)
    assert "## Provenance (§15.1, M11b)" in text
    assert "provenance not computed" in text


def test_report_timing_worst_path_uses_refdes():
    from gatepack.analysis.clock import TimingReport

    abc_names = (
        "$abc$148$auto$blifparse.cc:386:parse_blif$149",
        "$abc$148$auto$blifparse.cc:386:parse_blif$150",
    )
    inp = ReportInputs(
        design="demo",
        timing_model="synchronous",
        packed_stats=_stats(),
        unpacked_stats=_stats(),
        timing=TimingReport(
            combinational_depth=2,
            cumulative_tpd_ns=10.0,
            worst_path=abc_names,
            note="not STA",
        ),
        cell_refdes={abc_names[0]: "U6", abc_names[1]: "U19"},
    )
    text = emit_report(inp)
    assert "worst path: U6 -> U19" in text
    assert "$abc$" not in text.split("worst path:")[1].split("\n")[0]


def test_report_timing_worst_path_falls_back_to_names():
    from gatepack.analysis.clock import TimingReport

    abc_names = ("$abc$149", "$abc$150")
    inp = ReportInputs(
        design="demo",
        timing_model="synchronous",
        packed_stats=_stats(),
        unpacked_stats=_stats(),
        timing=TimingReport(
            combinational_depth=2,
            cumulative_tpd_ns=10.0,
            worst_path=abc_names,
            note="not STA",
        ),
    )
    text = emit_report(inp)
    assert "worst path: $abc$149 -> $abc$150" in text
