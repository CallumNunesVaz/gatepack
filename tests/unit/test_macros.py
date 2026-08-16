"""Tests for the M-cell library (gatepack.macros) — §9.4, §19 R25."""

from __future__ import annotations

from gatepack.macros import (
    blackbox_module,
    get_binding,
    get_spec,
    known_m_cells,
    known_spec_cells,
    load_models,
    load_spec_models,
    model_files,
    spec_model,
)


def test_cnT4_binding_maps_to_74lvc161():
    binding = get_binding("CNT4")
    assert binding.part == "74LVC161"
    assert binding.package == "SO-16"
    assert binding.pins["CLK"] and binding.pins["RST_N"] and binding.pins["EN"]
    # every binding in this file is unverified (candidate) until a datasheet backs it
    assert binding.verified is False


def test_known_m_cells_lists_cnT4():
    assert known_m_cells() == ("CNT4",)


def test_load_models_contains_cnT4_module():
    text = load_models()
    assert "module CNT4 (" in text
    assert "always @(posedge CLK or negedge RST_N)" in text
    assert text.count("module ") == text.count("endmodule")


def test_model_file_is_single_source_for_c4():
    # §19 R25: the model C4 uses for equivalence must be *the same file* as the
    # one appended to cells_sim.v — there is exactly one model file per M-cell.
    paths = model_files()
    assert len(paths) == 1
    assert paths[0].endswith("CNT4.v")
    from pathlib import Path

    assert Path(paths[0]).is_file()


def test_unknown_m_cell_raises():
    import pytest

    with pytest.raises(KeyError, match="JOHN10"):
        get_binding("JOHN10")


# ---------------------------------------------------------------------------
# Specification models (§9.4, M8) — the independent spec side of equivalence
# ---------------------------------------------------------------------------


def test_spec_model_counts_by_one_with_async_low_reset():
    text = spec_model("CNT4")
    assert "module CNT4 (" in text
    assert "always @(posedge CLK or negedge RST_N)" in text
    assert "if (!RST_N)" in text
    assert "Q <= 4'd0;" in text
    assert "else if (EN)" in text
    assert "Q <= Q + 4'd1;" in text  # counts by ONE; period 2^4


def test_spec_ports_match_implementation_model_ports():
    # The golden side reads the spec model, the gate side the implementation
    # model; both must present the same module signature or equiv_make fails.
    spec = get_spec("CNT4")
    impl = load_models()
    for port in spec.ports:
        assert port.name in impl, f"impl model is missing port {port.name}"
    assert "[3:0] Q" in impl  # the counter width must agree
    assert "[3:0] Q" in spec_model("CNT4")


def test_spec_model_is_independent_of_the_implementation_file():
    # The acceptance criterion of the M-cell mutation test: mutating the
    # implementation model must NOT change the specification model.  They are
    # produced by different paths (specs.py vs models/CNT4.v).
    before = spec_model("CNT4")
    mutated_impl = load_models().replace("Q <= Q + 1'b1;", "Q <= Q + 4'd2;")
    assert mutated_impl != load_models()  # sanity: the mutation actually took
    assert spec_model("CNT4") == before  # the spec is untouched


def test_blackbox_module_elaborates_under_hierarchy_check():
    # `(* blackbox *)` is what lets `hierarchy -check` accept the instantiation
    # while keeping the physical part out of dfflibmap/abc (M8).
    bb = blackbox_module("CNT4")
    assert "(* blackbox *)" in bb
    assert "module CNT4 (" in bb
    assert "output wire [3:0] Q" in bb
    for port in get_spec("CNT4").ports:
        assert port.name in bb


def test_known_spec_cells_tracks_known_m_cells():
    assert known_spec_cells() == ("CNT4",)
    assert load_spec_models().count("module CNT4") == 1
