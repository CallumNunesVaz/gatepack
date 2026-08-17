"""Tests for the verified/placeholder distinction (§1.3, §23).

A placeholder electrical value is a different thing from a cited one: the
``Part`` model carries a ``Verification`` status, and the build gate + outputs
must not let a placeholder read as a verified figure.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gatepack.parts import (
    Part,
    Verification,
    mark_packaging_verification,
    mark_verification,
    unverified_multi_gate_parts,
    verification_from_citation,
)
from gatepack.refs import load_parts_cited, parse_refs, parse_refs_packaging, placeholder_summary


def _row(**overrides) -> dict[str, str]:
    base: dict[str, str] = {
        "cell": "INV",
        "tier": "G",
        "family": "AUP",
        "part_suffix": "1G04",
        "equivalents": "",
        "function": "!A",
        "inputs": "1",
        "gates_per_pkg": "1",
        "package": "SOT-353",
        "mfrs": "TI;Nexperia",
        "vcc_min": "0.8",
        "vcc_max": "3.6",
        "area": "1.0",
        "tpd_ns": "4.6",
        "iq_ua": "0.9",
    }
    base.update(overrides)
    return base


def test_part_defaults_to_placeholder():
    # fail-closed: a part with no citation must never read as verified
    part = Part.from_row(_row())
    assert part.verification is Verification.PLACEHOLDER
    assert part.is_verified is False


def test_verification_from_citation():
    assert verification_from_citation(None) is Verification.PLACEHOLDER
    assert verification_from_citation("placeholder — unverified") is Verification.PLACEHOLDER
    assert verification_from_citation("unverified") is Verification.PLACEHOLDER
    assert verification_from_citation("verified — TI datasheet SLVS...") is Verification.VERIFIED


def test_mark_verification_attaches_status_per_cell():
    parts = [Part.from_row(_row()), Part.from_row(_row(cell="BUF"))]
    mark_verification(parts, {"INV": "verified", "BUF": "placeholder — unverified"})
    assert parts[0].is_verified is True
    assert parts[1].is_verified is False


def test_unverified_multi_gate_parts_flags_only_multi_gate():
    single = Part.from_row(_row())
    multi = Part.from_row(_row(part_suffix="2G04", gates_per_pkg="2", package="VSSOP-8"))
    verified_multi = Part.from_row(_row(part_suffix="2G04", gates_per_pkg="2", package="VSSOP-8"))
    verified_multi.packaging_verification = Verification.VERIFIED
    assert unverified_multi_gate_parts([single, multi, verified_multi]) == [multi]


def test_unverified_multi_gate_parts_uses_packaging_verification():
    # Electrical verification is NOT enough to clear a multi-gate package: the
    # gate counts + package facts have their own citation.  A row that claims
    # verified electrical data while its gates_per_pkg is still a placeholder
    # must keep firing the gate, or the two axes collapse back into one.
    electrically_verified = Part.from_row(
        _row(part_suffix="2G04", gates_per_pkg="2", package="VSSOP-8")
    )
    electrically_verified.verification = Verification.VERIFIED
    assert unverified_multi_gate_parts([electrically_verified]) == [electrically_verified]

    packaging_verified = Part.from_row(
        _row(part_suffix="2G04", gates_per_pkg="2", package="VSSOP-8")
    )
    packaging_verified.packaging_verification = Verification.VERIFIED
    assert unverified_multi_gate_parts([packaging_verified]) == []


def test_mark_packaging_verification_is_keyed_by_part_number():
    # One cell, two packages: the single-gate and dual-gate AND2.  A citation
    # keyed by part number must mark only the package it names.
    single = Part.from_row(_row(cell="AND2", part_suffix="1G08", gates_per_pkg="1"))
    dual = Part.from_row(_row(cell="AND2", part_suffix="2G08", gates_per_pkg="2", package="VSSOP-8"))
    mark_packaging_verification([single, dual], {"74AUP2G08": "verified"})
    assert single.packaging_is_verified is False
    assert dual.packaging_is_verified is True


def test_parse_refs_reads_only_the_electrical_table(tmp_path: Path):
    refs = tmp_path / "parts.refs.md"
    refs.write_text(
        "| cell | datasheet | revision | table/page | electrical status |\n"
        "|------|-----------|----------|------------|-------------------|\n"
        "| INV | TBD | TBD | TBD | placeholder — unverified |\n"
        "\n"
        "## Packaging citations\n"
        "| part_number | datasheet | revision | table/page | packaging status |\n"
        "|-------------|-----------|----------|------------|------------------|\n"
        "| 74AUP2G08 | Nexperia 74AUP2G08 data sheet | 2023-07-19 | Table 3 | verified |\n"
    )
    assert parse_refs(refs) == {"INV": "placeholder — unverified"}
    assert parse_refs_packaging(refs) == {"74AUP2G08": "verified"}


def test_load_parts_cited_reads_companion_refs(tmp_path: Path):
    csv = tmp_path / "parts.csv"
    csv.write_text(
        "cell,tier,family,part_suffix,equivalents,function,inputs,gates_per_pkg,"
        "package,mfrs,vcc_min,vcc_max,area,tpd_ns,iq_ua\n"
        'INV,G,AUP,1G04,,!A,1,1,SOT-353,"TI;Nexperia",0.8,3.6,1.0,4.6,0.9\n'
    )
    (tmp_path / "parts.refs.md").write_text(
        "| cell | datasheet | revision | table/page | electrical status |\n"
        "|------|-----------|----------|------------|-------------------|\n"
        "| INV | TBD | TBD | TBD | placeholder — unverified |\n"
    )
    parts = load_parts_cited(csv)
    assert parts[0].is_verified is False


def test_load_parts_cited_without_refs_fails_closed(tmp_path: Path):
    csv = tmp_path / "parts.csv"
    csv.write_text(
        "cell,tier,family,part_suffix,equivalents,function,inputs,gates_per_pkg,"
        "package,mfrs,vcc_min,vcc_max,area,tpd_ns,iq_ua\n"
        'INV,G,AUP,1G04,,!A,1,1,SOT-353,"TI;Nexperia",0.8,3.6,1.0,4.6,0.9\n'
    )
    parts = load_parts_cited(csv)
    assert parts[0].is_verified is False  # no refs -> placeholder, never verified


def test_placeholder_summary_counts_unverified_cells(tmp_path: Path):
    csv = tmp_path / "parts.csv"
    csv.write_text(
        "cell,tier,family,part_suffix,equivalents,function,inputs,gates_per_pkg,"
        "package,mfrs,vcc_min,vcc_max,area,tpd_ns,iq_ua\n"
        'INV,G,AUP,1G04,,!A,1,1,SOT-353,"TI;Nexperia",0.8,3.6,1.0,4.6,0.9\n'
        'BUF,G,AUP,1G34,,A,1,1,SOT-353,"TI;Nexperia",0.8,3.6,1.0,4.6,0.9\n'
    )
    (tmp_path / "parts.refs.md").write_text(
        "| cell | datasheet | revision | table/page | electrical status |\n"
        "|------|-----------|----------|------------|-------------------|\n"
        "| INV | TI SLVS123 | Rev B | Table 7.6 | verified |\n"
        "| BUF | TBD | TBD | TBD | placeholder — unverified |\n"
    )
    summary = placeholder_summary(csv)
    assert summary == {"total": 2, "unverified": 1, "unverifiedCells": ["BUF"]}
