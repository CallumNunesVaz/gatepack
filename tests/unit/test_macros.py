"""Tests for the M-cell library (gatepack.macros) — §9.4, §19 R25."""

from __future__ import annotations

from gatepack.macros import get_binding, known_m_cells, load_models, model_files


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
