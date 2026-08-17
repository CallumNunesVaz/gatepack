"""A gate must physically fit its package (§10.1).

``pins_needed = gates_per_pkg * (inputs + outputs) + 2``  (+2 for VCC and GND).

For a G-cell ``inputs + outputs`` is the ``A``/``B``/``C`` inputs plus the single
``Y`` output; for an F-cell it is the D/CK/async inputs plus the ``Q`` output,
read from ``gatepack.pins`` so the netlist and this check cannot disagree.  The
package's own pin count is *data*, not recollection, so it is read from the
companion refs file (``libraries/74aup.refs.md``, "Package pin counts" table);
a package with no cited pin count is reported, never silently passed.  A row
with no candidate part (empty ``part_suffix``, e.g. ``DFF_S``) has a placeholder
package, not a fact, so it is skipped.
"""

from __future__ import annotations

from pathlib import Path

from gatepack.parts import Part, load_parts
from gatepack.pins import cell_pin_directions

LIBRARY = Path(__file__).resolve().parents[2] / "libraries" / "74aup.csv"
REFS = Path(__file__).resolve().parents[2] / "libraries" / "74aup.refs.md"


def parse_pin_counts(path: Path) -> dict[str, int]:
    """Return ``{package: pins}`` from the refs file's "Package pin counts" table."""
    counts: dict[str, int] = {}
    active = False
    for line in path.read_text().splitlines():
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
        counts[cells[0]] = int(cells[1])
    return counts


def pins_needed(part: Part) -> int:
    """Signal pins a single gate needs, plus the two power pins."""
    return part.gates_per_pkg * len(cell_pin_directions(part)) + 2


def check_pin_fit(
    parts: list[Part], pin_counts: dict[str, int]
) -> tuple[list[str], list[str]]:
    """Return ``(violations, uncited)`` over the G- and F-cells of ``parts``.

    A row that needs more pins than its package provides is a *violation*.  A
    row whose package has no cited pin count is *uncited* (reported, never
    silently passed).  A row with no candidate part is skipped: its package is
    a placeholder, not a fact.
    """
    violations: list[str] = []
    uncited: list[str] = []
    for part in parts:
        if part.tier not in ("G", "F"):
            continue
        if not part.part_suffix:
            continue
        if part.package not in pin_counts:
            uncited.append(f"{part.cell}: package {part.package!r} has no cited pin count")
            continue
        needed = pins_needed(part)
        if needed > pin_counts[part.package]:
            violations.append(
                f"{part.cell}: {part.part_number} needs {needed} pins "
                f"but {part.package} has {pin_counts[part.package]}"
            )
    return violations, uncited


def test_every_g_f_cell_fits_its_package():
    parts = load_parts(LIBRARY)
    pin_counts = parse_pin_counts(REFS)
    assert pin_counts, "refs pin-count table is empty — the check would pass vacuously"
    violations, uncited = check_pin_fit(parts, pin_counts)
    assert not uncited, (
        "G-/F-cell packages with no cited pin count are never silently passed; "
        "add them to the refs pin-count table:\n" + "\n".join(uncited)
    )
    assert not violations, (
        "rows that do not fit their package:\n" + "\n".join(violations)
    )


def test_pin_fit_flags_a_wrong_row():
    # A deliberately wrong row: a 3-input gate back in a 5-pin package.  This is
    # the falsification of the check — without it the test above would be
    # measuring nothing.
    wrong = Part(
        cell="AND3",
        tier="G",
        family="AUP",
        part_suffix="1G11",
        function="A&B&C",
        inputs=3,
        gates_per_pkg=1,
        package="SOT-353",
        mfrs=["TI", "Nexperia"],
        vcc_min=0.8,
        vcc_max=3.6,
        area=1.0,
    )
    violations, uncited = check_pin_fit([wrong], parse_pin_counts(REFS))
    assert not uncited
    assert violations and "AND3" in violations[0] and "SOT-353" in violations[0]
