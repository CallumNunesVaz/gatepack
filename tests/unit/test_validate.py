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
