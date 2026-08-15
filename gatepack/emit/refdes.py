"""Reference designator assignment and delta reporting ([R4-19] stage 3).

A refdes identifies a *package*, so it is assigned per package (never per logic
cone).  Packages are ordered deterministically and refdes are handed out in
sorted order.  The cell->refdes mapping is recorded here so it can be stored in
the provenance map rather than recomputed; ``refdes_delta`` reports renumbering
against a previous build so it is visible before layout, not discovered after.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from gatepack.pack.packer import PackageGroup

REFDES_PREFIX = "U"


def package_id(group: PackageGroup) -> str:
    """A deterministic identity for a package: its sorted cell names."""
    return "|".join(group.cells)


def assign_refdes(
    packages: Sequence[PackageGroup], start: int = 1
) -> list[tuple[str, PackageGroup]]:
    """Assign ``U<n>`` refdes to ``packages`` in sorted order.

    The sort key is ``(part_suffix, sorted cell names)`` so identical input
    always yields identical refdes.
    """
    ordered = sorted(packages, key=lambda g: (g.part.part_suffix, g.cells))
    return [(f"{REFDES_PREFIX}{i}", g) for i, g in enumerate(ordered, start=start)]


def refdes_map(assigned: Sequence[tuple[str, PackageGroup]]) -> dict[str, str]:
    """Return ``package_id -> refdes`` for a previous/current build comparison."""
    return {package_id(g): ref for ref, g in assigned}


@dataclass(frozen=True)
class RefdesDelta:
    added: tuple[str, ...]
    removed: tuple[str, ...]
    renumbered: tuple[tuple[str, str, str], ...]  # (package_id, old, new)
    unchanged: int


def refdes_delta(prev: Mapping[str, str], curr: Mapping[str, str]) -> RefdesDelta:
    """Compare two ``package_id -> refdes`` maps.

    ``renumbered`` lists packages that survived but changed refdes, so layout
    churn is visible before the board is touched.
    """
    added = tuple(sorted(k for k in curr if k not in prev))
    removed = tuple(sorted(k for k in prev if k not in curr))
    renumbered = tuple(
        sorted(
            (k, prev[k], curr[k])
            for k in curr
            if k in prev and prev[k] != curr[k]
        )
    )
    unchanged = sum(1 for k in curr if k in prev and prev[k] == curr[k])
    return RefdesDelta(
        added=added, removed=removed, renumbered=renumbered, unchanged=unchanged
    )
