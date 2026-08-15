"""Tests for provenance capture (§15.1): parsing ``write_json`` + ``src`` recovery.

The parser operates on synthetic Yosys JSON (Yosys is not installed here), so
these tests double as the specification of the JSON shape the parser assumes.
"""

from __future__ import annotations

import json

from gatepack.provenance.capture import (
    Netlist,
    SourceRef,
    capture_net_sources,
    capture_sources,
    parse_netlist_json,
    read_netlist_json,
)

from tests.unit.helpers import netlist_json


def test_source_ref_parse_full():
    ref = SourceRef.parse("design.yaml:42:transitions[2]")
    assert ref.filename == "design.yaml"
    assert ref.line == 42
    assert ref.path == "transitions[2]"
    assert ref.raw == "design.yaml:42:transitions[2]"


def test_source_ref_parse_unknown_line():
    ref = SourceRef.parse("design.yaml:?:transitions[2]")
    assert ref.line is None
    assert ref.path == "transitions[2]"


def test_source_ref_parse_no_colon():
    ref = SourceRef.parse("design.yaml")
    assert ref.filename == "design.yaml"
    assert ref.line is None
    assert ref.path == ""


def test_parse_minimal_netlist():
    data = netlist_json(
        inputs=("a", "b"),
        outputs=("y",),
        cells=(
            {
                "name": "g1",
                "type": "$_AND_",
                "connections": {"A": "a", "B": "b", "Y": "y"},
                "gp_src": "design.yaml:5:expressions.f",
            },
        ),
    )
    net = parse_netlist_json(data)
    assert isinstance(net, Netlist)
    assert net.module == "top"
    assert net.inputs == ("a", "b")
    assert net.outputs == ("y",)
    assert set(net.cells) == {"g1"}
    cell = net.cells["g1"]
    assert cell.type == "$_AND_"
    assert cell.connections["A"].net == "a"
    assert cell.connections["B"].net == "b"
    assert cell.connections["Y"].net == "y"
    assert cell.source is not None
    assert cell.source.path == "expressions.f"


def test_parse_constants():
    data = netlist_json(
        inputs=("a",),
        outputs=("y",),
        cells=(
            {
                "name": "g1",
                "type": "$_AND_",
                "connections": {"A": "a", "B": "1", "Y": "y"},
            },
        ),
    )
    net = parse_netlist_json(data)
    pin = net.cells["g1"].connections["B"]
    assert pin.net == ""
    assert pin.constant is True
    assert pin.is_constant


def test_parse_unknown_constant():
    data = netlist_json(
        inputs=("a",),
        outputs=("y",),
        cells=(
            {
                "name": "g1",
                "type": "$_AND_",
                "connections": {"A": "a", "B": "x", "Y": "y"},
            },
        ),
    )
    net = parse_netlist_json(data)
    pin = net.cells["g1"].connections["B"]
    assert pin.net == ""
    assert pin.constant is None
    assert pin.is_unknown


def test_parse_chooses_largest_module():
    data = netlist_json(
        inputs=("a",),
        outputs=("y",),
        cells=(
            {"name": "g", "type": "$_NOT_", "connections": {"A": "a", "Y": "y"}},
        ),
    )
    data["modules"]["empty"] = {"attributes": {}, "ports": {}, "cells": {}, "netnames": {}}
    data["modules"]["big"] = data["modules"]["top"]
    del data["modules"]["top"]
    net = parse_netlist_json(data)
    assert net.module == "big"


def test_parse_explicit_module():
    data = netlist_json(inputs=("a",), outputs=("y",), cells=())
    data["modules"]["other"] = {"attributes": {}, "ports": {}, "cells": {}, "netnames": {}}
    net = parse_netlist_json(data, module="other")
    assert net.module == "other"


def test_capture_sources():
    data = netlist_json(
        inputs=("a", "b"),
        outputs=("y",),
        cells=(
            {
                "name": "g1",
                "type": "$_AND_",
                "connections": {"A": "a", "B": "b", "Y": "y"},
                "gp_src": "d.yaml:5:expressions.f",
            },
            {
                "name": "g2",
                "type": "$_OR_",
                "connections": {"A": "a", "B": "b", "Y": "z"},
            },
        ),
    )
    net = parse_netlist_json(data)
    sources = capture_sources(net)
    assert set(sources) == {"g1"}
    assert sources["g1"].line == 5


def test_capture_net_sources_from_netnames():
    # gp_src on a wire declaration lands in the netnames entry, not on a cell.
    data = netlist_json(
        inputs=("a", "b"),
        outputs=("y",),
        cells=(
            {"name": "g1", "type": "$_AND_", "connections": {"A": "a", "B": "b", "Y": "y"}},
        ),
        net_sources={"y": "d.yaml:7:output_logic.y"},
    )
    net = parse_netlist_json(data)
    assert net.net_sources["y"].path == "output_logic.y"
    assert set(capture_net_sources(net)) == {"y"}
    # the attribute is on the net, so the *cell* carries none
    assert net.cells["g1"].source is None
    assert capture_sources(net) == {}


def test_read_netlist_json(tmp_path):
    data = netlist_json(inputs=("a",), outputs=("y",), cells=())
    path = tmp_path / "premap.json"
    path.write_text(json.dumps(data))
    net = read_netlist_json(path)
    assert net.inputs == ("a",)
    assert net.outputs == ("y",)
