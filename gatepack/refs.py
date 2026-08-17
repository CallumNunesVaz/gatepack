"""Datasheet-citation checking, §10.1 [R4-21].

``gatepack lib check`` fails if any ``parts.csv`` row lacks an entry in the
companion ``<name>.refs.md`` file.  The refs file holds two markdown tables:

* an **electrical** table, keyed by ``cell``, whose last column records the
  verification status of the electrical values::

      | cell | datasheet | revision | table/page | electrical status |
      |------|-----------|----------|------------|-------------------|
      | INV  | TBD       | —        | —          | placeholder — unverified |

* a **packaging** table, keyed by ``part_number``, whose last column records
  the verification status of ``gates_per_pkg``/``package``::

      | part_number | datasheet | revision | table/page | packaging status |
      |-------------|-----------|----------|------------|------------------|
      | 74AUP2G08   | Nexperia 74AUP2G08 data sheet | 2023-07-19 | Ordering information (Table 3) | verified |

Packaging is keyed by part number, not cell, because one function cell is
offered as several packages (``AND2`` = ``74AUP1G08`` and ``74AUP2G08``); a
cell-level citation cannot say which of them had its gate count confirmed.
"""

from __future__ import annotations

from pathlib import Path

from gatepack.parts import (
    Part,
    mark_packaging_verification,
    mark_verification,
    load_parts,
)


def find_refs_file(csv_path: str | Path) -> Path:
    """Return the ``<stem>.refs.md`` path beside ``csv_path``."""
    return Path(csv_path).with_suffix(".refs.md")


def _parse_table(path: Path, header_name: str) -> dict[str, str]:
    """Return ``{key: last_column}`` for the markdown table keyed ``header_name``.

    The file may hold more than one table (electrical and packaging); a row's
    table membership is decided by its header row (first cell ``cell`` or
    ``part_number``).  A missing file yields an empty dict.
    """
    if not path.exists():
        return {}
    citations: dict[str, str] = {}
    active = False
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            active = False
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if not cells or not cells[0]:
            continue
        name = cells[0]
        lowered = name.lower()
        if lowered in ("cell", "part_number"):
            active = lowered == header_name
            continue
        if not active:
            continue
        if all(set(c) <= {"-", ":", " "} for c in name):
            continue
        citations[name] = cells[-1] if len(cells) > 1 else ""
    return citations


def parse_refs(path: str | Path) -> dict[str, str]:
    """Return ``{cell_name: electrical_status_text}`` from the refs table."""
    return _parse_table(Path(path), "cell")


def parse_refs_packaging(path: str | Path) -> dict[str, str]:
    """Return ``{part_number: packaging_status_text}`` from the refs table."""
    return _parse_table(Path(path), "part_number")


def missing_citations(parts: list[Part], citations: dict[str, str]) -> list[str]:
    """Cell names in ``parts`` that have no refs entry."""
    return [p.cell for p in parts if p.cell not in citations]


def check_citations(
    parts: list[Part], csv_path: str | Path
) -> tuple[list[str], Path]:
    """Return ``(missing_cells, refs_path)`` for ``parts`` against its refs file."""
    refs_path = find_refs_file(csv_path)
    citations = parse_refs(refs_path)
    return missing_citations(parts, citations), refs_path


def load_parts_cited(csv_path: str | Path) -> list[Part]:
    """Load ``parts.csv`` with each part's verification status attached.

    The refs file is the citation source of truth; its electrical-status column
    marks a part verified or placeholder, and its packaging table marks the
    ``gates_per_pkg``/``package`` facts separately.  Parts loaded without a
    refs entry default to placeholder (fail-closed), so an uncited value is
    never mistaken for a cited one.
    """
    parts = load_parts(csv_path)
    refs_path = find_refs_file(csv_path)
    mark_verification(parts, parse_refs(refs_path))
    mark_packaging_verification(parts, parse_refs_packaging(refs_path))
    return parts


def placeholder_summary(csv_path: str | Path) -> dict:
    """The placeholder/unverified cell count for ``csv_path`` (for `doctor`).

    Returns ``{"total": N, "unverified": M, "unverifiedCells": [...]}`` so the
    count is visible without a separate `lib check` run.  Only the *data* lives
    here; `gatepack/doctor.py` owns how it is surfaced in the doctor report.
    """
    parts = load_parts_cited(csv_path)
    unverified = [p.cell for p in parts if not p.is_verified]
    return {
        "total": len(parts),
        "unverified": len(unverified),
        "unverifiedCells": sorted(unverified),
    }
