"""Tests for the C2 self-check (gatepack.liberty.validate).

The degenerate-library case is the §18 golden: a broken ``.lib`` must fail, not
silently parse into a degenerate library (§19 R1).
"""

from __future__ import annotations

import pytest

from gatepack.liberty.validate import LibertyError, validate_library


def _ok_library() -> str:
    return (
        'library (test) {\n'
        '  cell (INV) {\n'
        '    area : 1.0;\n'
        '    pin(A) { direction : input; }\n'
        '    pin(Y) { direction : output; function : "(!A)"; }\n'
        '  }\n'
        '}\n'
    )


def test_valid_library_passes():
    names = validate_library(_ok_library(), ["INV"])
    assert names == ["INV"]


@pytest.mark.parametrize(
    "text",
    [
        "",  # empty input
        'library (test) {',  # unbalanced brace
        'cell (INV) { area : 1.0; }',  # no library block
        'library (test) { cell (INV) { } }',  # missing area and function
        'library (test) { cell (INV) { area : 1.0; } }',  # no output function
        'library (test) { cell (INV) { area : 1.0; '
        'pin(A) { direction : input; } } }',  # input only
    ],
)
def test_degenerate_library_fails(text):
    with pytest.raises(LibertyError):
        validate_library(text, ["INV"])


def test_wrong_cell_count_fails():
    with pytest.raises(LibertyError, match="cell count/name mismatch"):
        validate_library(_ok_library(), ["INV", "NAND2"])


def test_duplicate_cell_fails():
    text = (
        'library (test) {\n'
        '  cell (INV) { area : 1.0; pin(A) { direction : input; } '
        'pin(Y) { direction : output; function : "(!A)"; } }\n'
        '  cell (INV) { area : 1.0; pin(A) { direction : input; } '
        'pin(Y) { direction : output; function : "(!A)"; } }\n'
        '}\n'
    )
    with pytest.raises(LibertyError, match="duplicate cell names"):
        validate_library(text, ["INV"])


def test_ff_missing_required_attr_fails():
    text = (
        'library (test) {\n'
        '  cell (DFF) {\n'
        '    area : 1.0;\n'
        '    ff (IQ, IQN) { clocked_on : "CK"; }\n'
        '    pin(D) { direction : input; }\n'
        '    pin(CK) { direction : input; clock : true; }\n'
        '    pin(Q) { direction : output; function : "IQ"; }\n'
        '  }\n'
        '}\n'
    )
    with pytest.raises(LibertyError, match="next_state"):
        validate_library(text, ["DFF"])


def _ff_library(cell: str, ff_body: str) -> str:
    return (
        f'library (test) {{\n'
        f'  cell ({cell}) {{\n'
        f'    area : 1.0;\n'
        f'    ff (IQ, IQN) {{ {ff_body} }}\n'
        f'    pin(D) {{ direction : input; }}\n'
        f'    pin(CK) {{ direction : input; clock : true; }}\n'
        f'    pin(Q) {{ direction : output; function : "IQ"; }}\n'
        f'  }}\n'
        f'}}\n'
    )


def test_dff_r_without_clear_rejected_by_spec():
    # §1 defect / §19 R1: the C2 self-check must be spec-driven, so a DFF_R
    # emitted without its `clear` is rejected — the validator shares the
    # generator's truth (the spec), not its output.
    from gatepack.liberty.generator import flop_ff_requirements

    text = _ff_library(
        "DFF_R",
        'next_state : "D"; clocked_on : "CK";',
    )
    with pytest.raises(LibertyError, match="clear"):
        validate_library(text, ["DFF_R"], flop_requirements=flop_ff_requirements())


def test_dff_r_complete_passes_spec():
    from gatepack.liberty.generator import flop_ff_requirements

    text = _ff_library(
        "DFF_R",
        'next_state : "D"; clocked_on : "CK"; clear : "!RST_N";',
    )
    names = validate_library(text, ["DFF_R"], flop_requirements=flop_ff_requirements())
    assert names == ["DFF_R"]


def test_unexpected_ff_attr_rejected_by_spec():
    # DFF must not carry a `clear`; a spec-driven check catches the inverse bug.
    from gatepack.liberty.generator import flop_ff_requirements

    text = _ff_library(
        "DFF",
        'next_state : "D"; clocked_on : "CK"; clear : "!RST_N";',
    )
    with pytest.raises(LibertyError, match="unexpected"):
        validate_library(text, ["DFF"], flop_requirements=flop_ff_requirements())


def test_dff_sr_requires_dominance_vars():
    from gatepack.liberty.generator import flop_ff_requirements

    text = _ff_library(
        "DFF_SR",
        'next_state : "D"; clocked_on : "CK"; clear : "!RST_N"; preset : "!SET_N";',
    )
    with pytest.raises(LibertyError, match="clear_preset_var1"):
        validate_library(text, ["DFF_SR"], flop_requirements=flop_ff_requirements())
