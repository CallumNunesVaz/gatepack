"""Footprint pin map — the ``<name>.pins.csv`` schema and its consistency checks.

``parts.csv`` carries ``package`` but no pin map.  A pinout is a property of the
*ordered part* (part number + package), not of the cell: one cell (``INV``) is
several parts (``1G04``, ``2G04``, ``3G04``) with different pinouts.  This
module is the data model for ``<name>.pins.csv``, keyed on ``(part_suffix,
package)``, and the six cross-checks that make a *placeholder* pin map worth
having.

Column order::

    part_suffix,package,pin,signal,gate

``signal`` uses the per-cell pin names ``gatepack/pins.py`` already owns (the
``A``/``B``/``C`` inputs plus ``Y`` for G-cells, ``D``/``CK``/async controls plus
``Q`` for F-cells) plus ``VCC``/``GND`` and the no-connect filler ``NC``.  ``gate``
is the 1-based gate index within the package, empty for power and ``NC`` pins.

**A pin map is a placeholder unless its citation says otherwise.**  Every pin
number in the shipped library is a placeholder: this project has no datasheets,
and a remembered pinout is a fabrication.  A pin map's *provenance* reuses
``gatepack.parts.Verification`` — fail-closed, so a pin map with no refs entry
is a placeholder, never assumed verified.  What a placeholder pin map *does*
deliver is the six consistency checks below: a wrong pinout (placeholder or
cited) that misdescribes a part's pin count, gate count or per-gate I/O is
caught here rather than trusted, because that is the class of error that reaches
a board.

Package pin counts are data already cited in ``libraries/74aup.refs.md``
("Package pin counts" table); :data:`PACKAGE_PIN_COUNTS` mirrors that table and
is cross-checked against it in the test suite.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Mapping, Sequence

from pydantic import BaseModel

from gatepack import pins
from gatepack.parts import Part, Verification, verification_from_citation

REQUIRED_COLUMNS = ("part_suffix", "package", "pin", "signal", "gate")

SIGNAL_VCC = "VCC"
SIGNAL_GND = "GND"
SIGNAL_NC = "NC"

POWER_SIGNALS = (SIGNAL_VCC, SIGNAL_GND)

# Package pin counts, mirroring the "Package pin counts" table in
# libraries/74aup.refs.md (each entry there carries a datasheet citation).  The
# pin map's first consistency check needs a pin count per package; this is that
# data, kept as a module constant and cross-checked against the refs file by
# tests/unit/test_pinmap.py so the two cannot drift.
PACKAGE_PIN_COUNTS = {
    "SOT-353": 5,
    "SOT-363": 6,
    "VSSOP-8": 8,
    "SO-16": 16,
    "SOT-23": 3,
}


class PinMapError(ValueError):
    """A ``.pins.csv`` file failed validation.

    ``key`` names the offending ``(part_suffix, package)``; ``message`` describes
    the failure.
    """

    def __init__(self, key: str, message: str) -> None:
        self.key = key
        super().__init__(f"{key}: {message}")


class PinMapRow(BaseModel):
    """One row of ``.pins.csv`` — a single physical pin."""

    part_suffix: str
    package: str
    pin: int
    signal: str
    #: 1-based gate index within the package; ``None`` for power/NC pins.
    gate: int | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, str]) -> "PinMapRow":
        part_suffix = (row.get("part_suffix") or "").strip()
        package = (row.get("package") or "").strip()
        signal = (row.get("signal") or "").strip()
        gate_raw = (row.get("gate") or "").strip()
        key = f"{part_suffix}/{package}"
        if not part_suffix:
            raise PinMapError(key, "part_suffix is empty")
        if not package:
            raise PinMapError(key, "package is empty")
        if not signal:
            raise PinMapError(key, f"signal is empty on pin {row.get('pin')!r}")
        try:
            pin = int((row.get("pin") or "").strip())
        except ValueError as exc:
            raise PinMapError(key, f"pin must be an integer, got {row.get('pin')!r}") from exc
        try:
            gate = int(gate_raw) if gate_raw else None
        except ValueError as exc:
            raise PinMapError(key, f"gate must be an integer or empty, got {gate_raw!r}") from exc
        return cls(
            part_suffix=part_suffix,
            package=package,
            pin=pin,
            signal=signal,
            gate=gate,
        )


class PartPinMap(BaseModel):
    """The pin map for one ordered part — ``(part_suffix, package)``."""

    part_suffix: str
    package: str
    pins: list[PinMapRow]
    #: Whether this pin map is cited (VERIFIED) or placeholder.  Defaults to
    #: placeholder — fail-closed — and is promoted only by a real citation in
    #: ``<name>.pins.refs.md``.
    verification: Verification = Verification.PLACEHOLDER

    @property
    def key(self) -> tuple[str, str]:
        return (self.part_suffix, self.package)

    @property
    def ordered_pins(self) -> list[PinMapRow]:
        """The pins sorted by pin number."""
        return sorted(self.pins, key=lambda r: r.pin)

    @property
    def is_verified(self) -> bool:
        return self.verification is Verification.VERIFIED

    def signal_pins(self, gate: int) -> list[PinMapRow]:
        """The signal pins belonging to ``gate`` (1-based)."""
        return [r for r in self.pins if r.gate == gate]


def pinmap_path(csv_path: str | Path) -> Path:
    """Return the ``<stem>.pins.csv`` path beside a ``parts.csv`` file."""
    return Path(csv_path).with_suffix(".pins.csv")


def pinmap_refs_path(pins_csv_path: str | Path) -> Path:
    """Return the ``<stem>.pins.refs.md`` path beside a ``.pins.csv`` file."""
    return Path(pins_csv_path).with_suffix(".refs.md")


#: Placeholders a refs table uses where a real citation field has not been
#: filled in.  A row carrying any of these has not been transcribed from a
#: document, whatever its status column says.
_UNFILLED_CITATION = frozenset({"", "tbd", "-", "—", "--", "n/a", "na", "?"})


def parse_pin_refs(path: str | Path) -> dict[str, str]:
    """Return ``{part_suffix: pin_status_text}`` from a ``.pins.refs.md`` table.

    The table is keyed by ``part_suffix`` and its last column is the *pin*
    status.  A missing file yields an empty dict (fail-closed at the caller).
    """
    return {name: row[-1] if row else "" for name, row in parse_pin_refs_rows(path).items()}


def parse_pin_refs_rows(path: str | Path) -> dict[str, list[str]]:
    """Return ``{part_suffix: [datasheet, revision, table/page, ..., status]}``.

    The whole row, not just the status column, because a pin map is promoted to
    *verified* only by a real citation — see :func:`pin_verification`.
    """
    if not Path(path).exists():
        return {}
    rows: dict[str, list[str]] = {}
    active = False
    for line in Path(path).read_text().splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            active = False
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if not cells or not cells[0]:
            continue
        name = cells[0]
        if name.lower() == "part_suffix":
            active = True
            continue
        if not active:
            continue
        if all(set(c) <= {"-", ":", " "} for c in name):
            continue
        rows[name] = cells[1:]
    return rows


def pin_verification(row: Sequence[str] | None) -> Verification:
    """Whether a refs row promotes its pin map to verified.

    Stricter than :func:`gatepack.parts.verification_from_citation`, which reads
    only the status word.  For *electrical* data that is enough — a wrong tPD is
    caught at review.  A wrong **pin number** is not: it survives review, reaches
    a fabricator, and shorts a rail to an output.  So a pin map is verified only
    when the row actually carries a document: editing the status column alone,
    while ``datasheet``/``revision``/``table`` still read ``TBD``, must not
    soften the "do not fabricate a board from these numbers" notice.

    ``None`` (no row at all) is a placeholder, fail-closed.
    """
    if row is None:
        return Verification.PLACEHOLDER
    status = verification_from_citation(row[-1] if row else None)
    if status is not Verification.PLACEHOLDER and any(
        cell.strip().lower() in _UNFILLED_CITATION for cell in row[:-1]
    ):
        return Verification.PLACEHOLDER
    return status


def load_pinmaps(path: str | Path) -> dict[tuple[str, str], PartPinMap]:
    """Load and validate a ``.pins.csv`` file, keyed by ``(part_suffix, package)``.

    The *structure* of the file is checked here (required columns, integer
    pins/gates, and — check six — no two rows for the same key disagree).  The
    six cross-checks against ``parts.csv`` data are :func:`check_pinmaps`.
    """
    path = Path(path)
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        missing = [c for c in REQUIRED_COLUMNS if c not in fieldnames]
        if missing:
            raise PinMapError("<header>", f"missing columns: {missing}")

        grouped: dict[tuple[str, str], dict[int, PinMapRow]] = {}
        for row in reader:
            parsed = PinMapRow.from_row(row)
            key = (parsed.part_suffix, parsed.package)
            by_pin = grouped.setdefault(key, {})
            if parsed.pin in by_pin:
                # check six: no two rows for the same key disagree.
                existing = by_pin[parsed.pin]
                if (existing.signal, existing.gate) != (parsed.signal, parsed.gate):
                    raise PinMapError(
                        f"{key[0]}/{key[1]}",
                        f"pin {parsed.pin} declared twice with different values: "
                        f"({existing.signal}, {existing.gate}) vs "
                        f"({parsed.signal}, {parsed.gate})",
                    )
            else:
                by_pin[parsed.pin] = parsed

    return {
        key: PartPinMap(
            part_suffix=key[0],
            package=key[1],
            pins=list(by_pin.values()),
        )
        for key, by_pin in grouped.items()
    }


def load_pinmaps_cited(csv_path: str | Path) -> dict[tuple[str, str], PartPinMap]:
    """Load the pin map beside ``csv_path``, with verification attached.

    A library with no ``<name>.pins.csv`` yields ``{}`` — the pin map is
    optional, and its absence must not change anything.  A pin map with no refs
    entry is a placeholder (fail-closed), never assumed verified.
    """
    path = pinmap_path(csv_path)
    if not path.exists():
        return {}
    pinmaps = load_pinmaps(path)
    rows = parse_pin_refs_rows(pinmap_refs_path(path))
    for pinmap in pinmaps.values():
        pinmap.verification = pin_verification(rows.get(pinmap.part_suffix))
    return pinmaps


# ---------------------------------------------------------------------------
# The six consistency checks.  Each returns the violations *it* owns, so a test
# can prove that an input violating exactly that check — and nothing else — is
# caught by that check and only that check.
# ---------------------------------------------------------------------------


def _check_pin_count(pm: PartPinMap, part: Part) -> list[str]:
    """Check 1: the number of pins equals the pin count implied by ``package``."""
    expected = PACKAGE_PIN_COUNTS.get(pm.package)
    if expected is None:
        return [f"{pm.part_suffix}: package {pm.package!r} has no known pin count"]
    if len(pm.pins) != expected:
        return [
            f"{pm.part_suffix}: pin count {len(pm.pins)} != package {pm.package} "
            f"({expected} pins)"
        ]
    return []


def _check_power_pins(pm: PartPinMap, part: Part) -> list[str]:
    """Check 2: exactly one VCC and exactly one GND."""
    vcc = [r for r in pm.pins if r.signal == SIGNAL_VCC]
    gnd = [r for r in pm.pins if r.signal == SIGNAL_GND]
    violations = []
    if len(vcc) != 1:
        violations.append(
            f"{pm.part_suffix}: expected exactly one VCC pin, got {len(vcc)}"
        )
    if len(gnd) != 1:
        violations.append(
            f"{pm.part_suffix}: expected exactly one GND pin, got {len(gnd)}"
        )
    return violations


def _check_gate_coverage(pm: PartPinMap, part: Part) -> list[str]:
    """Check 3: the map covers exactly ``gates_per_pkg`` gates."""
    gates = {r.gate for r in pm.pins if r.gate is not None}
    expected = set(range(1, part.gates_per_pkg + 1))
    if gates != expected:
        return [
            f"{pm.part_suffix}: gates {sorted(gates)} != expected 1.."
            f"{part.gates_per_pkg}"
        ]
    return []


def _check_gate_io(pm: PartPinMap, part: Part) -> list[str]:
    """Check 4: each gate has exactly the cell's input pins and one output pin.

    The pin map does not store direction — direction is the cell's property, so
    it is read from :func:`gatepack.pins.cell_pin_directions`.  A gate's signal
    set must equal the cell's pin table exactly, which is what makes "``inputs``
    input pins and exactly one output pin" true by construction.  Only the gates
    actually present in the map are checked; which gate indices exist is check 3's
    job, so the two cannot both fire on the same input.
    """
    if part.tier not in ("G", "F"):
        # M-/S-cell pin tables live elsewhere; check 4 is only meaningful for
        # the tiers whose per-cell pins gatepack/pins.py owns.
        return []
    try:
        directions = pins.cell_pin_directions(part)
    except KeyError:
        return [f"{pm.part_suffix}: no pin table for cell {part.cell!r}"]
    expected = set(directions)
    violations = []
    for gate in sorted({r.gate for r in pm.pins if r.gate is not None}):
        got = {r.signal for r in pm.pins if r.gate == gate}
        if got != expected:
            violations.append(
                f"{pm.part_suffix}: gate {gate} signals {sorted(got)} != expected "
                f"{sorted(expected)}"
            )
    return violations


def _check_pin_numbering(pm: PartPinMap, part: Part) -> list[str]:
    """Check 5: every pin number appears exactly once, contiguous from 1."""
    numbers = [r.pin for r in pm.pins]
    expected = list(range(1, len(numbers) + 1))
    if sorted(numbers) != expected:
        return [
            f"{pm.part_suffix}: pin numbers {sorted(numbers)} are not contiguous "
            f"from 1 (expected 1..{len(numbers)})"
        ]
    return []


def check_pinmaps(
    parts: Sequence[Part], pinmaps: Mapping[tuple[str, str], PartPinMap]
) -> list[str]:
    """Run the six consistency checks; return violation strings (empty = OK).

    A pin map is cross-checked against the ``parts.csv`` row that shares its
    ``part_suffix``: pin count vs package, VCC/GND counts, gate coverage vs
    ``gates_per_pkg``, per-gate I/O vs the cell's pin table, and contiguous pin
    numbering.  A pin map whose ``(part_suffix, package)`` has no matching part
    row, or whose package disagrees with the part's, is itself a violation.
    """
    violations: list[str] = []
    part_by_suffix = {p.part_suffix: p for p in parts if p.part_suffix}
    for (suffix, package) in sorted(pinmaps):
        pm = pinmaps[(suffix, package)]
        part = part_by_suffix.get(suffix)
        if part is None:
            violations.append(
                f"{suffix}: pin map has no matching part row in parts.csv"
            )
            continue
        if part.package != package:
            violations.append(
                f"{suffix}: pin map package {package!r} != parts.csv package "
                f"{part.package!r}"
            )
            continue
        violations.extend(_check_pin_count(pm, part))
        violations.extend(_check_power_pins(pm, part))
        violations.extend(_check_gate_coverage(pm, part))
        violations.extend(_check_gate_io(pm, part))
        violations.extend(_check_pin_numbering(pm, part))
    return violations


def pin_map_summary(csv_path: str | Path) -> dict:
    """The pin-map placeholder/cited counts for ``csv_path`` (for `lib check`).

    Returns ``{"total": N, "placeholder": M, "cited": K}``.  A library with no
    ``.pins.csv`` reports ``{"total": 0, "placeholder": 0, "cited": 0}`` — the
    pin map is optional, and zero is the honest count for "no pin maps".
    """
    pinmaps = load_pinmaps_cited(csv_path)
    placeholder = sum(1 for pm in pinmaps.values() if not pm.is_verified)
    return {
        "total": len(pinmaps),
        "placeholder": placeholder,
        "cited": len(pinmaps) - placeholder,
    }


def bundled_pin_map_summary() -> dict | None:
    """Pin-map counts for the library shipped beside the ``gatepack`` package.

    The shipped library (``libraries/74aup.csv``) is repo fixture data, not
    package data, so it is found only when a ``libraries/`` directory sits beside
    the ``gatepack`` package (a source checkout).  Returns ``None`` when it is
    not present, so the caller reports nothing rather than fabricating a count.
    """
    import gatepack

    lib_dir = Path(gatepack.__file__).resolve().parent.parent / "libraries"
    csv = lib_dir / "74aup.csv"
    if not csv.exists():
        return None
    return pin_map_summary(csv)


__all__ = [
    "PACKAGE_PIN_COUNTS",
    "POWER_SIGNALS",
    "PartPinMap",
    "PinMapError",
    "PinMapRow",
    "REQUIRED_COLUMNS",
    "SIGNAL_GND",
    "SIGNAL_NC",
    "SIGNAL_VCC",
    "check_pinmaps",
    "load_pinmaps",
    "load_pinmaps_cited",
    "parse_pin_refs",
    "parse_pin_refs_rows",
    "pin_verification",
    "pin_map_summary",
    "pinmap_path",
    "pinmap_refs_path",
]
