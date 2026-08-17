"""Integrity of the shipped cell library against its citation record.

The parts library (`libraries/74aup.csv`) and its companion
(`libraries/74aup.refs.md`) must not drift apart: every row needs an electrical
citation, every multi-gate row needs a packaging citation keyed by part number,
and every `function` string must parse and use exactly its declared inputs. A
citation keyed to a part number that is not in the CSV (or a multi-gate part
number missing from the packaging table) is the drift these tests exist to
catch.
"""

from __future__ import annotations

from pathlib import Path

from gatepack.liberty import boolean
from gatepack.parts import load_parts
from gatepack.refs import parse_refs, parse_refs_packaging

LIBRARY = Path(__file__).resolve().parents[2] / "libraries" / "74aup.csv"
REFS = Path(__file__).resolve().parents[2] / "libraries" / "74aup.refs.md"


def test_every_row_has_an_electrical_refs_entry():
    parts = load_parts(LIBRARY)
    citations = parse_refs(REFS)
    missing = [p.cell for p in parts if p.cell not in citations]
    assert missing == [], f"rows without an electrical citation: {missing}"


def test_every_multi_gate_row_has_a_packaging_citation():
    # gates_per_pkg > 1 decides which gates share a die; it must be gated on a
    # packaging citation, not just the (placeholder) electrical row.
    parts = load_parts(LIBRARY)
    packaging = parse_refs_packaging(REFS)
    missing = [
        p.part_number
        for p in parts
        if p.gates_per_pkg > 1 and p.part_number not in packaging
    ]
    assert missing == [], f"multi-gate rows without a packaging citation: {missing}"


def test_packaging_part_numbers_are_in_bijection_with_csv_multi_gate_rows():
    # A packaging citation keyed to a part number that is not a real multi-gate
    # row in the CSV (or a multi-gate row whose part number has no packaging
    # citation) is a citation that has drifted away from its row.
    parts = load_parts(LIBRARY)
    csv_multi_gate = {p.part_number for p in parts if p.gates_per_pkg > 1}
    packaging = set(parse_refs_packaging(REFS))
    assert packaging == csv_multi_gate, (
        f"packaging table {sorted(packaging)} != CSV multi-gate rows "
        f"{sorted(csv_multi_gate)}"
    )


def test_every_function_string_parses_and_uses_exactly_its_inputs():
    parts = load_parts(LIBRARY)
    for part in parts:
        if part.tier != "G" or not part.function:
            continue
        node = boolean.parse_function(part.function, part.inputs)
        used = boolean._variables(node)
        expected = set(boolean.pin_names(part.inputs))
        assert used == expected, (
            f"{part.cell}: function {part.function!r} uses {sorted(used)} "
            f"but inputs={part.inputs} names {sorted(expected)}"
        )


def test_mux2_function_matches_the_datasheet_function_table():
    # Y = (I0 & !S) | (I1 & S) with A=I0, B=I1, C=S (§74aup.refs.md).
    func = "(A&!C)|(B&C)"
    assert boolean.translate(func, 3) == "((A & (!C)) | (B & C))"
    # Full truth table.  A=I0, B=I1, C=S; S=0 selects I0 (A), S=1 selects I1 (B).
    rows = {
        (False, False, False): False,
        (False, False, True): False,
        (False, True, False): False,
        (False, True, True): True,
        (True, False, False): True,
        (True, False, True): False,
        (True, True, False): True,
        (True, True, True): True,
    }
    for (a, b, c), want in rows.items():
        got = boolean.evaluate(func, 3, {"A": a, "B": b, "C": c})
        assert got is want, (a, b, c)
