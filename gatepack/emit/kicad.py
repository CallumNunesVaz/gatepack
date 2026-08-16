"""KiCad ``.net`` s-expression netlist emitter (§12 C6, [R4-20]).

Three pin cases are emitted distinctly, per [R4-20]:

* **rail tie-offs** — spare-gate inputs and constant ``"0"``/``"1"`` connections
  become nodes on the global ``GND``/``VCC`` nets (power references), and every
  component's ``VCC``/``GND`` power pins attach to those rails;
* **genuinely unconnected pins** — emitted in a dedicated ``no_connects``
  section (not silently attached to a rail);
* **S-cells** — carry no logic function, so they are rendered from their pin
  table only (no cone, no boolean function).

The format follows the KiCad legacy ``.net`` s-expression shape as closely as it
can be reproduced without KiCad installed; it has **not** been import-tested
against real KiCad.  Pin *numbers* are assigned deterministically (gate-1 pins,
gate-2 pins, ..., VCC, GND) because ``parts.csv`` carries no footprint pin map;
real numbers need footprint data (a data concern, not a code one).  No
timestamps appear anywhere in the payload (§C6).
"""

from __future__ import annotations

from typing import Mapping, Sequence

from gatepack import pins
from gatepack.netlist import CellNames, MappedCell, MappedNetlist
from gatepack.pack.packer import PackageGroup

LIB_NAME = "gatepack"

_TIE_HIGH = "1"
_TIE_LOW = "0"
_RAIL_VCC = "VCC"
_RAIL_GND = "GND"


