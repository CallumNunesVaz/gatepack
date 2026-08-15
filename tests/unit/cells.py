"""Shared fixtures for the packer/emitter/analysis tests (M9/M10).

Small constructors for ``Part`` and ``MappedCell`` so tests can build synthetic
mapped netlists without Yosys.
"""

from __future__ import annotations

from gatepack.netlist import MappedCell, MappedNetlist, cell_from_part
from gatepack.parts import Part


def part(
    cell: str,
    tier: str = "G",
    function: str | None = None,
    inputs: int = 2,
    gates_per_pkg: int = 1,
    area: float = 1.0,
    tpd_ns: float | None = 5.0,
    iq_ua: float | None = 0.9,
    part_suffix: str | None = None,
    family: str = "AUP",
    package: str = "SOT-353",
    mfrs: tuple[str, ...] = ("TI", "Nexperia"),
) -> Part:
    return Part(
        cell=cell,
        tier=tier,
        family=family,
        part_suffix=part_suffix or cell,
        function=function,
        inputs=inputs,
        gates_per_pkg=gates_per_pkg,
        package=package,
        mfrs=list(mfrs),
        vcc_min=0.8,
        vcc_max=3.6,
        area=area,
        tpd_ns=tpd_ns,
        iq_ua=iq_ua,
    )


def cell(
    name: str,
    p: Part,
    connections: dict[str, str] | None = None,
) -> MappedCell:
    return cell_from_part(name, p, connections)


def netlist(top: str, cells: list[MappedCell], inputs=(), outputs=()) -> MappedNetlist:
    return MappedNetlist(top=top, cells=tuple(cells), inputs=tuple(inputs), outputs=tuple(outputs))
