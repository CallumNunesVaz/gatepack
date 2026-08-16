"""Datasheet-citation checking, §10.1 [R4-21].

``gatepack lib check`` fails if any ``parts.csv`` row lacks an entry in the
companion ``<name>.refs.md`` file.  The refs file is a markdown table whose
first column is the cell name and whose last column records the verification
status of the electrical values::

    | cell | datasheet | revision | table/page | electrical status |
    |------|-----------|----------|------------|-------------------|
    | INV  | TBD       | —        | —          | placeholder — unverified |
"""

from __future__ import annotations

from pathlib import Path

from gatepack.parts import Part, mark_verification, load_parts


def find_refs_file(csv_path: str | Path) -> Path:
    """Return the ``<stem>.refs.md`` path beside ``csv_path``."""
    return Path(csv_path).with_suffix(".refs.md")


def parse_refs(path: str | Path) -> dict[str, str]:
    """Return ``{cell_name: status_text}`` from a refs markdown table.

    Only markdown table rows are considered; the header row (``cell``) and the
    ``|----|`` separator row are skipped.  A missing file yields an empty dict.
    """
    refs_path = Path(path)
    if not refs_path.exists():
        return {}

    citations: dict[str, str] = {}
    for line in refs_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if not cells or not cells[0]:
            continue
        name = cells[0]
        if name.lower() == "cell":
            continue
        if all(set(c) <= {"-", ":", " "} for c in name):
            continue
        citations[name] = cells[-1] if len(cells) > 1 else ""
    return citations


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
    marks a part verified or placeholder.  Parts loaded without a refs entry
    default to placeholder (fail-closed), so an uncited value is never mistaken
    for a cited one.
    """
    parts = load_parts(csv_path)
    citations = parse_refs(find_refs_file(csv_path))
    mark_verification(parts, citations)
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