def _q(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _atom(x: object) -> str:
    if isinstance(x, bool):
        return "1" if x else "0"
    if isinstance(x, int):
        return str(x)
    s = str(x)
    if s.startswith("(") and s.endswith(")"):
        return s  # already-rendered s-expression
    return _q(s)


def _sexp(head: str, *parts: object) -> str:
    body = " ".join(_atom(p) for p in parts)
    return f"({head}" + (f" {body}" if body else "") + ")"


def _package_pins(part) -> list[tuple[str, str]]:
    """Ordered ``(pin_name, direction)`` list for a package.

    Signal pins are gate-scoped for multi-gate packages (``1A``, ``1B``, ``2A``
    ...); VCC/GND are appended last.  The position in this list is the pin
    number (1-based), deterministic because ``cell_pin_directions`` is sorted.
    """
    signal = pins.cell_pin_directions(part)
    multi = part.gates_per_pkg > 1
    out: list[tuple[str, str]] = []
    for slot in range(part.gates_per_pkg):
        prefix = f"{slot + 1}" if multi else ""
        for name in sorted(signal):
            out.append((prefix + name, signal[name]))
    out.append((_RAIL_VCC, "power_in"))
    out.append((_RAIL_GND, "power_in"))
    return out


def _build_nets(
    assigned: Sequence[tuple[str, PackageGroup]],
    names: CellNames,
    cells_by_instance: Mapping[str, MappedCell],
) -> tuple[dict[str, list[tuple[str, str]]], list[tuple[str, str]]]:
    """Collect ``net_name -> [(refdes, pin_number), ...]`` and no-connect pins."""
    nets: dict[str, list[tuple[str, str]]] = {}
    no_connects: list[tuple[str, str]] = []

    for ref, group in assigned:
        part = group.part
        ordered = _package_pins(part)
        number = {name: str(i + 1) for i, (name, _) in enumerate(ordered)}
        signal = pins.cell_pin_directions(part)
        multi = part.gates_per_pkg > 1

        for slot in range(part.gates_per_pkg):
            prefix = f"{slot + 1}" if multi else ""
            if slot < len(group.cells):
                # `group.cells` holds STABLE names; cross back to the instance
                # name through the one reverse lookup so connections are read
                # off the right cell.
                cell = cells_by_instance[names.to_instance(group.cells[slot])]
                for pin_name in sorted(signal):
                    pkg_pin = prefix + pin_name
                    net = cell.connections.get(pin_name)
                    if net is None:
                        no_connects.append((ref, number[pkg_pin]))
                    elif net == _TIE_HIGH:
                        nets.setdefault(_RAIL_VCC, []).append((ref, number[pkg_pin]))
                    elif net == _TIE_LOW:
                        nets.setdefault(_RAIL_GND, []).append((ref, number[pkg_pin]))
                    else:
                        nets.setdefault(net, []).append((ref, number[pkg_pin]))
            else:
                # spare gate: tie inputs to a rail, leave output unconnected
                for pin_name, direction in sorted(signal.items()):
                    pkg_pin = prefix + pin_name
                    if direction == "input":
                        nets.setdefault(_RAIL_GND, []).append((ref, number[pkg_pin]))
                    else:
                        no_connects.append((ref, number[pkg_pin]))

        nets.setdefault(_RAIL_VCC, []).append((ref, number[_RAIL_VCC]))
        nets.setdefault(_RAIL_GND, []).append((ref, number[_RAIL_GND]))

    return nets, no_connects


def _components(assigned: Sequence[tuple[str, PackageGroup]]) -> list[str]:
    lines: list[str] = []
    for ref, group in assigned:
        part = group.part
        pn = part.part_number or part.cell
        lines.append(
            _sexp(
                "comp",
                "ref", ref,
                "value", pn,
                "footprint", part.package,
                "libsource", _sexp("lib", LIB_NAME, "part", pn),
            )
        )
    return lines


def _libparts(assigned: Sequence[tuple[str, PackageGroup]]) -> list[str]:
    seen: dict[str, str] = {}
    lines: list[str] = []
    for _, group in assigned:
        part = group.part
        pn = part.part_number or part.cell
        if pn in seen:
            continue
        seen[pn] = pn
        pin_lines = [
            _sexp("pin", "num", num, "name", name, "type", direction)
            for num, (name, direction) in (
                (str(i + 1), pd) for i, pd in enumerate(_package_pins(part))
            )
        ]
        lines.append(
            _sexp("libpart", "lib", LIB_NAME, "part", pn,
                  _sexp("pins", *pin_lines))
        )
    return lines


def emit_netlist(
    netlist: MappedNetlist,
    assigned: Sequence[tuple[str, PackageGroup]],
    stable_names: CellNames,
) -> str:
    """Emit the KiCad ``.net`` s-expression for the *packed* netlist.

    ``assigned`` is the ``(refdes, PackageGroup)`` list from
    :func:`gatepack.emit.refdes.assign_refdes`; ``stable_names`` is the
    :class:`CellNames` instance -> stable mapping, used to resolve a package's
    STABLE cell list back to its instance name (and therefore its connections).
    """
    cells_by_instance = {c.name: c for c in netlist.cells}
    nets, no_connects = _build_nets(assigned, stable_names, cells_by_instance)

    lines: list[str] = [_sexp("export", "version", "gatepack-0.1.0")]
    lines.append(
        _sexp(
            "design",
            "source", "gatepack",
            _sexp("sheet", "number", "1", "name", "", "tstamps", "/"),
        )
    )

    lines.append(_sexp("components", *_components(assigned)))
    lines.append(_sexp("libparts", *_libparts(assigned)))
    lines.append(_sexp("libraries", _sexp("library", "logical", LIB_NAME, "uri", "")))

    net_lines: list[str] = []
    for code, name in enumerate(sorted(nets), start=1):
        nodes = nets[name]
        node_lines = [
            _sexp("node", "ref", ref, "pin", pin) for ref, pin in sorted(nodes)
        ]
        net_lines.append(_sexp("net", "code", code, "name", name, *node_lines))
    lines.append(_sexp("nets", *net_lines))

    nc_lines = [
        _sexp("no_connect", "ref", ref, "pin", pin)
        for ref, pin in sorted(no_connects)
    ]
    lines.append(_sexp("no_connects", *nc_lines))

    return "\n".join(lines) + "\n"
