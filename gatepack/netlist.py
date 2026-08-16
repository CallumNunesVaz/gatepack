"""Mapped-netlist model shared by the packer (C5), emitters (C6) and analysis (C7).

Represents the C3 output (Yosys ``mapped.json``) in a form the downstream
components can consume without Yosys.  Provides:

* :class:`MappedCell` / :class:`MappedNetlist` — the model.
* :func:`parse_mapped_json` — the Yosys ``write_json`` parser.
* :func:`resolve_parts` — attach a :class:`~gatepack.parts.Part` and tier to each
  cell by Liberty cell name.
* :func:`stable_cell_names` — [R4-19] stage 1: deterministic, best-effort-stable
  naming from function + topologically-ordered input-cone hashes.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Mapping as MappingABC
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

from gatepack import pins
from gatepack.parts import Part

TIER_G = "G"
TIER_F = "F"
TIER_M = "M"
TIER_S = "S"

_CONSTANTS = frozenset({"0", "1", "x", "z"})


@dataclass(frozen=True)
class MappedCell:
    """One mapped cell instance in the netlist.

    ``cell`` is the Liberty cell name (Yosys ``type``); ``tier`` is G/F/M/S;
    ``part`` the resolved ``parts.csv`` row (``None`` when unresolved);
    ``connections`` maps pin name -> net name (constants appear as ``"0"``/``"1"``);
    ``directions`` maps pin name -> ``"input"``/``"output"``.
    """

    name: str
    cell: str
    tier: str
    part: Part | None = None
    connections: Mapping[str, str] = field(default_factory=dict)
    directions: Mapping[str, str] = field(default_factory=dict)

    @property
    def input_pins(self) -> tuple[str, ...]:
        return tuple(sorted(p for p, d in self.directions.items() if d == "input"))

    @property
    def output_pins(self) -> tuple[str, ...]:
        return tuple(sorted(p for p, d in self.directions.items() if d == "output"))


@dataclass(frozen=True)
class MappedNetlist:
    top: str
    cells: tuple[MappedCell, ...]
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()


def cell_from_part(
    name: str,
    part: Part,
    connections: Mapping[str, str] | None = None,
) -> MappedCell:
    """Build a :class:`MappedCell` from a resolved part (test/orchestrator path)."""
    directions = pins.cell_pin_directions(part)
    return MappedCell(
        name=name,
        cell=part.cell,
        tier=part.tier,
        part=part,
        connections=dict(connections or {}),
        directions=directions,
    )


def parse_mapped_json(text: str) -> MappedNetlist:
    """Parse a Yosys ``write_json`` document into a :class:`MappedNetlist`.

    Exercised against real Yosys 0.23 output via the toolchain container as
    well as hand-written fixtures.
    """
    data = json.loads(text)
    modules = data.get("modules", {})
    if not modules:
        raise ValueError("mapped.json has no 'modules'")
    top, module = next(iter(modules.items()))

    netnames = module.get("netnames", {})
    bit_to_net: dict[int, str] = {}
    for net, info in netnames.items():
        for bit in info.get("bits", []):
            if isinstance(bit, int):
                bit_to_net[bit] = net

    ports = module.get("ports", {})

    # A bit can carry several net names. C1 deliberately emits `<out>_int`
    # intermediates to hold provenance (M0-FINDINGS §1), so an output bit is
    # named both `walk` and `walk_int`, and the loop above keeps whichever came
    # last. Port names must win: `inputs`/`outputs` below are port names, and
    # any consumer that compares a cell connection against them silently
    # matches nothing otherwise.
    #
    # That is not hypothetical. It made SCOAP report every output-driving net
    # as unobservable - including all four of the showcase's outputs - which
    # reads as "this design is untestable".
    for name, info in ports.items():
        for bit in info.get("bits", []):
            if isinstance(bit, int):
                bit_to_net[bit] = name

    inputs = tuple(
        name for name, info in ports.items() if info.get("direction") == "input"
    )
    outputs = tuple(
        name for name, info in ports.items() if info.get("direction") == "output"
    )

    cells: list[MappedCell] = []
    for name, info in module.get("cells", {}).items():
        directions = info.get("port_directions", {})
        connections: dict[str, str] = {}
        for pin, bits in info.get("connections", {}).items():
            connections[pin] = _resolve_connection(bits, bit_to_net)
        cells.append(
            MappedCell(
                name=name,
                cell=info.get("type", ""),
                tier="",
                connections=connections,
                directions=dict(directions),
            )
        )

    cells.sort(key=lambda c: c.name)
    return MappedNetlist(
        top=top, cells=tuple(cells), inputs=inputs, outputs=outputs
    )


def _resolve_connection(bits: object, bit_to_net: Mapping[int, str]) -> str:
    if isinstance(bits, str):
        return bits
    if isinstance(bits, (list, tuple)):
        resolved = [
            b if isinstance(b, str) else bit_to_net.get(b, f"<bit{b}>") for b in bits
        ]
        return resolved[0] if len(resolved) == 1 else "|".join(resolved)
    return str(bits)


def resolve_parts(netlist: MappedNetlist, parts: Sequence[Part]) -> MappedNetlist:
    """Attach a part and tier to each cell by Liberty cell name.

    Cells whose ``type`` is not in the library keep ``part=None`` and ``tier=""``;
    callers decide whether that is an error.  M-cell pin tables live in
    ``gatepack/macros`` and are not available here, so a cell with no directions
    and an unknown pin table keeps its directions empty rather than failing.
    """
    by_cell = {p.cell: p for p in parts}

    def _directions(c: MappedCell) -> dict[str, str]:
        if c.directions:
            return dict(c.directions)
        part = by_cell.get(c.cell)
        if part is None:
            return {}
        try:
            return pins.cell_pin_directions(part)
        except KeyError:
            return {}

    cells = tuple(
        MappedCell(
            name=c.name,
            cell=c.cell,
            tier=(by_cell[c.cell].tier if c.cell in by_cell else ""),
            part=by_cell.get(c.cell),
            connections=c.connections,
            directions=_directions(c),
        )
        for c in netlist.cells
    )
    return MappedNetlist(
        top=netlist.top, cells=cells, inputs=netlist.inputs, outputs=netlist.outputs
    )


class CellNames(MappingABC[str, str]):
    """The two cell-name spaces, reconciled in exactly one place.

    A mapped cell has two names, and confusing them has caused real defects:

    * the **instance** name — what Yosys/ABC emit and what ``MappedCell.name``
      holds (``$abc$148$...$154``); renumbered by every synthesis;
    * the **stable** name — the cone-hash from :func:`stable_cell_names`
      (``OR2__3cf29954``); deterministic across runs.

    This object owns *both* directions of the mapping, so a call site never has
    to guess which space a ``str`` is in or re-derive the reverse lookup.  It is
    a :class:`~collections.abc.Mapping` keyed by **instance** name (so
    ``dict(names)`` is instance -> stable, the shape the IPC contract exposes
    as ``stableCellNames``), and it adds two explicit, direction-named methods
    that hard-error on a name from the wrong space:

    * :meth:`to_stable` — instance -> stable;
    * :meth:`to_instance` — stable -> instance.

    Both raise :class:`KeyError` with a message that names the space, so passing
    an instance name where a stable one belongs fails loudly instead of
    silently producing a wrong answer.
    """

    def __init__(self, instance_to_stable: Mapping[str, str]) -> None:
        by_instance = dict(instance_to_stable)
        by_stable: dict[str, str] = {}
        for instance, stable in by_instance.items():
            if stable in by_stable:
                raise ValueError(
                    f"two cells map to the same stable name {stable!r}: "
                    f"{by_stable[stable]!r} and {instance!r}"
                )
            by_stable[stable] = instance
        self._by_instance = by_instance
        self._by_stable = by_stable

    def __getitem__(self, instance: str) -> str:
        return self.to_stable(instance)

    def __iter__(self) -> Iterator[str]:
        return iter(self._by_instance)

    def __len__(self) -> int:
        return len(self._by_instance)

    def __repr__(self) -> str:
        return f"CellNames({self._by_instance!r})"

    def to_stable(self, instance: str) -> str:
        try:
            return self._by_instance[instance]
        except KeyError:
            raise KeyError(f"{instance!r} is not a known instance name") from None

    def to_instance(self, stable: str) -> str:
        try:
            return self._by_stable[stable]
        except KeyError:
            raise KeyError(f"{stable!r} is not a known stable name") from None

    def stable_of(self, cell: MappedCell) -> str:
        """The stable name of ``cell`` (an instance -> stable lookup)."""
        return self.to_stable(cell.name)

    @property
    def stable_names(self) -> tuple[str, ...]:
        """The stable names (the *values* of the instance -> stable map)."""
        return tuple(self._by_stable)

    @property
    def instance_to_stable(self) -> dict[str, str]:
        """A plain instance -> stable dict (the ``stableCellNames`` IPC shape)."""
        return dict(self._by_instance)

    @classmethod
    def identity(cls, cells: Sequence[MappedCell]) -> CellNames:
        """An identity mapping (stable name == instance name) for ``cells``."""
        return cls({c.name: c.name for c in cells})


def stable_cell_names(netlist: MappedNetlist) -> CellNames:
    """Return a deterministic stable name for each cell ([R4-19] stage 1).

    A cell's identity is its Liberty function plus the hash of its
    topologically-ordered input cones.  Sequential (F/M) outputs are treated as
    cone leaves so combinational feedback through a flop does not create a
    cycle.  Identical structural cells are disambiguated deterministically.

    The *determinism* guarantee is exact; the *stability under re-optimisation*
    guarantee is best-effort (reduced churn, not eliminated) and is only fully
    observable against real Yosys output, which is not available here.

    Returns a :class:`CellNames` owning both directions of the instance<->stable
    mapping, so the reverse lookup is derived once rather than re-derived (and
    re-gotten-wrong) at each call site.
    """
    cells = netlist.cells
    by_name = {c.name: c for c in cells}

    driver_by_net: dict[str, str] = {}
    for c in cells:
        for pin, net in c.connections.items():
            if c.directions.get(pin) == "output":
                driver_by_net.setdefault(net, c.name)

    leaves: dict[str, str] = {n: f"i:{n}" for n in netlist.inputs}
    sequential = [c for c in cells if c.tier in (TIER_F, TIER_M)]
    for c in sequential:
        for pin, net in c.connections.items():
            if c.directions.get(pin) == "output":
                leaves.setdefault(net, f"{c.cell}@{c.name}")

    combinational = [c for c in cells if c.tier in ("", TIER_G)]
    order = _topo_order(combinational, driver_by_net)
    order.extend(sorted(sequential, key=lambda c: c.name))
    order.extend(
        sorted(
            (c for c in cells if c.tier in (TIER_S,)),
            key=lambda c: c.name,
        )
    )

    sig: dict[str, str] = {}
    for c in order:
        sig[c.name] = _cone_sig(c, sig, leaves, driver_by_net)
    for c in cells:
        sig.setdefault(c.name, _cone_sig(c, sig, leaves, driver_by_net))

    names: dict[str, str] = {}
    groups: dict[str, list[MappedCell]] = {}
    for c in cells:
        groups.setdefault(f"{c.cell}__{sig[c.name][:8]}", []).append(c)
    for base in sorted(groups):
        grp = sorted(groups[base], key=lambda c: (_output_net(c), c.name))
        for i, c in enumerate(grp):
            names[c.name] = base if len(grp) == 1 else f"{base}_{i}"
    return CellNames(names)


def _output_net(cell: MappedCell) -> str:
    for pin in cell.output_pins:
        net = cell.connections.get(pin)
        if net is not None:
            return net
    return ""


def _topo_order(
    cells: Sequence[MappedCell], driver_by_net: Mapping[str, str]
) -> list[MappedCell]:
    """Kahn topological order of combinational cells; deterministic fallback.

    A cell depends on another when an input pin's net is driven by the other's
    output.  Residual (cycle) nodes are appended in sorted order so the result
    is deterministic even on unexpected feedback.
    """
    by_name = {c.name: c for c in cells}
    g_driver: dict[str, str] = {
        net: name
        for net, name in driver_by_net.items()
        if name in by_name
    }
    dependents: dict[str, set[str]] = {c.name: set() for c in cells}
    indegree: dict[str, int] = {c.name: 0 for c in cells}
    for c in cells:
        for pin in c.input_pins:
            net = c.connections.get(pin)
            dep = g_driver.get(net) if net is not None else None
            if dep is not None and dep != c.name:
                dependents[dep].add(c.name)
                indegree[c.name] += 1

    ready = sorted((c for c in cells if indegree[c.name] == 0), key=lambda c: c.name)
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
    remaining = sorted(
        (c for c in cells if c.name not in seen), key=lambda c: c.name
    )
    order.extend(remaining)
    return order


def _cone_sig(
    cell: MappedCell,
    sig: Mapping[str, str],
    leaves: Mapping[str, str],
    driver_by_net: Mapping[str, str],
) -> str:
    h = hashlib.sha256()
    h.update(cell.cell.encode())
    for pin in cell.input_pins:
        net = cell.connections.get(pin, "")
        h.update(b"\x1f")
        h.update(pin.encode())
        h.update(b"\x1e")
        h.update(_net_label(net, sig, leaves, driver_by_net).encode())
    return h.hexdigest()


def _net_label(
    net: str,
    sig: Mapping[str, str],
    leaves: Mapping[str, str],
    driver_by_net: Mapping[str, str],
) -> str:
    if net in _CONSTANTS:
        return net
    if net in leaves:
        return leaves[net]
    drv = driver_by_net.get(net)
    if drv is not None and drv in sig:
        return sig[drv]
    return net


def load_mapped_json(path: str | Path) -> MappedNetlist:
    """Read a ``mapped.json`` file and parse it."""
    return parse_mapped_json(Path(path).read_text())
