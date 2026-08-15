"""Tests for ``gatepack simulate`` — the C11 divergence table.

Pinned here:

* the ``expected`` column comes from the *spec* (so it matches the C4
  exhaustive check), and the ``actual`` column comes from the mapped netlist —
  so a deliberately-wrong netlist makes ``diverges`` true (the check can fail);
* ``actual`` is omitted (not fabricated) when synthesis has not run;
* the row cap sets ``exhaustive: false`` rather than truncating silently;
* sequential rows carry a ``state`` and are enumerated exhaustively.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from gatepack.frontend import compile_design_file
from gatepack.netlist import MappedCell, MappedNetlist
from gatepack.parts import load_parts
from gatepack.simulate import SimulateConfig, build_simulation_table, evaluate_mapped_netlist

DESIGNS = Path(__file__).resolve().parents[1] / "golden" / "designs"
LIBRARY_CSV = Path(__file__).resolve().parents[2] / "libraries" / "74aup.csv"


def _compiled(name: str):
    return compile_design_file(DESIGNS / name).compiled


def _parts():
    return load_parts(LIBRARY_CSV)


def _and2_netlist() -> MappedNetlist:
    """A mapped netlist computing ``y = a & b`` (deliberately wrong for ``y = a ^ b``)."""
    cell = MappedCell(
        name="$and",
        cell="AND2",
        tier="G",
        connections={"A": "a", "B": "b", "Y": "y"},
        directions={"A": "input", "B": "input", "Y": "output"},
    )
    return MappedNetlist(top="xor2", cells=(cell,), inputs=("a", "b"), outputs=("y",))


# --- expected-only (no netlist) ----------------------------------------------


def test_expected_table_has_no_actual_column_without_netlist():
    table = build_simulation_table(_compiled("xor2.yaml"), None)
    assert table["inputNames"] == ["a", "b"]
    assert table["outputNames"] == ["y"]
    assert table["exhaustive"] is True
    assert table["dontCareCount"] == 0
    assert table["unreachableCount"] == 0
    assert len(table["rows"]) == 4
    for row in table["rows"]:
        assert "actual" not in row
        assert row["diverges"] is False
    # expected == spec (a ^ b)
    by_inputs = {tuple(sorted(row["inputs"].items())): row for row in table["rows"]}
    assert by_inputs[(("a", "0"), ("b", "0"))]["expected"]["y"] == "0"
    assert by_inputs[(("a", "0"), ("b", "1"))]["expected"]["y"] == "1"
    assert by_inputs[(("a", "1"), ("b", "0"))]["expected"]["y"] == "1"
    assert by_inputs[(("a", "1"), ("b", "1"))]["expected"]["y"] == "0"


# --- deliberately divergent ---------------------------------------------------


def test_divergent_netlist_flags_diverges_true():
    table = build_simulation_table(_compiled("xor2.yaml"), _and2_netlist(), _parts())
    divergent = [row for row in table["rows"] if row["diverges"]]
    # y = a & b disagrees with y = a ^ b on exactly (0,1), (1,0) and (1,1).
    assert len(divergent) == 3
    for row in divergent:
        assert "actual" in row
    # the agreeing row is (0,0)
    agreeing = [row for row in table["rows"] if not row["diverges"]]
    assert len(agreeing) == 1
    assert agreeing[0]["inputs"] == {"a": "0", "b": "0"}
    assert agreeing[0]["actual"] == {"y": "0"}


def test_matching_netlist_never_diverges():
    """A netlist that matches the spec must produce zero divergent rows (and
    this is what keeps the column from being a tautology)."""
    cell = MappedCell(
        name="$xor",
        cell="XOR2",
        tier="G",
        connections={"A": "a", "B": "b", "Y": "y"},
        directions={"A": "input", "B": "input", "Y": "output"},
    )
    netlist = MappedNetlist(top="xor2", cells=(cell,), inputs=("a", "b"), outputs=("y",))
    table = build_simulation_table(_compiled("xor2.yaml"), netlist, _parts())
    assert all(not row["diverges"] for row in table["rows"])


# --- netlist evaluation -------------------------------------------------------


def test_evaluate_mapped_netlist_combines_gcell_and_unknown():
    parts = _parts()
    and_fn = next(p for p in parts if p.cell == "AND2")
    # an AND2 cell feeding an unclocked flop: the flop's Q is unknown.
    and_cell = MappedCell(
        name="$and",
        cell="AND2",
        tier="G",
        connections={"A": "a", "B": "b", "Y": "n"},
        directions={"A": "input", "B": "input", "Y": "output"},
    )
    dff = MappedCell(
        name="$dff",
        cell="DFF_R",
        tier="F",
        connections={"D": "n", "Q": "q", "CK": "1", "RST_N": "1"},
        directions={"D": "input", "Q": "output", "CK": "input", "RST_N": "input"},
    )
    netlist = MappedNetlist(top="t", cells=(and_cell, dff), inputs=("a", "b"), outputs=("q",))
    from gatepack.simulate import _functions

    out = evaluate_mapped_netlist(netlist, _functions(parts), {"a": True, "b": True})
    assert out["q"] is None  # state-held, never clocked


# --- sequential ---------------------------------------------------------------


def test_sequential_table_enumerates_state_times_input():
    table = build_simulation_table(_compiled("traffic_light.yaml"), None)
    # 3 states x 2 inputs = 12 rows.
    assert len(table["rows"]) == 12
    assert table["exhaustive"] is True
    states = {row["state"] for row in table["rows"]}
    assert states == {"RED", "GREEN", "AMBER"}
    # Moore outputs track the row's state, not the transition target.
    red_rows = [r for r in table["rows"] if r["state"] == "RED"]
    assert all(r["expected"]["red"] == "1" for r in red_rows)
    assert all(r["expected"]["green"] == "0" for r in red_rows)


# --- cap ----------------------------------------------------------------------


def test_cap_sets_exhaustive_false_and_truncates():
    compiled = _compiled("traffic_light.yaml")
    table = build_simulation_table(
        compiled, None, config=SimulateConfig(max_rows=3)
    )
    assert table["exhaustive"] is False
    assert len(table["rows"]) == 3


def test_exhaustive_true_when_under_cap():
    compiled = _compiled("xor2.yaml")
    table = build_simulation_table(
        compiled, None, config=SimulateConfig(max_rows=4)
    )
    assert table["exhaustive"] is True
    assert len(table["rows"]) == 4


# --- CLI ----------------------------------------------------------------------


def _run_cli(*argv: str) -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", "gatepack.cli", *argv],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[2],
    )
    return json.loads(proc.stdout)


def test_cli_simulate_json_envelope():
    env = _run_cli(
        "simulate",
        str(DESIGNS / "xor2.yaml"),
        "--json",
    )
    assert env["ok"] is True
    assert env["command"] == "simulate"
    assert env["schema"] == 1
    data = env["data"]
    assert data["inputNames"] == ["a", "b"]
    assert len(data["rows"]) == 4


def test_cli_simulate_divergent_with_mapped(tmp_path):
    mapped_path = tmp_path / "mapped.json"
    mapped_path.write_text(json.dumps({
        "modules": {
            "xor2": {
                "ports": {
                    "a": {"direction": "input", "bits": [0]},
                    "b": {"direction": "input", "bits": [1]},
                    "y": {"direction": "output", "bits": [2]},
                },
                "netnames": {
                    "a": {"bits": [0]},
                    "b": {"bits": [1]},
                    "y": {"bits": [2]},
                },
                "cells": {
                    "$and": {
                        "hide_name": 1,
                        "type": "AND2",
                        "port_directions": {"A": "input", "B": "input", "Y": "output"},
                        "connections": {"A": [0], "B": [1], "Y": [2]},
                    },
                },
            },
        },
    }))
    env = _run_cli(
        "simulate",
        str(DESIGNS / "xor2.yaml"),
        "--library", str(LIBRARY_CSV),
        "--mapped", str(mapped_path),
        "--json",
    )
    assert env["ok"] is True
    rows = env["data"]["rows"]
    assert sum(1 for r in rows if r["diverges"]) == 3
