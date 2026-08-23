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
against real KiCad.  No timestamps appear anywhere in the payload (§C6).

Pin *numbers* come from two sources, chosen per part:

* a **pin map** (``gatepack.pinmap.PartPinMap``), when the part carries one —
  its numbers are used verbatim;
* otherwise the **positional fallback** (gate-1 signal pins, gate-2 signal
  pins, ..., VCC, GND), which is what this emitter always produced before a pin
  map existed.

A pin map is only ever *cited* or *placeholder*; the notice below is conditional
on that provenance, and is per-part, so a netlist mixing cited and placeholder
parts says which is which instead of making one global claim.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from gatepack import pins
from gatepack.netlist import CellNames, MappedCell, MappedNetlist
from gatepack.pack.packer import PackageGroup
from gatepack.pinmap import SIGNAL_GND, SIGNAL_NC, SIGNAL_VCC

PIN_NUMBER_NOTICE = (
    "PIN NUMBERS ARE POSITIONAL PLACEHOLDERS, NOT THE MANUFACTURER PINOUT: "
    "no footprint pin map was supplied for this part, so pins are numbered "
    "gate-1 signal pins, gate-2 signal pins, ..., VCC, GND. Do not fabricate a "
    "board from these numbers without applying real footprint pin data."
)

_PIN_MAP_PLACEHOLDER_NOTICE = (
    "PIN NUMBERS ARE PLACEHOLDERS, NOT THE MANUFACTURER PINOUT: the pin map for "
    "this part is marked placeholder (unverified) in the pin refs file, so it "
    "has no datasheet citation. Do not fabricate a board from these numbers "
    "until the pin map is verified."
)

_PIN_MAP_CITED_NOTICE = (
    "PIN NUMBERS come from a cited pin map (see the pin refs file for the "
    "datasheet citation)."
)

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


def _positional_pins(part) -> list[tuple[str, str]]:
    """The positional fallback: ``(pin_name, direction)`` in pin-number order.

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


def _pinmap_entries(part, pinmap) -> list[tuple[str, str, str]]:
    """``(pin_name, direction, pin_number)`` triples from a pin map.

    The pin map stores an unscoped ``signal`` plus a 1-based ``gate``; the name
    is re-scoped for multi-gate packages exactly as the positional fallback
    scopes it (``1A``, ``2A``).  Directions are the cell's, except VCC/GND
    (power) and NC (no-connect, emitted as a passive pin that attaches to no
    net).
    """
    signal = pins.cell_pin_directions(part)
    multi = part.gates_per_pkg > 1
    out: list[tuple[str, str, str]] = []
    for row in pinmap.ordered_pins:
        if row.gate is not None:
            name = f"{row.gate}{row.signal}" if multi else row.signal
        else:
            name = row.signal
        if row.signal in (SIGNAL_VCC, SIGNAL_GND):
            direction = "power_in"
        elif row.signal == SIGNAL_NC:
            direction = "passive"
        else:
            direction = signal[row.signal]
        out.append((name, direction, str(row.pin)))
    return out


def _package_pin_entries(part, pinmap=None) -> list[tuple[str, str, str]]:
    """Ordered ``(pin_name, direction, pin_number)`` triples for a package.

    With a pin map the names and numbers come from the map; without one, pins
    are numbered positionally (the pre-pin-map behaviour, preserved
    byte-for-byte).
    """
    if pinmap is None:
        return [
            (name, direction, str(i + 1))
            for i, (name, direction) in enumerate(_positional_pins(part))
        ]
    return _pinmap_entries(part, pinmap)


def _pin_number_notice(part) -> str:
    """The per-part pin-number provenance notice.

    Three states, only one of which softens the warning: no pin map (positional
    placeholder, loud), a placeholder pin map (loud, names the map as the
    source), and a cited pin map (positive, no "do not fabricate").
    """
    pn = part.part_number or part.cell
    pinmap = getattr(part, "pinmap", None)
    if pinmap is None:
        return f"{pn}: {PIN_NUMBER_NOTICE}"
    if not pinmap.is_verified:
        return f"{pn}: {_PIN_MAP_PLACEHOLDER_NOTICE}"
    return f"{pn}: {_PIN_MAP_CITED_NOTICE}"


def _pin_notices(assigned: Sequence[tuple[str, PackageGroup]]) -> list[str]:
    """One notice per distinct part, in first-appearance order."""
    seen: dict[str, str] = {}
    notices: list[str] = []
    for _ref, group in assigned:
        pn = group.part.part_number or group.part.cell
        if pn in seen:
            continue
        seen[pn] = pn
        notices.append(_pin_number_notice(group.part))
    return notices


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
        entries = _package_pin_entries(part, getattr(part, "pinmap", None))
        number = {name: num for name, _, num in entries}
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
            for name, direction, num in _package_pin_entries(
                part, getattr(part, "pinmap", None)
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
            # Say in the artefact, per part, what was previously said only once
            # and only in this file's docstring: these pin *numbers* may be
            # positional placeholders or placeholder pin-map values.  The
            # notice is conditional on provenance and per-part, so a netlist
            # mixing cited and placeholder parts names each part and its
            # status — a single global claim over a mixed netlist is exactly
            # the unmarked assumption this project refuses to emit.
            *[
                _sexp("comment", "number", str(i + 1), "value", notice)
                for i, notice in enumerate(_pin_notices(assigned))
            ],
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
