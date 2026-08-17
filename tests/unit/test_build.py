"""Tests for the build orchestration (gatepack.build)."""

from __future__ import annotations

import json

import pytest

from gatepack.build import AssembleConfig, assemble, run_build

from .cells import cell, netlist, part

_MAPPED = (
    '{"modules": {"demo": {'
    '"ports": {"a": {"direction": "input", "bits": [2]}, '
    '"b": {"direction": "input", "bits": [3]}, '
    '"y": {"direction": "output", "bits": [6]}},'
    '"cells": {'
    '"$1": {"type": "NOR2", "port_directions": {"A": "input", "B": "input", "Y": "output"},'
    '"connections": {"A": [2], "B": [3], "Y": [4]}},'
    '"$2": {"type": "INV", "port_directions": {"A": "input", "Y": "output"},'
    '"connections": {"A": [4], "Y": [6]}}'
    "},"
    '"netnames": {"a": {"bits": [2]}, "b": {"bits": [3]}, '
    '"n1": {"bits": [4]}, "y": {"bits": [6]}}'
    "}}}"
)


def _parts():
    return [
        part("NOR2", function="!(A|B)", inputs=2),
        part("INV", function="!A", inputs=1),
    ]


def test_assemble_end_to_end():
    from gatepack.netlist import parse_mapped_json

    nl = parse_mapped_json(_MAPPED)
    result = assemble(nl, _parts(), AssembleConfig(design_name="demo"))
    assert result.bom.startswith("part_number,")
    assert result.netlist_text.startswith("(export")
    assert result.report.startswith("# demo — build report")
    assert set(result.refdes.values()) == {"U1", "U2"}
    assert result.packed_stats.package_count == 2
    assert result.timing.combinational_depth == 2


def test_assemble_deterministic():
    from gatepack.netlist import parse_mapped_json

    nl = parse_mapped_json(_MAPPED)
    r1 = assemble(nl, _parts(), AssembleConfig(design_name="demo"))
    r2 = assemble(nl, _parts(), AssembleConfig(design_name="demo"))
    assert r1.bom == r2.bom
    assert r1.netlist_text == r2.netlist_text
    assert r1.report == r2.report
    assert r1.refdes == r2.refdes


def test_refdes_delta_persists(tmp_path):
    from gatepack.netlist import parse_mapped_json

    nl = parse_mapped_json(_MAPPED)
    cfg = AssembleConfig(design_name="demo")
    r1 = assemble(nl, _parts(), cfg, previous_refdes={})
    # second build with the previous map: nothing changed
    r2 = assemble(nl, _parts(), cfg, previous_refdes=r1.refdes)
    assert r2.refdes_delta.unchanged == 2
    assert r2.refdes_delta.renumbered == ()


def test_run_build_with_mapped_json(tmp_path):
    design = tmp_path / "d.yaml"
    design.write_text(
        "name: demo\n"
        "timing_model: synchronous\n"
        "clock: {signal: clk, freq_hz: 1000, source: OSC}\n"
        "reset: {signal: rst_n, active: low}\n"
        "inputs:\n  - {name: a, sync: false}\n  - {name: b, sync: false}\n"
        "outputs:\n  - {name: y}\n"
        "states: [S0, S1]\n"
        "initial: S0\n"
        "transitions:\n"
        '  - {from: S0, to: S1, when: "a"}\n'
        '  - {from: S0, to: S0, when: "!a"}\n'
        '  - {from: S1, to: S0, when: "1"}\n'
        "output_logic: {y: \"a | b\"}\n"
    )
    library = tmp_path / "parts.csv"
    library.write_text(
        "cell,tier,family,part_suffix,equivalents,function,inputs,gates_per_pkg,"
        "package,mfrs,vcc_min,vcc_max,area,tpd_ns,iq_ua\n"
        'NOR2,G,AUP,1G02,,!(A|B),2,1,SOT-353,"TI;Nexperia",0.8,3.6,1.0,5.1,0.9\n'
        'INV,G,AUP,1G04,,!A,1,1,SOT-353,"TI;Nexperia",0.8,3.6,1.0,4.6,0.9\n'
        'DFF,F,AUP,1G79,,,2,1,SOT-353,"TI;Nexperia",0.8,3.6,1.0,7.2,0.9\n'
    )
    mapped = tmp_path / "mapped.json"
    mapped.write_text(_MAPPED)

    out = tmp_path / "out"
    result, paths = run_build(design, library, out_dir=out, mapped_json=mapped)
    assert (out / "bom.csv").exists()
    assert (out / "netlist.net").exists()
    assert (out / "report.md").exists()
    assert (out / "refdes.json").exists()
    data = json.loads((out / "refdes.json").read_text())
    assert list(data.keys()) == sorted(data.keys())


