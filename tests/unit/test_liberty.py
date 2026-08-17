"""Tests for the C2 Liberty generator and boolean translation."""

from __future__ import annotations

from pathlib import Path

import pytest

from gatepack.liberty import generate
from gatepack.liberty import boolean
from gatepack.parts import Part, load_parts

LIBRARY_CSV = Path(__file__).resolve().parents[2] / "libraries" / "74aup.csv"


@pytest.mark.parametrize(
    ("func", "inputs", "expected"),
    [
        ("!A", 1, "(!A)"),
        ("A", 1, "A"),
        ("!(A&B)", 2, "(!(A & B))"),
        ("A&B", 2, "(A & B)"),
        ("A|B", 2, "(A | B)"),
        ("A^B", 2, "(A ^ B)"),
        ("!(A^B)", 2, "(!(A ^ B))"),
        ("A&B&C", 3, "((A & B) & C)"),
        ("!(A|B|C)", 3, "(!((A | B) | C))"),
    ],
)
def test_boolean_translation(func, inputs, expected):
    assert boolean.translate(func, inputs) == expected


@pytest.mark.parametrize(
    ("func", "inputs"),
    [
        ("!A&C", 1),  # references C but only 1 input
        ("A&", 2),  # trailing operator
        ("A)", 2),  # stray ')' / missing '('
        ("A B", 2),  # missing operator
        ("", 1),  # empty
    ],
)
def test_boolean_translation_rejects(func, inputs):
    with pytest.raises(boolean.BooleanError):
        boolean.translate(func, inputs)


def _cell_block(text: str, name: str) -> str:
    marker = f"cell ({name}) {{"
    start = text.index(marker)
    i = text.index("{", start)
    depth = 0
    j = i
    while True:
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                break
        j += 1
    return text[start : j + 1]


def _generate(csv_path=LIBRARY_CSV, **kwargs):
    parts = load_parts(csv_path)
    return generate(parts, library_name="test", **kwargs)


def test_valid_library_round_trips_with_expected_cell_count():
    result = _generate()
    # 10 G-cells + DFF/DFF_R/DFF_SR; DFF_S is single-sourced and excluded.
    assert result.cells == [
        "INV", "BUF", "NAND2", "NAND3", "NOR2", "NOR3",
        "AND2", "AND3", "OR2", "XOR2",
        "DFF", "DFF_R", "DFF_SR",
    ]
    assert len(result.cells) == 13
    assert "cell (DFF_S)" not in result.text


def test_allow_single_source_includes_dff_s():
    result = _generate(allow_single_source=True)
    # 13 default cells + single-sourced DFF_S and MUX2 (74AUP1G157).
    assert len(result.cells) == 15
    assert "cell (DFF_S)" in result.text
    assert "cell (MUX2)" in result.text


def test_g_cell_has_function():
    result = _generate()
    block = _cell_block(result.text, "NAND2")
    assert 'function : "(!(A & B))";' in block
    assert "direction : input" in block
    assert "direction : output" in block


def test_dff_has_no_clear_or_preset():
    block = _cell_block(_generate().text, "DFF")
    assert "next_state" in block
    assert "clocked_on" in block
    assert "clear" not in block
    assert "preset" not in block


def test_dff_r_has_clear_only():
    block = _cell_block(_generate().text, "DFF_R")
    assert 'clear : "!RST_N";' in block
    assert "preset" not in block


def test_dff_s_has_preset_only():
    result = _generate(allow_single_source=True)
    block = _cell_block(result.text, "DFF_S")
    assert 'preset : "!SET_N";' in block
    assert "clear" not in block


def test_dff_sr_emits_clear_and_preset_with_dominance():
    block = _cell_block(_generate().text, "DFF_SR")
    assert 'clear : "!RST_N";' in block
    assert 'preset : "!SET_N";' in block
    # reset/clear dominates set/preset to match $_DFFSR_* semantics
    assert 'clear_preset_var1 : "L";' in block
    assert 'clear_preset_var2 : "H";' in block


def test_flop_inputs_mismatch_fails():
    from gatepack.liberty import LibertyError

    parts = load_parts(LIBRARY_CSV)
    bad = [p for p in parts if p.cell != "DFF_R"]
    broken = Part(
        cell="DFF_R",
        tier="F",
        family="AUP",
        part_suffix="1G175",
        inputs=2,  # DFF_R needs 3 (D, CK, RST_N)
        gates_per_pkg=1,
        package="SOT-353",
        mfrs=["TI", "Nexperia"],
        vcc_min=0.8,
        vcc_max=3.6,
        area=1.0,
    )
    with pytest.raises(LibertyError, match="DFF_R"):
        generate(bad + [broken], library_name="test")
