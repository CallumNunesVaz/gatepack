"""Tests for the net-based provenance spine (gatepack.provenance, M0 §3)."""

from __future__ import annotations

from pathlib import Path

from gatepack.frontend import compile_design_file, compile_design_text
from gatepack.provenance import net_provenance

from .helpers import sync_design

DESIGNS = Path(__file__).resolve().parents[1] / "golden" / "designs"


def test_net_provenance_extracts_named_nets():
    v = compile_design_text(sync_design()).verilog
    prov = net_provenance(v)
    assert "state_A" in prov
    assert "state_B" in prov
    assert "next_A" in prov
    assert "t_0" in prov
    # the value carries the source file, line and path
    assert prov["state_A"].startswith("design.yaml:")


def test_net_provenance_ignores_attributes_before_module_or_assign():
    # An attribute before `module` is not a net; the function must not attribute
    # it to a wire/reg.
    v = (
        '(* gp_src = "x:1:name" *)\n'
        "module m;\n"
        "  wire a;\n"
        "  assign a = 1'b0;\n"
        "endmodule\n"
    )
    prov = net_provenance(v)
    assert "a" not in prov
    assert "m" not in prov


def test_traffic_light_nets_carry_provenance():
    result = compile_design_file(DESIGNS / "traffic_light.yaml")
    prov = net_provenance(result.verilog)
    # state regs, transition terms, next-state nets, and the output intermediate
    # nets are the named-net carriers (M0 §1, §3).
    for name in ("state_RED", "state_GREEN", "state_AMBER"):
        assert name in prov, name
    for i in range(5):
        assert f"t_{i}" in prov, f"t_{i}"
    assert "next_RED" in prov
    assert "red_int" in prov
    assert "green_int" in prov
    assert "amber_int" in prov
