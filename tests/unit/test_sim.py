"""Tests for the C2 ``cells_sim.v`` behavioural-model emitter (gatepack.liberty.sim).

[R4-17]: the models must be generated from the same ``parts.csv`` function
strings and ``_FLOP_SPECS`` the Liberty file uses, so they cannot drift.
"""

from __future__ import annotations

from pathlib import Path

from gatepack.liberty.sim import generate
from gatepack.parts import load_parts

LIBRARY_CSV = Path(__file__).resolve().parents[2] / "libraries" / "74aup.csv"


def _models(**kwargs) -> str:
    return generate(load_parts(LIBRARY_CSV), project_vcc=3.3, **kwargs)


def test_g_cell_function_matches_parts_csv():
    text = _models()
    # NAND2 function in parts.csv is "!(A&B)" -> Verilog (~(A & B)).
    assert "assign Y = (~(A & B));" in text
    # XOR2 function is "A^B".
    assert "assign Y = (A ^ B);" in text


def test_dff_model_has_no_async_control():
    text = _models()
    assert "module DFF (" in text
    assert "always @(posedge CK) begin" in text


def test_dff_r_model_resets_low():
    text = _models()
    assert "always @(posedge CK or negedge RST_N) begin" in text
    assert "if (!RST_N) Q <= 1'b0;" in text


def test_dff_sr_model_clear_dominates_preset():
    text = _models()
    # clear is checked first, matching clear_preset_var1/var2 dominance.
    block = text[text.index("module DFF_SR ("):]
    assert block.index("if (!RST_N) Q <= 1'b0;") < block.index("if (!SET_N) Q <= 1'b1;")


def test_models_match_liberty_cell_set():
    from gatepack.liberty.generator import generate as generate_liberty

    parts = load_parts(LIBRARY_CSV)
    liberty = generate_liberty(parts, library_name="t", project_vcc=3.3)
    sim = _models()
    for cell in liberty.cells:
        assert f"module {cell} (" in sim
    # single-sourced DFF_S is excluded from both, unless overridden.
    assert "module DFF_S (" not in sim


def test_allow_single_source_adds_dff_s():
    text = _models(allow_single_source=True)
    assert "module DFF_S (" in text
    assert "always @(posedge CK or negedge SET_N) begin" in text


def test_every_module_is_balanced():
    text = _models()
    assert text.count("module ") == text.count("endmodule")
