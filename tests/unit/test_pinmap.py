"""Pin-map data model and the six consistency checks.

The pin map exists so a wrong pinout — placeholder or cited — is *caught* rather
than trusted.  Each of the six checks below has a falsifying input that violates
*exactly* that check and nothing else: the assertion is not just "the check
fires", it is "the other five checks stay silent on the same input", so a check
that silently stopped measuring would fail its own test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gatepack.parts import Part, Verification, load_parts
from gatepack.pinmap import (
    PartPinMap,
    PinMapError,
    PinMapRow,
    _check_gate_coverage,
    _check_gate_io,
    _check_pin_count,
    _check_pin_numbering,
    _check_power_pins,
    check_pinmaps,
    load_pinmaps,
    load_pinmaps_cited,
    parse_pin_refs,
    pin_map_summary,
)

LIBRARY = Path(__file__).resolve().parents[2] / "libraries" / "74aup.csv"
PINS_CSV = Path(__file__).resolve().parents[2] / "libraries" / "74aup.pins.csv"


def _part(
    cell: str = "NAND2",
    suffix: str = "1G00",
    inputs: int = 2,
    gpp: int = 1,
    package: str = "SOT-353",
    tier: str = "G",
) -> Part:
    return Part(
        cell=cell,
        tier=tier,
        family="AUP",
        part_suffix=suffix,
        function="!(A&B)" if cell == "NAND2" else "A&B",
        inputs=inputs,
        gates_per_pkg=gpp,
        package=package,
        mfrs=["TI"],
        vcc_min=0.8,
        vcc_max=3.6,
        area=1.0,
    )


def _pm(suffix: str, package: str, rows: list[tuple[int, str, int | None]]) -> PartPinMap:
    return PartPinMap(
        part_suffix=suffix,
        package=package,
        pins=[
            PinMapRow(part_suffix=suffix, package=package, pin=p, signal=s, gate=g)
            for (p, s, g) in rows
        ],
    )


# A valid single NAND2 gate in a 5-pin SOT-353: A, B, Y, VCC, GND.
_VALID_1G00 = [(1, "A", 1), (2, "B", 1), (3, "Y", 1), (4, "VCC", None), (5, "GND", None)]


def test_shipped_pin_map_is_consistent_and_entirely_placeholder():
    parts = load_parts(LIBRARY)
    pinmaps = load_pinmaps_cited(LIBRARY)
    assert len(pinmaps) == 20
    assert check_pinmaps(parts, pinmaps) == []
    assert all(pm.verification is Verification.PLACEHOLDER for pm in pinmaps.values())


def test_shipped_pin_map_covers_every_g_f_part_with_a_part_number():
    # A G/F part with a real part number must have a pin map; the pin map is the
    # only thing that stops the KiCad emitter inventing pin numbers for it.
    parts = load_parts(LIBRARY)
    pinmaps = load_pinmaps_cited(LIBRARY)
    mapped = {k for k in pinmaps}
    expected = {
        (p.part_suffix, p.package)
        for p in parts
        if p.tier in ("G", "F")
        and p.part_suffix
        and p.part_suffix != "1G74"  # DFF_SR: Q̄ not in the pin model yet
    }
    assert mapped == expected


def test_load_pinmaps_missing_columns_raises(tmp_path: Path):
    csv = tmp_path / "pins.csv"
    csv.write_text("part_suffix,package,pin\n1G00,SOT-353,1\n")
    with pytest.raises(PinMapError, match="missing columns"):
        load_pinmaps(csv)


def test_no_pin_map_file_is_an_empty_optional_map(tmp_path: Path):
    # A library with no .pins.csv must behave as if it had none — {} not an error.
    assert load_pinmaps_cited(tmp_path / "no_such.csv") == {}


# --- check 1: pin count equals the package's pin count ------------------------


def test_check_pin_count_fires_only_on_count_mismatch():
    part = _part()
    valid = _pm("1G00", "SOT-353", list(_VALID_1G00))
    assert _check_pin_count(valid, part) == []
    # an extra NC lead: 6 rows in a 5-pin package, and nothing else wrong
    wrong = _pm("1G00", "SOT-353", _VALID_1G00 + [(6, "NC", None)])
    assert _check_pin_count(wrong, part)
    assert _check_power_pins(wrong, part) == []
    assert _check_gate_coverage(wrong, part) == []
    assert _check_gate_io(wrong, part) == []
    assert _check_pin_numbering(wrong, part) == []


def test_check_pin_count_unknown_package_is_a_violation():
    part = _part()
    pm = _pm("1G00", "QFN-99", list(_VALID_1G00))
    assert "no known pin count" in _check_pin_count(pm, part)[0]


# --- check 2: exactly one VCC and one GND -------------------------------------


def test_check_power_pins_fires_only_on_power_mismatch():
    part = _part()
    # GND renamed to VCC: two VCC, zero GND — power count wrong, nothing else.
    wrong = _pm("1G00", "SOT-353", [
        (1, "A", 1), (2, "B", 1), (3, "Y", 1), (4, "VCC", None), (5, "VCC", None),
    ])
    assert _check_power_pins(wrong, part)
    assert _check_pin_count(wrong, part) == []
    assert _check_gate_coverage(wrong, part) == []
    assert _check_gate_io(wrong, part) == []
    assert _check_pin_numbering(wrong, part) == []


# --- check 3: covers exactly gates_per_pkg gates ------------------------------


def test_check_gate_coverage_fires_only_on_wrong_gate_set():
    # a dual NAND2 (2G00) in VSSOP-8, but the second gate is labelled 3.
    part = _part(cell="NAND2", suffix="2G00", inputs=2, gpp=2, package="VSSOP-8")
    wrong = _pm("2G00", "VSSOP-8", [
        (1, "A", 1), (2, "B", 1), (3, "Y", 1),
        (4, "A", 3), (5, "B", 3), (6, "Y", 3),
        (7, "VCC", None), (8, "GND", None),
    ])
    assert _check_gate_coverage(wrong, part)
    assert _check_pin_count(wrong, part) == []
    assert _check_power_pins(wrong, part) == []
    assert _check_gate_io(wrong, part) == []
    assert _check_pin_numbering(wrong, part) == []


# --- check 4: each gate has exactly inputs input pins and one output ----------


def test_check_gate_io_fires_only_on_wrong_signal_set():
    part = _part()
    # Y renamed to Z: the gate's signal set no longer matches the cell's pins.
    wrong = _pm("1G00", "SOT-353", [
        (1, "A", 1), (2, "B", 1), (3, "Z", 1), (4, "VCC", None), (5, "GND", None),
    ])
    assert _check_gate_io(wrong, part)
    assert _check_pin_count(wrong, part) == []
    assert _check_power_pins(wrong, part) == []
    assert _check_gate_coverage(wrong, part) == []
    assert _check_pin_numbering(wrong, part) == []


# --- check 5: pin numbers are contiguous from 1, each once --------------------


def test_check_pin_numbering_fires_only_on_noncontiguous_numbers():
    part = _part()
    wrong = _pm("1G00", "SOT-353", [
        (1, "A", 1), (2, "B", 1), (3, "Y", 1), (4, "VCC", None), (6, "GND", None),
    ])
    assert _check_pin_numbering(wrong, part)
    assert _check_pin_count(wrong, part) == []
    assert _check_power_pins(wrong, part) == []
    assert _check_gate_coverage(wrong, part) == []
    assert _check_gate_io(wrong, part) == []


# --- check 6: no two rows for the same key disagree (load time) ---------------


def test_load_pinmaps_rejects_disagreeing_rows_for_the_same_pin(tmp_path: Path):
    csv = tmp_path / "pins.csv"
    csv.write_text(
        "part_suffix,package,pin,signal,gate\n"
        "1G00,SOT-353,1,A,1\n"
        "1G00,SOT-353,1,B,1\n"  # pin 1 declared twice with different signals
    )
    with pytest.raises(PinMapError, match="declared twice"):
        load_pinmaps(csv)


# --- cross-checks against parts.csv -------------------------------------------


def test_check_pinmaps_flags_a_pin_map_with_no_matching_part():
    pm = _pm("9G99", "SOT-353", list(_VALID_1G00))
    violations = check_pinmaps([_part()], {("9G99", "SOT-353"): pm})
    assert any("no matching part row" in v for v in violations)


def test_check_pinmaps_flags_a_package_mismatch():
    # the pin map says SOT-363 but the part row says SOT-353.
    pm = _pm("1G00", "SOT-363", [
        (1, "A", 1), (2, "B", 1), (3, "Y", 1), (4, "VCC", None), (5, "GND", None),
    ])
    violations = check_pinmaps([_part()], {("1G00", "SOT-363"): pm})
    assert any("!= parts.csv package" in v for v in violations)


def test_pin_map_summary_reports_all_placeholder_for_shipped_library():
    summary = pin_map_summary(LIBRARY)
    assert summary == {"total": 20, "placeholder": 20, "cited": 0}


def test_lib_check_reports_pin_map_placeholder_count(capsys):
    # Acceptance: `gatepack lib check` reports the pin-map placeholder count, and
    # a test pins the number so it cannot silently drift to zero.
    from gatepack.cli import main

    assert main(["lib", "check", str(LIBRARY)]) == 0
    out = capsys.readouterr().out
    assert "pin maps: 20 part(s) mapped, 20 placeholder, 0 cited" in out


def test_doctor_surfaces_the_same_pin_map_count(capsys):
    # `gatepack doctor` surfaces the same placeholder count as `lib check`.
    from gatepack.cli import main

    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "bundled library pin maps: 20 part(s), 20 placeholder, 0 cited" in out


def test_lib_check_rejects_an_inconsistent_pin_map(tmp_path: Path, capsys):
    # "An inconsistent one is rejected before it ships" — `lib check` must exit
    # non-zero when a pin map violates a consistency check, not just report it.
    from gatepack.cli import main

    (tmp_path / "parts.csv").write_text(
        "cell,tier,family,part_suffix,equivalents,function,inputs,gates_per_pkg,"
        "package,mfrs,vcc_min,vcc_max,area,tpd_ns,iq_ua\n"
        'INV,G,AUP,1G04,,!A,1,1,SOT-353,"TI;Nexperia",0.8,3.6,1.0,4.6,0.9\n'
    )
    (tmp_path / "parts.refs.md").write_text(
        "| cell | datasheet | revision | table/page | electrical status |\n"
        "|------|-----------|----------|------------|-------------------|\n"
        "| INV | TBD | TBD | TBD | placeholder — unverified |\n"
    )
    # six pins for a five-pin package: violates check 1 (pin count).
    (tmp_path / "parts.pins.csv").write_text(
        "part_suffix,package,pin,signal,gate\n"
        "1G04,SOT-353,1,A,1\n"
        "1G04,SOT-353,2,Y,1\n"
        "1G04,SOT-353,3,VCC,\n"
        "1G04,SOT-353,4,GND,\n"
        "1G04,SOT-353,5,NC,\n"
        "1G04,SOT-353,6,NC,\n"
    )
    assert main(["lib", "check", str(tmp_path / "parts.csv")]) == 1
    err = capsys.readouterr().err
    assert "pin-map consistency violation" in err
    assert "pin count 6 != package SOT-353" in err


def test_pin_refs_status_is_placeholder_for_every_shipped_part():
    from gatepack.pinmap import pinmap_refs_path

    refs = parse_pin_refs(pinmap_refs_path(PINS_CSV))
    assert set(refs) == {pm.part_suffix for pm in load_pinmaps_cited(LIBRARY).values()}
    assert all("placeholder" in status.lower() for status in refs.values())


def test_package_pin_counts_mirror_the_refs_pin_count_table():
    # The PACKAGE_PIN_COUNTS constant must not drift from the cited table in
    # 74aup.refs.md ("Package pin counts").  A fabricated pin count is the one
    # number this module must never invent.
    from gatepack.pinmap import PACKAGE_PIN_COUNTS

    refs = Path(__file__).resolve().parents[2] / "libraries" / "74aup.refs.md"
    active = False
    table: dict[str, int] = {}
    for line in refs.read_text().splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            active = False
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if not cells or not cells[0]:
            continue
        if cells[0].lower() == "package":
            active = True
            continue
        if not active:
            continue
        if all(set(c) <= {"-", ":", " "} for c in cells[0]):
            continue
        table[cells[0]] = int(cells[1])
    for package, count in table.items():
        assert PACKAGE_PIN_COUNTS.get(package) == count, package


# ---------------------------------------------------------------------------
# A pin map is promoted to *verified* only by a real citation, never by the
# status word alone.  Reviewed addition: `verification_from_citation` reads only
# the status column, which is enough for electrical data (a wrong tPD is caught
# at review) but not for a pin number (it survives review and reaches a
# fabricator).  Editing "placeholder — unverified" to "verified" while the
# datasheet/revision/table columns still read TBD must not soften the notice.
# ---------------------------------------------------------------------------


def _refs_table(rows: str) -> str:
    return (
        "| part_suffix | datasheet | revision | table/page | pin status |\n"
        "|---|---|---|---|---|\n" + rows
    )


def test_status_word_alone_does_not_promote_a_pin_map(tmp_path):
    from gatepack.pinmap import parse_pin_refs_rows, pin_verification

    refs = tmp_path / "x.pins.refs.md"
    refs.write_text(_refs_table("| 1G00 | TBD | TBD | TBD | verified |\n"))
    rows = parse_pin_refs_rows(refs)
    assert pin_verification(rows["1G00"]) is Verification.PLACEHOLDER


def test_a_real_citation_does_promote_a_pin_map(tmp_path):
    from gatepack.pinmap import parse_pin_refs_rows, pin_verification

    refs = tmp_path / "x.pins.refs.md"
    refs.write_text(
        _refs_table("| 1G00 | SCES500N | Rev N (2016-08) | Table 6-1, p.12 | verified |\n")
    )
    rows = parse_pin_refs_rows(refs)
    assert pin_verification(rows["1G00"]) is Verification.VERIFIED


def test_a_placeholder_status_stays_placeholder_even_when_cited(tmp_path):
    from gatepack.pinmap import parse_pin_refs_rows, pin_verification

    refs = tmp_path / "x.pins.refs.md"
    refs.write_text(
        _refs_table(
            "| 1G00 | SCES500N | Rev N (2016-08) | Table 6-1, p.12 | placeholder — unverified |\n"
        )
    )
    rows = parse_pin_refs_rows(refs)
    assert pin_verification(rows["1G00"]) is Verification.PLACEHOLDER


def test_no_refs_row_is_placeholder():
    from gatepack.pinmap import pin_verification

    assert pin_verification(None) is Verification.PLACEHOLDER


# ---------------------------------------------------------------------------
# Tripwire, added in review 2026-08-24.
#
# Every example ships its own `parts.csv` (so a project can be opened without
# the repository), and the pin map is a *companion file* — `<stem>.pins.csv` —
# which the examples do not carry. The KiCad emitter therefore uses the pin map
# when building against `libraries/74aup.csv` and the positional fallback when
# building against `examples/<name>/parts.csv`.
#
# Measured today, those two produce identical pin numbers, because the shipped
# map IS the positional numbering. So there is no divergence to fix yet, and
# nothing to warn a user about.
#
# The day someone transcribes a real datasheet pinout into `74aup.pins.csv`,
# that stops being true and the same design silently emits different pin numbers
# depending on which `--library` path was passed — one of them wrong. This test
# fails on that day, which is the day the examples need the map copied beside
# them. It is a tripwire, not an assertion that positional numbering is correct.
# ---------------------------------------------------------------------------


def test_shipped_pin_map_still_agrees_with_the_positional_fallback():
    from gatepack.emit.kicad import _package_pin_entries, _positional_pins

    parts = load_parts(str(LIBRARY))
    pinmaps = load_pinmaps_cited(str(LIBRARY))
    checked = 0
    for part in parts:
        pm = pinmaps.get((part.part_suffix, part.package))
        if pm is None:
            continue
        mapped = _package_pin_entries(part, pm)
        fallback = [
            (name, direction, str(i + 1))
            for i, (name, direction) in enumerate(_positional_pins(part))
        ]
        # The map may declare extra package leads (an NC the fallback never
        # emitted); every pin the fallback *does* number must match.
        assert mapped[: len(fallback)] == fallback, (
            f"{part.part_suffix}/{part.package}: the pin map has diverged from the "
            "positional fallback. Examples ship parts.csv without a .pins.csv, so "
            "they now emit different pin numbers from a build against the full "
            "library. Copy the pin-map subset beside each example's parts.csv."
        )
        checked += 1
    assert checked >= 20, f"expected the shipped map to cover >=20 parts, checked {checked}"
