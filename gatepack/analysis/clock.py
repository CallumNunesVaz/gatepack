"""C7 clock and timing analysis (§9.6, §13.3).

Reports worst-case combinational depth and cumulative tPD from Liberty ``tpd_ns``
data, with the explicit caveat that this excludes PCB parasitics and is **not**
static timing analysis ([R4-16]: "no STA" is not "no timing model").  Skew is a
layout property; it is reported as an estimate with its assumption inline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from gatepack.netlist import MappedCell, MappedNetlist

# Estimated worst-case skew contribution per extra fanout load, in ns.  This is
# a placeholder constant — skew is a layout property and cannot be derived from
# the netlist — and is stated as such wherever it is used (§9.6).
ASSUMED_SKEW_NS_PER_LOAD = 0.25

_NOTE = (
    "excludes PCB parasitics; not static timing analysis (no clock-to-Q, no "
    "setup, no routing skew)"
)


@dataclass(frozen=True)
class TimingReport:
    combinational_depth: int
    cumulative_tpd_ns: float
    worst_path: tuple[str, ...]
    note: str


def flop_count(netlist: MappedNetlist) -> int:
    return sum(1 for c in netlist.cells if c.tier == "F")


def clock_fanout(netlist: MappedNetlist) -> int:
    """Clock loads: each F-cell is one load; each M-cell adds one clock pin."""
    return sum(1 for c in netlist.cells if c.tier in ("F", "M"))


def timing_analysis(netlist: MappedNetlist) -> TimingReport:
    """Worst-case combinational depth and cumulative tPD over the G-cell cones.

    Combinational depth counts G-cell levels; cumulative tPD sums each cell's
    ``tpd_ns`` along the worst path (flops and routing are not counted).  Cells
    with no ``tpd_ns`` contribute 0 to delay but still count a level.
    """
    cells = netlist.cells
    driver_by_net: dict[str, str] = {}
    for c in cells:
        for pin, net in c.connections.items():
            if c.directions.get(pin) == "output":
                driver_by_net.setdefault(net, c.name)

    leaves = set(netlist.inputs)
    for c in cells:
        if c.tier in ("F", "M"):
            for pin, net in c.connections.items():
                if c.directions.get(pin) == "output":
                    leaves.add(net)

    order = _combinational_order(cells, driver_by_net, leaves)

    depth: dict[str, int] = {n: 0 for n in leaves}
    tpd: dict[str, float] = {n: 0.0 for n in leaves}
    path: dict[str, tuple[str, ...]] = {n: () for n in leaves}

    worst = TimingReport(0, 0.0, (), _NOTE)

    for c in order:
        in_depth = 0
        in_tpd = 0.0
        best_net: str | None = None
        for pin in c.input_pins:
            net = c.connections.get(pin)
            if net is None:
                continue
            d = depth.get(net, 0)
            t = tpd.get(net, 0.0)
            if d > in_depth or (d == in_depth and t > in_tpd):
                in_depth, in_tpd = d, t
                best_net = net

        cell_depth = in_depth + 1
        cell_tpd = in_tpd + (c.part.tpd_ns if c.part and c.part.tpd_ns else 0.0)
        cell_path = path.get(best_net, ()) + (c.name,)

        for pin in c.output_pins:
            net = c.connections.get(pin)
            if net is None:
                continue
            if cell_depth > depth.get(net, 0) or (
                cell_depth == depth.get(net, 0) and cell_tpd > tpd.get(net, 0.0)
            ):
                depth[net] = cell_depth
                tpd[net] = cell_tpd
                path[net] = cell_path

        if cell_depth > worst.combinational_depth or (
            cell_depth == worst.combinational_depth
            and cell_tpd > worst.cumulative_tpd_ns
        ):
            worst = TimingReport(
                combinational_depth=cell_depth,
                cumulative_tpd_ns=cell_tpd,
                worst_path=cell_path,
                note=_NOTE,
            )

    return worst


def combinational_depth(netlist: MappedNetlist) -> int:
    return timing_analysis(netlist).combinational_depth


def cumulative_tpd_ns(netlist: MappedNetlist) -> float:
    return timing_analysis(netlist).cumulative_tpd_ns


def clock_margin_ns(
    period_ns: float,
    cumulative_tpd_ns: float,
    fanout: int,
    skew_per_load: float = ASSUMED_SKEW_NS_PER_LOAD,
) -> float:
    """Period margin after tPD and an estimated skew term.

    ``skew_per_load`` is a placeholder constant — real skew is a layout property
    (§9.6) — so the margin is advisory, not a sign-off number.
    """
    skew = max(0, fanout - 1) * skew_per_load
    return period_ns - cumulative_tpd_ns - skew


def _combinational_order(
    cells: Sequence[MappedCell],
    driver_by_net: Mapping[str, str],
    leaves: set[str],
) -> list[MappedCell]:
    comb = [c for c in cells if c.tier in ("", "G")]
    by_name = {c.name: c for c in comb}
    g_driver = {net: n for net, n in driver_by_net.items() if n in by_name}
    indegree = {c.name: 0 for c in comb}
    dependents: dict[str, list[str]] = {c.name: [] for c in comb}
    for c in comb:
        for pin in c.input_pins:
            net = c.connections.get(pin)
            dep = g_driver.get(net) if net is not None else None
            if dep is not None and dep != c.name:
                indegree[c.name] += 1
                dependents[dep].append(c.name)
    ready = sorted((c for c in comb if indegree[c.name] == 0), key=lambda c: c.name)
    order: list[MappedCell] = []
    seen: set[str] = set()
    while ready:
        nxt = ready.pop(0)
        order.append(nxt)
        seen.add(nxt.name)
        for dep in sorted(dependents[nxt.name]):
            indegree[dep] -= 1
            if indegree[dep] == 0:
                ready.append(by_name[dep])
                ready.sort(key=lambda c: c.name)
    order.extend(sorted((c for c in comb if c.name not in seen), key=lambda c: c.name))
    return order
