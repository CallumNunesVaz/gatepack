"""BOM CSV emitter (§12 C6).

Columns (the §12 C6 order, with ``equivalents`` inserted after ``manufacturers``
to carry the §10.1 [R4-9] second-source status)::

    part_number,manufacturers,equivalents,package,quantity,refdes,tier,unit_price

``quantity`` is a count of packages (deduplicated by ``part_suffix`` so
configurable-gate configurations sharing a suffix collapse to one line, §9.1).
``unit_price`` is empty: ``parts.csv`` carries no price data ("where available").
"""

from __future__ import annotations

import re

import csv
import io
from dataclasses import dataclass
from typing import Sequence

from gatepack.pack.packer import PackageGroup

BOM_COLUMNS = (
    "part_number",
    "manufacturers",
    "equivalents",
    "package",
    "quantity",
    "refdes",
    "tier",
    "unit_price",
    "unverified",
)


@dataclass(frozen=True)
class BomRow:
    part_number: str
    manufacturers: str
    equivalents: str
    package: str
    quantity: int
    refdes: tuple[str, ...]
    tier: str
    unit_price: str = ""
    #: Gates the package holds. Not a BOM column — it is carried so the
    #: application can say whether grouping is possible at all rather than
    #: asserting it. A one-gate-per-package library makes packing a no-op, and
    #: a UI that claims otherwise (or hardcodes "inert" when it is not) is
    #: telling the user something false about their own design.
    gates_per_pkg: int = 1
    #: True when this part's electrical values (package, gates_per_pkg, tpd,
    #: iq, vcc) rest on placeholder data rather than a datasheet citation.  A
    #: reader of the BOM must not have to go back to parts.csv to find out.
    unverified: bool = False


def _refdes_key(ref: str) -> tuple[str, int, str]:
    """Sort refdes naturally: U9 before U10, not after it.

    Plain lexicographic order puts U10 before U7, which reads as a mistake
    on a BOM line and makes a part list hard to check against a board.
    """
    match = re.match(r"^([A-Za-z]+)(\d+)(.*)$", ref)
    if match is None:
        return (ref, 0, "")
    prefix, number, rest = match.groups()
    return (prefix, int(number), rest)


def collect_bom(assigned: Sequence[tuple[str, PackageGroup]]) -> list[BomRow]:
    """Aggregate assigned packages into BOM rows, deduplicated by part number."""
    by_part: dict[str, dict] = {}
    order: list[str] = []
    for ref, group in assigned:
        pn = group.part.part_number or group.part.cell
        if pn not in by_part:
            by_part[pn] = {
                "part_number": pn,
                "manufacturers": ";".join(group.part.mfrs),
                "equivalents": ";".join(str(e) for e in group.part.equivalents),
                "package": group.part.package,
                "refdes": [],
                "tier": group.part.tier,
                "unit_price": "",
                "gates_per_pkg": group.part.gates_per_pkg,
                "unverified": not group.part.is_verified,
            }
            order.append(pn)
        by_part[pn]["refdes"].append(ref)
    rows = [
        BomRow(
            part_number=pn,
            manufacturers=by_part[pn]["manufacturers"],
            equivalents=by_part[pn]["equivalents"],
            gates_per_pkg=by_part[pn]["gates_per_pkg"],
            package=by_part[pn]["package"],
            quantity=len(by_part[pn]["refdes"]),
            refdes=tuple(sorted(by_part[pn]["refdes"], key=_refdes_key)),
            tier=by_part[pn]["tier"],
            unit_price="",
            unverified=by_part[pn]["unverified"],
        )
        for pn in order
    ]
    rows.sort(key=lambda r: (r.part_number, r.refdes))
    return rows


def emit_bom(assigned: Sequence[tuple[str, PackageGroup]]) -> str:
    """Render the BOM as deterministic CSV text."""
    rows = collect_bom(assigned)
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(BOM_COLUMNS)
    for r in rows:
        writer.writerow(
            [
                r.part_number,
                r.manufacturers,
                r.equivalents,
                r.package,
                r.quantity,
                ";".join(r.refdes),
                r.tier,
                r.unit_price,
                "yes" if r.unverified else "",
            ]
        )
    return buf.getvalue()
