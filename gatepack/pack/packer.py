"""C5 — constrained bin packing (§12 C5, §9.7).

Nothing off the shelf does this; treat the generated code as a first draft.

The objective is the §9.7 cost function exactly::

    pack_cost = sum(package_cost) + spare_count * spare_leakage_weight

``package_cost`` is the part's ``area`` (the §10.1 cost metric).  Spares are a
*cost*, not free: a spare gate's inputs float near Vcc/2 and the resulting
crowbar current rises with temperature, so the packer will sometimes select
*more* packages to avoid leaving a spare.  Package count and spare count are
reported separately, never folded into a gates-per-package efficiency ratio
(§9.7 explains why that ratio punishes correct behaviour).

Cells group by function: a 74AUP2G02 holds two NOR2 gates, never a NOR and a
NAND.  Configurable-gate configurations sharing a ``part_suffix`` are distinct
functions and never share a gate slot; they are deduplicated at BOM time (§9.1).

Determinism is mandatory: identical input gives identical output — every
iteration and sort is keyed, and ties are broken lexicographically.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from gatepack.netlist import MappedCell
from gatepack.parts import Part

DEFAULT_SPARE_LEAKAGE_WEIGHT = 2.0

_EPS = 1e-12


class PackError(ValueError):
    """A packing constraint cannot be satisfied."""


@dataclass(frozen=True)
class PackerConfig:
    """Tunables for the packer.

    ``spare_leakage_weight`` prices a spare gate in the same cost units as
    ``area``.  ``force_groups`` is a list of cell-name groups (stable names)
    that must share a package; all cells in a group must be the same function.
    """

    spare_leakage_weight: float = DEFAULT_SPARE_LEAKAGE_WEIGHT
    force_groups: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True)
class PackageGroup:
    """A physical package holding one or more gates of one function."""

    part: Part
    cells: tuple[str, ...]  # stable cell names, sorted deterministically
    capacity: int
    spare: int
    rationale: str


@dataclass(frozen=True)
class PackingStats:
    package_count: int
    spare_count: int
    package_cost: float
    pack_cost: float


@dataclass(frozen=True)
class PackingResult:
    packed: tuple[PackageGroup, ...]
    unpacked: tuple[PackageGroup, ...]
    packed_stats: PackingStats
    unpacked_stats: PackingStats


def package_cost(part: Part) -> float:
    """The cost of one package of ``part`` (its ``area``)."""
    return part.area


def _pack_key(part: Part) -> tuple[str, str]:
    if part.tier == "G":
        return ("G", part.function or part.cell)
    return (part.tier, part.cell)


def pack(
    cells: Sequence[MappedCell],
    parts: Sequence[Part],
    config: PackerConfig | None = None,
    stable_names: Mapping[str, str] | None = None,
) -> PackingResult:
    """Pack ``cells`` into physical packages and return both views.

    ``cells`` must already carry resolved parts (``cell.part is not None``).
    ``parts`` is the full library, used to find packaging options (e.g. a
    2-gate 74AUP2G02 alongside a 1-gate 74AUP1G02 for the same function).
    """
    cfg = config or PackerConfig()
    names = dict(stable_names or {c.name: c.name for c in cells})
    by_name = {c.name: c for c in cells}

    options_by_key: dict[tuple[str, str], list[Part]] = {}
    for p in parts:
        options_by_key.setdefault(_pack_key(p), []).append(p)
    for opts in options_by_key.values():
        opts.sort(key=lambda p: (p.part_suffix, p.cell))

    groups: dict[tuple[str, str], list[MappedCell]] = {}
    for c in cells:
        if c.part is None:
            raise PackError(f"cell {c.name!r} has no resolved part")
        groups.setdefault(_pack_key(c.part), []).append(c)

    forced = _collect_forced(cells, names, cfg.force_groups, by_name)

    packed: list[PackageGroup] = []
    for key in sorted(groups):
        members = sorted(groups[key], key=lambda c: names[c.name])
        opts = options_by_key.get(key)
        if opts is None:
            opts = [members[0].part]  # type: ignore[list-item]
        free = [c for c in members if c.name not in forced["cells"]]
        if free:
            packed.extend(_pack_group(free, opts, cfg, names))
        for unit in forced["units"].get(key, []):
            packed.extend(_pack_forced(unit, opts, cfg, names))

    packed.sort(key=lambda g: (g.part.part_suffix, g.cells))
    unpacked = _unpacked(cells, names)

    return PackingResult(
        packed=tuple(packed),
        unpacked=tuple(unpacked),
        packed_stats=_stats(packed, cfg.spare_leakage_weight),
        unpacked_stats=_stats(unpacked, cfg.spare_leakage_weight),
    )


def _collect_forced(
    cells: Sequence[MappedCell],
    names: Mapping[str, str],
    force_groups: Sequence[Sequence[str]],
    by_name: Mapping[str, MappedCell],
) -> dict:
    known = set(names.values())
    units: dict[tuple[str, str], list[list[MappedCell]]] = {}
    forced_cells: set[str] = set()
    seen: set[str] = set()
    for group in force_groups:
        members: list[MappedCell] = []
        key: tuple[str, str] | None = None
        for n in group:
            if n not in known:
                raise PackError(f"force_groups references unknown cell {n!r}")
            if n in seen:
                raise PackError(f"cell {n!r} appears in more than one force_group")
            seen.add(n)
            cell = by_name[n]
            k = _pack_key(cell.part)  # type: ignore[arg-type]
            if key is None:
                key = k
            elif k != key:
                raise PackError(
                    f"force_groups {tuple(group)!r} mixes functions ({key} vs {k})"
                )
            members.append(cell)
        assert key is not None
        units.setdefault(key, []).append(members)
        forced_cells.update(group)
    return {"cells": forced_cells, "units": units}


def _pack_forced(
    members: Sequence[MappedCell],
    opts: Sequence[Part],
    cfg: PackerConfig,
    names: Mapping[str, str],
) -> list[PackageGroup]:
    part = _best_part(len(members), opts, cfg)
    spare = part.gates_per_pkg - len(members)
    cell_names = tuple(sorted(names[m.name] for m in members))
    return [
        PackageGroup(
            part=part,
            cells=cell_names,
            capacity=part.gates_per_pkg,
            spare=spare,
            rationale=_rationale("forced group", cell_names, part, spare),
        )
    ]


def _best_part(n: int, opts: Sequence[Part], cfg: PackerConfig) -> Part:
    feasible = [p for p in opts if p.gates_per_pkg >= n]
    if not feasible:
        raise PackError(
            f"force_group of {n} cells cannot fit any package "
            f"(capacities: {sorted(p.gates_per_pkg for p in opts)})"
        )
    return min(feasible, key=lambda p: _forced_cost(p, n, cfg))


def _forced_cost(part: Part, n: int, cfg: PackerConfig) -> float:
    return package_cost(part) + (part.gates_per_pkg - n) * cfg.spare_leakage_weight


def _pack_group(
    members: Sequence[MappedCell],
    opts: Sequence[Part],
    cfg: PackerConfig,
    names: Mapping[str, str],
) -> list[PackageGroup]:
    n = len(members)
    counts, _package_cost, _spare = _solve(n, opts, cfg.spare_leakage_weight)

    result: list[PackageGroup] = []
    cursor = 0
    for part, count in zip(opts, counts):
        for _ in range(count):
            take = members[cursor : cursor + part.gates_per_pkg]
            cursor += part.gates_per_pkg
            cell_names = tuple(sorted(names[m.name] for m in take))
            spare_slots = part.gates_per_pkg - len(take)
            result.append(
                PackageGroup(
                    part=part,
                    cells=cell_names,
                    capacity=part.gates_per_pkg,
                    spare=spare_slots,
                    rationale=_rationale("function group", cell_names, part, spare_slots),
                )
            )
    return result


def _rationale(kind: str, cells: tuple[str, ...], part: Part, spare: int) -> str:
    spare_note = f", {spare} spare gate(s)" if spare else ""
    return (
        f"{kind}: {part.cell} ({part.part_suffix}) holds "
        f"{len(cells)} gate(s){spare_note}"
    )


def _solve(
    n: int, opts: Sequence[Part], spare_weight: float
) -> tuple[list[int], float, int]:
    """Minimum-cost way to provide >= ``n`` gate slots.

    Coin-change DP over exact slot counts 0..n+max_cap-1; the answer is the
    cheapest k >= n after adding the spare penalty.  Deterministic: options are
    pre-sorted and ties break to the earlier option.
    """
    if n <= 0:
        return [0] * len(opts), 0.0, 0
    max_cap = max(p.gates_per_pkg for p in opts)
    k_limit = n + max_cap - 1
    inf = float("inf")
    dp = [inf] * (k_limit + 1)
    prev: list[int | None] = [None] * (k_limit + 1)
    dp[0] = 0.0
    for k in range(1, k_limit + 1):
        best = inf
        best_idx = None
        for idx, p in enumerate(opts):
            cap = p.gates_per_pkg
            if cap <= k and dp[k - cap] < inf:
                cand = dp[k - cap] + package_cost(p)
                if cand < best - _EPS:
                    best = cand
                    best_idx = idx
        if best_idx is not None:
            dp[k] = best
            prev[k] = best_idx

    best_total = inf
    best_k = None
    for k in range(n, k_limit + 1):
        if dp[k] < inf:
            total = dp[k] + (k - n) * spare_weight
            if total < best_total - _EPS:
                best_total = total
                best_k = k

    counts = [0] * len(opts)
    k = best_k
    while k is not None and k > 0:
        idx = prev[k]
        if idx is None:
            break
        counts[idx] += 1
        k -= opts[idx].gates_per_pkg
    spare = (best_k - n) if best_k is not None else 0
    return counts, (dp[best_k] if best_k is not None else 0.0), spare


def _unpacked(
    cells: Sequence[MappedCell], names: Mapping[str, str]
) -> list[PackageGroup]:
    """One package per cell (no multi-gate sharing)."""
    groups: list[PackageGroup] = []
    for c in sorted(cells, key=lambda c: names[c.name]):
        part = c.part  # type: ignore[assignment]
        spare = part.gates_per_pkg - 1
        groups.append(
            PackageGroup(
                part=part,
                cells=(names[c.name],),
                capacity=part.gates_per_pkg,
                spare=spare,
                rationale=f"unpacked: one {part.cell} per package",
            )
        )
    return groups


def _stats(groups: Sequence[PackageGroup], spare_weight: float) -> PackingStats:
    package_cost_sum = sum(package_cost(g.part) for g in groups)
    spare_count = sum(g.spare for g in groups)
    return PackingStats(
        package_count=len(groups),
        spare_count=spare_count,
        package_cost=package_cost_sum,
        pack_cost=package_cost_sum + spare_count * spare_weight,
    )
