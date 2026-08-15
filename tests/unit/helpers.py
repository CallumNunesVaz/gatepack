"""Shared helpers for front-end unit tests."""

from __future__ import annotations


def netlist_json(
    module: str = "top",
    inputs: tuple[str, ...] = (),
    outputs: tuple[str, ...] = (),
    cells: tuple[dict, ...] = (),
    net_sources: dict[str, str] | None = None,
) -> dict:
    """Build a Yosys ``write_json`` document for provenance unit tests.

    ``cells`` are dicts with keys ``name``, ``type``, ``connections``
    (port -> net name or the constant ``"0"``/``"1"``), optional ``gp_src``
    (a cell attribute, the sequential carrier) and optional
    ``port_directions``.  ``net_sources`` maps a net name to its ``gp_src``
    attribute value (the combinational carrier).  Missing port directions are
    derived from the type (``Q`` for sequential-looking types, ``Y``
    otherwise).
    """
    bit_of: dict[str, int] = {}
    netnames: dict[str, dict] = {}

    def get_bit(net: str) -> int:
        if net not in bit_of:
            idx = len(bit_of)
            bit_of[net] = idx
            netnames[net] = {"hide_name": 0, "bits": [idx], "attributes": {}}
        return bit_of[net]

    for net in inputs:
        get_bit(net)
    for net in outputs:
        get_bit(net)
    for net in (net_sources or {}):
        get_bit(net)
    for net, value in (net_sources or {}).items():
        netnames[net]["attributes"] = {"gp_src": value}

    ports: dict[str, dict] = {}
    for net in inputs:
        ports[net] = {"direction": "input", "bits": [get_bit(net)]}
    for net in outputs:
        ports[net] = {"direction": "output", "bits": [get_bit(net)]}

    cells_json: dict[str, dict] = {}
    for spec in cells:
        name = spec["name"]
        type_ = spec["type"]
        connections = spec["connections"]
        resolved: dict[str, list] = {}
        for port, ref in connections.items():
            if isinstance(ref, str) and ref in ("0", "1", "x", "z"):
                resolved[port] = [ref]
            else:
                resolved[port] = [get_bit(ref)]
        directions = spec.get("port_directions") or _default_dirs(type_, connections)
        cells_json[name] = {
            "hide_name": 0,
            "type": type_,
            "parameters": {},
            "attributes": {"gp_src": spec["gp_src"]} if spec.get("gp_src") else {},
            "port_directions": directions,
            "connections": resolved,
        }

    return {
        "creator": "Yosys 0.40 (test)",
        "modules": {
            module: {
                "attributes": {},
                "ports": ports,
                "cells": cells_json,
                "netnames": netnames,
            }
        },
    }


def _default_dirs(type_: str, connections: dict[str, str]) -> dict[str, str]:
    output = "Q" if ("DFF" in type_ or "DLATCH" in type_ or "SR" in type_) else "Y"
    return {port: ("output" if port == output else "input") for port in connections}


def sync_design(**overrides) -> str:
    """A minimal, valid synchronous design (explicit self-loops, one input ``x``)."""
    name = overrides.pop("name", "min")
    states = overrides.pop("states", ["A", "B"])
    initial = overrides.pop("initial", "A")
    transitions = overrides.pop(
        "transitions",
        [
            ("A", "B", "x"),
            ("A", "A", "!x"),
            ("B", "A", "!x"),
            ("B", "B", "x"),
        ],
    )
    outputs = overrides.pop("outputs", [])
    output_logic = overrides.pop("output_logic", {})
    expressions = overrides.pop("expressions", {})

    lines = [
        f"name: {name}",
        "timing_model: synchronous",
        "clock: {signal: clk, freq_hz: 1000, source: OSC}",
        "reset: {signal: rst_n, active: low, source: SUPERVISOR}",
        "encoding: one_hot",
        "inputs:",
        "  - {name: x, sync: false}",
    ]
    if expressions:
        lines.append("expressions:")
        for k, v in expressions.items():
            lines.append(f'  {k}: "{v}"')
    lines.append(f"states: {states}")
    lines.append(f"initial: {initial}")
    lines.append("transitions:")
    for src, dst, when in transitions:
        lines.append(f'  - {{from: {src}, to: {dst}, when: "{when}"}}')
    if outputs:
        lines.append("outputs:")
        for o in outputs:
            lines.append(f"  - {{name: {o}}}")
    if output_logic:
        lines.append("output_logic:")
        for k, v in output_logic.items():
            lines.append(f'  {k}: "{v}"')
    for k, v in overrides.items():
        lines.append(f"{k}: {v}")
    return "\n".join(lines) + "\n"