_TWO_INV_MAPPED = (
    '{"modules": {"demo": {'
    '"ports": {"a": {"direction": "input", "bits": [2]}},'
    '"cells": {'
    '"$1": {"type": "INV", "port_directions": {"A": "input", "Y": "output"},'
    '"connections": {"A": [2], "Y": [4]}},'
    '"$2": {"type": "INV", "port_directions": {"A": "input", "Y": "output"},'
    '"connections": {"A": [4], "Y": [6]}}'
    "},"
    '"netnames": {"a": {"bits": [2]}, "n1": {"bits": [4]}, "n2": {"bits": [6]}}'
    "}}}"
)


def _simple_design(tmp_path) -> Path:
    design = tmp_path / "d.yaml"
    design.write_text(
        "name: demo\n"
        "timing_model: synchronous\n"
        "clock: {signal: clk, freq_hz: 1000, source: OSC}\n"
        "reset: {signal: rst_n, active: low}\n"
        "inputs:\n  - {name: a, sync: false}\n"
        "states: [S0]\n"
        "initial: S0\n"
        "transitions:\n"
        '  - {from: S0, to: S0, when: "1"}\n'
        "output_logic: {}\n"
    )
    return design


def _multi_gate_library(tmp_path) -> Path:
    library = tmp_path / "parts.csv"
    library.write_text(
        "cell,tier,family,part_suffix,equivalents,function,inputs,gates_per_pkg,"
        "package,mfrs,vcc_min,vcc_max,area,tpd_ns,iq_ua\n"
        'INV,G,AUP,1G04,,!A,1,1,SOT-353,"TI;Nexperia",0.8,3.6,1.0,4.6,0.9\n'
        'INV,G,AUP,2G04,,!A,1,2,SOT-363,"TI;Nexperia",0.8,3.6,1.4,4.6,0.9\n'
    )
    return library


def test_run_build_refuses_unverified_multi_gate_parts(tmp_path):
    design = _simple_design(tmp_path)
    library = _multi_gate_library(tmp_path)
    mapped = tmp_path / "mapped.json"
    mapped.write_text(_TWO_INV_MAPPED)

    from gatepack.parts import UnverifiedGatesPerPackageError

    with pytest.raises(UnverifiedGatesPerPackageError, match="gates_per_pkg"):
        run_build(design, library, out_dir=tmp_path / "out", mapped_json=mapped)


def test_run_build_acknowledges_unverified_multi_gate_parts(tmp_path):
    design = _simple_design(tmp_path)
    library = _multi_gate_library(tmp_path)
    mapped = tmp_path / "mapped.json"
    mapped.write_text(_TWO_INV_MAPPED)

    result, paths = run_build(
        design, library, out_dir=tmp_path / "out",
        mapped_json=mapped, allow_unverified_gates_per_pkg=True,
    )
    assert (tmp_path / "out" / "bom.csv").exists()
    # the two INVs share a die in a 2-gate package
    assert result.packed_stats.package_count == 1


def test_run_build_accepts_packaging_verified_multi_gate_parts(tmp_path):
    # A packaging citation for the dual inverter clears the gate on its own; no
    # acknowledgement flag is needed.  If the gate is (re)wired to the electrical
    # status, this fails: the part's electrical figures stay placeholder here.
    design = _simple_design(tmp_path)
    library = _multi_gate_library(tmp_path)
    (tmp_path / "parts.refs.md").write_text(
        "| cell | datasheet | revision | table/page | electrical status |\n"
        "|------|-----------|----------|------------|-------------------|\n"
        "| INV | TBD | TBD | TBD | placeholder — unverified |\n"
        "\n"
        "## Packaging citations\n"
        "| part_number | datasheet | revision | table/page | packaging status |\n"
        "|-------------|-----------|----------|------------|------------------|\n"
        "| 74AUP2G04 | Nexperia 74AUP2G04 data sheet | 2023-07-19 | Table 3 | verified |\n"
    )
    mapped = tmp_path / "mapped.json"
    mapped.write_text(_TWO_INV_MAPPED)

    result, paths = run_build(
        design, library, out_dir=tmp_path / "out", mapped_json=mapped,
    )
    assert (tmp_path / "out" / "bom.csv").exists()
    assert result.packed_stats.package_count == 1
    # the BOM still flags the part's *electrical* figures as unverified — the
    # packaging citation must not leak into the electrical status.
    import csv as _csv
    import io as _io

    rows = list(_csv.DictReader(_io.StringIO(result.bom)))
    dual = next(r for r in rows if r["part_number"] == "74AUP2G04")
    assert dual["unverified"] == "yes"
