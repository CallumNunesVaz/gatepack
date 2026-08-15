"""Provenance capture (§15.1): parse Yosys ``write_json`` and recover ``gp_src``.

C1 emits Verilog carrying ``(* gp_src = "design.yaml:LINE:PATH" *)`` attributes on
every construct.  The attribute namespace is ``gp_src``, never ``src`` — Yosys
populates ``src`` itself with the Verilog file/line that created a cell and that
value wins, so anything reading ``src`` for gatepack provenance is reading
Yosys's data, not ours (docs/M0-FINDINGS.md §2).

Where the attribute lands depends on the declaration it is attached to
(docs/M0-FINDINGS.md §3):

* an attribute on a ``wire`` declaration attaches to the **net** (``netnames``
  entry), not to the combinational cell derived from it, and survives ``abc``
  intact;
* an attribute on a ``reg`` declaration reaches the flop **cell**, and survives
  ``dfflibmap`` intact.

This module therefore recovers two distinct carriers:

* :func:`capture_sources` — ``cell name -> SourceRef`` from cell attributes
  (the sequential carrier);
* :func:`capture_net_sources` — ``net name -> SourceRef`` from ``netnames``
  attributes (the combinational carrier).

Both are present in ``build/premap.json`` (written before ``dfflibmap``/``abc``)
and the net carrier is also present in ``build/mapped.json`` (it survives
``abc``).

The parser is written against the Yosys ``write_json`` shape and operates on
single-bit cells (post-``techmap`` ``$_*`` cells and the single-gate 74AUP
library are both single-bit).  Because Yosys is not installed in this
environment, the format assumptions below are documented in BUILD-NOTES and are
pinned by the synthetic-JSON unit tests rather than by a real run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

# The attribute namespace gatepack owns.  Never ``src`` (§M0.2).
PROVENANCE_ATTR = "gp_src"


@dataclass(frozen=True)
class SourceRef:
    """A parsed ``gp_src`` attribute: ``"design.yaml:42:transitions[2]"``.

    ``filename`` is the C1 source name, ``line`` the source line (or ``None``
    when C1 could not pin it), ``path`` the construct path (e.g.
    ``transitions[2]``), and ``raw`` the un-split string.
    """

    filename: str
    line: int | None
    path: str
    raw: str

    @classmethod
    def parse(cls, text: str) -> "SourceRef":
        filename, sep, rest = text.partition(":")
        if not sep:
            return cls(filename=text, line=None, path="", raw=text)
        line_text, _, path = rest.partition(":")
        line: int | None
        try:
            line = int(line_text)
        except ValueError:
            line = None
        return cls(filename=filename, line=line, path=path, raw=text)


@dataclass(frozen=True)
class PinRef:
    """A single-bit cell connection.

    ``net`` is the net name; it is empty when the pin is tied to a constant.
    ``constant`` is the tied value (``True``/``False``) when the pin is tied,
    or ``None`` either for a real net or for an unknown (``x``/``z``) tie.
    """

    net: str
    constant: bool | None

    @property
    def is_constant(self) -> bool:
        return not self.net and self.constant is not None

    @property
    def is_unknown(self) -> bool:
        return not self.net and self.constant is None


@dataclass(frozen=True)
class Cell:
    """One cell of a parsed Yosys netlist."""

    name: str
    type: str
    attributes: Mapping[str, object]
    connections: Mapping[str, PinRef]
    port_directions: Mapping[str, str]

    @property
    def gp_src(self) -> str | None:
        value = self.attributes.get(PROVENANCE_ATTR)
        return value if isinstance(value, str) else None

    @property
    def source(self) -> SourceRef | None:
        src = self.gp_src
        return SourceRef.parse(src) if src is not None else None


@dataclass(frozen=True)
class Netlist:
    """A single-module, single-bit view of a ``write_json`` document."""

    module: str
    cells: Mapping[str, Cell]
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    net_sources: Mapping[str, SourceRef] = field(default_factory=dict)


def parse_netlist_json(
    data: Mapping[str, object], module: str | None = None
) -> Netlist:
    """Parse a Yosys ``write_json`` document into a :class:`Netlist`.

    ``module`` selects a module by name; when omitted the module with the most
    cells (the flattened top) is chosen.
    """
    modules = data.get("modules") or {}
    if not isinstance(modules, Mapping) or not modules:
        return Netlist(module=module or "", cells={})

    name = module if module is not None else _choose_module(modules)
    mod = modules.get(name) or {}
    if not isinstance(mod, Mapping):
        return Netlist(module=name, cells={})

    bit_to_net, net_sources = _parse_netnames(mod.get("netnames"))
    inputs, outputs = _resolve_ports(mod.get("ports"), bit_to_net)

    cells: dict[str, Cell] = {}
    raw_cells = mod.get("cells") or {}
    if isinstance(raw_cells, Mapping):
        for cell_name, cell_info in raw_cells.items():
            if not isinstance(cell_info, Mapping):
                continue
            cells[cell_name] = _resolve_cell(cell_name, cell_info, bit_to_net)

    return Netlist(
        module=name,
        cells=cells,
        inputs=tuple(inputs),
        outputs=tuple(outputs),
        net_sources=net_sources,
    )


def read_netlist_json(path: str | Path, module: str | None = None) -> Netlist:
    """Read a ``write_json`` file and parse it."""
    return parse_netlist_json(json.loads(Path(path).read_text()), module=module)


def capture_sources(netlist: Netlist) -> dict[str, SourceRef]:
    """Extract ``cell name -> SourceRef`` for every cell carrying a ``gp_src``.

    C1 annotates ``reg`` declarations, and Yosys propagates those attributes onto
    the flop cells through ``proc``/``flatten``/``opt``/``techmap``, so flop cell
    attributes are the sequential recovery point and survive ``dfflibmap``.
    Combinational cells do not carry a ``gp_src`` cell attribute — their
    provenance lives on the net (see :func:`capture_net_sources`).  Cells that
    carry no ``gp_src`` are simply absent from the result.
    """
    sources: dict[str, SourceRef] = {}
    for name, cell in netlist.cells.items():
        if cell.source is not None:
            sources[name] = cell.source
    return sources


def capture_net_sources(netlist: Netlist) -> dict[str, SourceRef]:
    """Extract ``net name -> SourceRef`` for every net carrying a ``gp_src``.

    C1 annotates ``wire`` declarations, so the attribute lives in the
    ``netnames`` entry and survives ``abc`` intact.  This is the primary
    combinational carrier (§15.1, docs/M0-FINDINGS.md §3).
    """
    return dict(netlist.net_sources)


def _choose_module(modules: Mapping[str, object]) -> str:
    best = ""
    best_count = -1
    for name, mod in modules.items():
        if not isinstance(mod, Mapping):
            continue
        raw_cells = mod.get("cells")
        count = len(raw_cells) if isinstance(raw_cells, Mapping) else 0
        if count > best_count:
            best, best_count = name, count
    return best


def _parse_netnames(
    raw: object,
) -> tuple[dict[int, str], dict[str, SourceRef]]:
    """Invert ``netnames`` into ``bit index -> net`` and ``net -> SourceRef``."""
    bit_to_net: dict[int, str] = {}
    net_sources: dict[str, SourceRef] = {}
    if not isinstance(raw, Mapping):
        return bit_to_net, net_sources
    for net, info in raw.items():
        if not isinstance(info, Mapping):
            continue
        bits = info.get("bits") or []
        for bit in bits:
            if isinstance(bit, int):
                bit_to_net[bit] = net
        attrs = info.get("attributes")
        if isinstance(attrs, Mapping):
            value = attrs.get(PROVENANCE_ATTR)
            if isinstance(value, str):
                net_sources[net] = SourceRef.parse(value)
    return bit_to_net, net_sources


def _resolve_ports(
    raw: object, bit_to_net: Mapping[int, str]
) -> tuple[list[str], list[str]]:
    inputs: list[str] = []
    outputs: list[str] = []
    if not isinstance(raw, Mapping):
        return inputs, outputs
    for port, info in raw.items():
        if not isinstance(info, Mapping):
            continue
        direction = info.get("direction")
        nets = [
            name
            for bit in (info.get("bits") or [])
            if isinstance(bit, int) and (name := bit_to_net.get(bit)) is not None
        ]
        if direction == "input":
            inputs.extend(nets)
        elif direction == "output":
            outputs.extend(nets)
    return inputs, outputs


def _resolve_cell(
    name: str, info: Mapping[str, object], bit_to_net: Mapping[int, str]
) -> Cell:
    connections: dict[str, PinRef] = {}
    raw_connections = info.get("connections") or {}
    if isinstance(raw_connections, Mapping):
        for port, bits in raw_connections.items():
            if not isinstance(bits, list) or not bits:
                continue
            connections[port] = _resolve_bit(bits[0], bit_to_net)

    port_directions: dict[str, str] = {}
    raw_dirs = info.get("port_directions") or {}
    if isinstance(raw_dirs, Mapping):
        for port, direction in raw_dirs.items():
            if isinstance(direction, str):
                port_directions[port] = direction

    attributes = info.get("attributes") or {}
    if not isinstance(attributes, Mapping):
        attributes = {}

    return Cell(
        name=name,
        type=str(info.get("type", "")),
        attributes=attributes,
        connections=connections,
        port_directions=port_directions,
    )


def _resolve_bit(bit: object, bit_to_net: Mapping[int, str]) -> PinRef:
    if isinstance(bit, str):
        return PinRef(net="", constant=_constant_value(bit))
    if isinstance(bit, int):
        net = bit_to_net.get(bit, "")
        return PinRef(net=net, constant=None)
    return PinRef(net="", constant=None)


def _constant_value(bit: str) -> bool | None:
    if bit == "1":
        return True
    if bit == "0":
        return False
    return None
