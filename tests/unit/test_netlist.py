"""Tests for the mapped-netlist model (gatepack.netlist)."""

from __future__ import annotations

from gatepack.netlist import (
    MappedCell,
    MappedNetlist,
    parse_mapped_json,
    resolve_parts,
    stable_cell_names,
)
from gatepack.parts import Part

from .cells import cell, netlist, part


def _inv() -> Part:
    return part("INV", function="!A", inputs=1)


def test_parse_mapped_json_basic():
    text = (
        '{"modules": {"top": {'
        '"ports": {"a": {"direction": "input", "bits": [2]}, '
        '"y": {"direction": "output", "bits": [5]}},'
        '"cells": {"$1": {'
        '"type": "INV", "port_directions": {"A": "input", "Y": "output"},'
        '"connections": {"A": [2], "Y": [5]}}},'
        '"netnames": {"a": {"bits": [2]}, "y": {"bits": [5]}}'
        "}}}"
    )
    nl = parse_mapped_json(text)
    assert nl.top == "top"
    assert nl.inputs == ("a",)
    assert nl.outputs == ("y",)
    assert len(nl.cells) == 1
    c = nl.cells[0]
    assert c.cell == "INV"
    assert c.connections == {"A": "a", "Y": "y"}


def test_parse_mapped_json_constant_connection():
    text = (
        '{"modules": {"top": {'
        '"ports": {},'
        '"cells": {"$1": {'
        '"type": "NAND2", "port_directions": {"A": "input", "B": "input", "Y": "output"},'
        '"connections": {"A": ["1"], "B": [3], "Y": [4]}}},'
        '"netnames": {"n3": {"bits": [3]}, "n4": {"bits": [4]}}'
        "}}}"
    )
    nl = parse_mapped_json(text)
    c = nl.cells[0]
    assert c.connections["A"] == "1"
    assert c.connections["B"] == "n3"


def test_resolve_parts_attaches_tier_and_directions():
    inv = _inv()
    raw = MappedCell(name="g0", cell="INV", tier="", connections={"A": "a", "Y": "n1"})
    nl = resolve_parts(MappedNetlist(top="top", cells=(raw,)), [inv])
    assert nl.cells[0].part is inv
    assert nl.cells[0].tier == "G"
    assert nl.cells[0].directions == {"A": "input", "Y": "output"}


def test_stable_cell_names_deterministic():
    inv = _inv()
    c1 = cell("$abc1", inv, {"A": "a", "Y": "n1"})
    c2 = cell("$abc2", inv, {"A": "n1", "Y": "y"})
    nl = netlist("top", [c1, c2], inputs=("a",), outputs=("y",))
    n1 = stable_cell_names(nl)
    n2 = stable_cell_names(nl)
    assert n1 == n2


def test_stable_cell_names_identical_cells_disambiguated():
    inv = _inv()
    c1 = cell("$abc1", inv, {"A": "a", "Y": "y1"})
    c2 = cell("$abc2", inv, {"A": "a", "Y": "y2"})
    nl = netlist("top", [c1, c2], inputs=("a",), outputs=("y1", "y2"))
    names = stable_cell_names(nl)
    assert len(set(names.values())) == 2
    assert names["$abc1"] != names["$abc2"]


def test_stable_cell_names_cone_sensitive():
    inv = _inv()
    nand = part("NAND2", function="!(A&B)", inputs=2)
    # same cell type, different cones -> different signatures
    c1 = cell("$1", nand, {"A": "a", "B": "b", "Y": "n1"})
    c2 = cell("$2", nand, {"A": "a", "B": "c", "Y": "n2"})
    nl = netlist("top", [c1, c2], inputs=("a", "b", "c"), outputs=("n1", "n2"))
    names = stable_cell_names(nl)
    assert names["$1"] != names["$2"]
    assert names["$1"].startswith("NAND2__")
