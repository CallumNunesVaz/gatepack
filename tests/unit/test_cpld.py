"""Tests for the CPLD-hostile construct lint (§24.1).

The correct result on the golden designs is an empty list — so the negative
tests here are what prove the lint can actually fire.  A lint that cannot fail is
worthless (§24.1).
"""

from __future__ import annotations

from pathlib import Path

from gatepack.analysis.cpld import lint_cpld, lint_netlist, lint_verilog
from gatepack.frontend import compile_design_file
from gatepack.netlist import MappedCell, MappedNetlist

DESIGNS = Path(__file__).resolve().parents[1] / "golden" / "designs"


def test_golden_generated_verilog_has_no_cpld_blockers():
    for name in ("traffic_light", "xor2", "decoder_3to8"):
        result = compile_design_file(DESIGNS / f"{name}.yaml")
        assert lint_verilog(result.verilog) == [], name


def test_lint_cpld_clean_golden_is_empty():
    result = compile_design_file(DESIGNS / "traffic_light.yaml")
    assert lint_cpld(result.verilog, None) == []


def test_lint_verilog_detects_memory_declaration():
    hostile = "module m;\n  reg [7:0] mem [0:15];\nendmodule\n"
    blockers = lint_verilog(hostile)
    assert blockers, "a memory declaration must fire the lint"
    assert any("memory" in b.message for b in blockers)
    assert blockers[0].code == "GP1009"
    assert blockers[0].severity == "warning"


def test_lint_verilog_detects_latch_inference():
    hostile = (
        "module m;\n"
        "  reg y;\n"
        "  always @* begin\n"
        "    if (a) y = 1'b1;\n"
        "  end\n"
        "endmodule\n"
    )
    blockers = lint_verilog(hostile)
    assert blockers, "a latch-inferring always block must fire the lint"
    assert any("latch" in b.message for b in blockers)


def test_lint_verilog_ignores_vector_register():
    # a plain vector state register (binary/gray encoding) is CPLD-portable
    assert lint_verilog("module m;\n  reg [1:0] state;\nendmodule\n") == []


def test_lint_netlist_detects_latch_memory_and_internal_cells():
    netlist = MappedNetlist(
        top="t",
        cells=(
            MappedCell("c1", "$_DLATCH_P_", "", connections={}, directions={}),
            MappedCell("c2", "$mem", "", connections={}, directions={}),
            MappedCell("c3", "$and", "", connections={}, directions={}),
        ),
    )
    messages = " ".join(b.message for b in lint_netlist(netlist))
    assert "latch" in messages
    assert "memory" in messages
    assert "internal cell" in messages


def test_lint_netlist_clean_is_empty():
    netlist = MappedNetlist(
        top="t",
        cells=(MappedCell("c1", "INV", "G", connections={}, directions={}),),
    )
    assert lint_netlist(netlist) == []
