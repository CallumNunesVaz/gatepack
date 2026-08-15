"""Tests for the parts data model (gatepack.parts)."""

from __future__ import annotations

import pytest

from gatepack.parts import (
    DropReason,
    Equivalent,
    Part,
    PartError,
    load_parts,
    select_for_liberty,
)


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


def _part(**overrides) -> Part:
    return Part.from_row(_row(**overrides))


def test_round_trip(tmp_path):
    csv_path = tmp_path / "parts.csv"
    csv_path.write_text(
        "cell,tier,family,part_suffix,equivalents,function,inputs,gates_per_pkg,"
        "package,mfrs,vcc_min,vcc_max,area,tpd_ns,iq_ua\n"
        'INV,G,AUP,1G04,,!A,1,1,SOT-353,"TI;Nexperia",0.8,3.6,1.0,4.6,0.9\n'
    )
    parts = load_parts(csv_path)
    assert len(parts) == 1
    inv = parts[0]
    assert inv.cell == "INV"
    assert inv.tier == "G"
    assert inv.function == "!A"
    assert inv.inputs == 1
    assert inv.mfrs == ["TI", "Nexperia"]
    assert inv.vcc_min == 0.8
    assert inv.tpd_ns == 4.6
    assert inv.is_second_sourced


def test_equivalents_parse():
    part = _part(
        cell="SUPERVISOR",
        tier="S",
        family="-",
        part_suffix="TPS3839",
        equivalents="APX803:Diodes;NCP303:onsemi",
        function="",
        inputs="1",
        mfrs="TI",
        tpd_ns="",
    )
    assert part.equivalents == [
        Equivalent(part_number="APX803", mfr="Diodes"),
        Equivalent(part_number="NCP303", mfr="onsemi"),
    ]
    # len(mfrs) + len(equivalents) == 1 + 2 >= 2 -> second sourced
    assert part.second_source_count == 3
    assert part.is_second_sourced


def test_equivalents_bad_form_names_cell():
    with pytest.raises(PartError, match="SUPERVISOR"):
        _part(
            cell="SUPERVISOR",
            tier="S",
            equivalents="APX803-without-colon",
            function="",
        )


def test_invalid_tier_names_cell():
    with pytest.raises(PartError, match="NAND2"):
        _part(cell="NAND2", tier="Q")


def test_vcc_min_exceeds_max_names_cell():
    with pytest.raises(PartError, match="BUF"):
        _part(cell="BUF", vcc_min="3.6", vcc_max="0.8")


def test_bad_number_names_cell():
    with pytest.raises(PartError, match="XOR2"):
        _part(cell="XOR2", inputs="abc")


def test_missing_column_fails(tmp_path):
    csv_path = tmp_path / "parts.csv"
    csv_path.write_text("cell,tier,family,part_suffix\nINV,G,AUP,1G04\n")
    with pytest.raises(PartError, match="missing columns"):
        load_parts(csv_path)


def test_second_sourced_threshold():
    assert _part(mfrs="TI").is_second_sourced is False
    assert _part(mfrs="TI;Nexperia").is_second_sourced is True
    assert _part(mfrs="", equivalents="APX803:Diodes").is_second_sourced is False
    assert (
        _part(mfrs="TI", equivalents="APX803:Diodes").is_second_sourced is True
    )


def test_single_source_excluded_by_default():
    part = _part(mfrs="TI")
    included, excluded = select_for_liberty([part], project_vcc=3.3)
    assert included == []
    assert [e.reason for e in excluded] == [DropReason.SINGLE_SOURCE]


def test_allow_single_source_includes():
    part = _part(mfrs="TI")
    included, excluded = select_for_liberty(
        [part], project_vcc=3.3, allow_single_source=True
    )
    assert [p.cell for p in included] == ["INV"]
    assert excluded == []


def test_vcc_incompatible_excluded():
    # 74HC part: supply 2.0..6.0 V does not operate at 1.8 V (§9.4 [R4-8]).
    part = _part(
        cell="HC_NAND2",
        family="HC",
        mfrs="TI;Nexperia",
        vcc_min="2.0",
        vcc_max="6.0",
    )
    included, excluded = select_for_liberty([part], project_vcc=1.8)
    assert included == []
    assert [e.reason for e in excluded] == [DropReason.VCC]


def test_m_and_s_tier_excluded():
    m = _part(cell="CNT4", tier="M", function="", mfrs="TI;Nexperia")
    s = _part(
        cell="SUPERVISOR",
        tier="S",
        function="",
        mfrs="TI",
        equivalents="APX803:Diodes",
    )
    included, excluded = select_for_liberty([m, s], project_vcc=3.3)
    assert included == []
    assert [e.reason for e in excluded] == [DropReason.TIER, DropReason.TIER]


def test_part_number_composition():
    # 74-logic: family + suffix -> 74<FAMILY><SUFFIX>
    assert _part(cell="NAND2", family="AUP", part_suffix="1G00").part_number == "74AUP1G00"
    # suffix already carries the family (74HC4017)
    assert _part(cell="JOHN10", tier="M", family="HC", part_suffix="HC4017", function="").part_number == "74HC4017"
    # S-cell with no family uses the suffix verbatim
    assert _part(cell="SUPERVISOR", tier="S", family="-", part_suffix="TPS3839", function="").part_number == "TPS3839"
    # empty suffix -> empty part number
    assert _part(cell="DFF_S", part_suffix="").part_number == ""
