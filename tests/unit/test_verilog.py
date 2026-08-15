"""Tests for behavioural Verilog + properties emission (gatepack.frontend.verilog)."""

from __future__ import annotations

from gatepack.frontend import compile_design_text

from .helpers import sync_design


def test_module_declaration_and_ports():
    result = compile_design_text(sync_design())
    v = result.verilog
    assert "module min (" in v
    assert "input wire clk" in v
    assert "input wire rst_n" in v
    assert "input wire x" in v
    assert "endmodule" in v


def test_src_attributes_present_on_constructs():
    result = compile_design_text(sync_design())
    v = result.verilog
    assert '(* gp_src = "design.yaml:1:name" *)' in v
    assert '(* gp_src = "design.yaml:' in v
    assert "transitions[0]" in v
    assert "output_logic" not in v  # no outputs in the minimal design


def test_one_hot_state_bits_named_state_name():
    result = compile_design_text(sync_design())
    v = result.verilog
    assert "reg state_A;" in v
    assert "reg state_B;" in v
    assert "wire next_A" in v


def test_synchroniser_emitted_for_sync_input():
    yaml = sync_design().replace("sync: false", "sync: true")
    result = compile_design_text(yaml)
    v = result.verilog
    assert "reg x_s1;" in v
    assert "reg x_s2;" in v
    assert "wire x_i = x_s2;" in v
    assert result.compiled.flop_count == 2 + 2 + 2  # state + reset + input sync


def test_reset_deassert_synchroniser():
    result = compile_design_text(sync_design())
    v = result.verilog
    assert "rst_n_s1" in v
    assert "rst_n_s2" in v
    assert "wire rst_n_i = rst_n_s2;" in v


def test_output_logic_emits_state_compare():
    yaml = sync_design(
        outputs=["green"],
        output_logic={"green": "state == B"},
    )
    v = compile_design_text(yaml).verilog
    assert "assign green = state_B;" in v


def test_output_provenance_is_on_port_not_assign():
    # gp_src must be on the output net (port declaration), never before the
    # continuous assign — Yosys 0.23 rejects an attribute before `assign`.
    yaml = sync_design(
        outputs=["green"],
        output_logic={"green": "state == B"},
    )
    v = compile_design_text(yaml).verilog
    assert "(* gp_src" in v
    assert "output wire green" in v
    assert "assign green = state_B;" in v
    # the attribute is attached to the port declaration, not to the assign
    assert "*)\n  assign green" not in v


def test_binary_encoding_emits_vector_and_localparams():
    yaml = sync_design(
        states=["A", "B", "C", "D"],
        transitions=[
            ("A", "B", "1"), ("B", "C", "1"), ("C", "D", "1"), ("D", "A", "1"),
        ],
    ).replace("encoding: one_hot", "encoding: binary")
    v = compile_design_text(yaml).verilog
    assert "localparam [1:0] STATE_A = 2'd0;" in v
    assert "localparam [1:0] STATE_D = 2'd3;" in v
    assert "reg [1:0] state;" in v
    assert "case (state)" in v


def test_gray_encoding_uses_reflected_code():
    # 4 states -> width 2 -> gray(0)=0, gray(1)=1, gray(2)=3, gray(3)=2
    yaml = sync_design(
        states=["A", "B", "C", "D"],
        transitions=[
            ("A", "B", "1"), ("B", "C", "1"), ("C", "D", "1"), ("D", "A", "1"),
        ],
    ).replace("encoding: one_hot", "encoding: gray")
    v = compile_design_text(yaml).verilog
    assert "STATE_C = 2'd3;" in v
    assert "STATE_D = 2'd2;" in v


def test_properties_file_emits_assertions():
    yaml = sync_design(
        outputs=["o"],
        output_logic={"o": "state == A"},
    )
    yaml += 'properties:\n  - {name: p1, kind: invariant, expr: "!(o & x)"}\n'
    props = compile_design_text(yaml).properties
    assert "assert property" in props
    assert "p1" in props
    assert "disable iff (!rst_n)" in props


def test_johnson_suggestion_surfaced_in_result():
    yaml = sync_design(
        states=["A", "B", "C"],
        transitions=[("A", "B", "1"), ("B", "C", "1"), ("C", "A", "1")],
    )
    result = compile_design_text(yaml)
    assert result.compiled.johnson_suggestion is not None
    assert "JOHN10" in result.compiled.johnson_suggestion
