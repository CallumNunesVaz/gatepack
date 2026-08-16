"""Contract tests for ``gatepack packed-netlist`` (§C12, app/shared/api.ts).

``packed-netlist <dir> --json`` must emit the standard ``ok``/``schema``
envelope whose ``data`` is the ``PackedView``.  The payload is *package
boundaries only* — it is produced once by ``gatepack build`` (which writes
``out/packed.json``) and handed through unchanged, so the renderer never holds
two representations of one circuit.

The critical name-space contract is pinned here: ``cells`` are STABLE cone-hash
names (what ``packing.force_groups`` records) while ``instanceCells`` are the
mapped-netlist INSTANCE names (what the rendered SVG is keyed by).  A stable
name appearing in ``instanceCells`` is the defect these tests exist to catch.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LIBRARY_CSV = REPO / "libraries" / "74aup.csv"

# Instance names deliberately shaped like ABC's renumbered output so a stable
# name written into `instanceCells` cannot accidentally match them.
MAPPED = (
    '{"modules": {"t": {'
    '"ports": {"a": {"direction": "input", "bits": [2]},'
    '          "b": {"direction": "input", "bits": [3]},'
    '          "y": {"direction": "output", "bits": [6]}},'
    '"cells": {'
    '"$abc$1$inst$100": {"type": "NOR2", "port_directions": {"A": "input", "B": "input", "Y": "output"},'
    '"connections": {"A": [2], "B": [3], "Y": [4]}},'
    '"$abc$1$inst$101": {"type": "INV", "port_directions": {"A": "input", "Y": "output"},'
    '"connections": {"A": [4], "Y": [6]}}'
    "},"
    '"netnames": {"a": {"bits": [2]}, "b": {"bits": [3]}, '
    '"n1": {"bits": [4]}, "y": {"bits": [6]}}'
    "}}}"
)

DESIGN = (
    "name: t\n"
    "timing_model: synchronous\n"
    "clock: {signal: clk, freq_hz: 1, source: OSC}\n"
    "reset: {signal: rst_n, active: low, source: SUPERVISOR}\n"
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


def _run(*argv: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "gatepack.cli", *argv],
        cwd=str(cwd or REPO),
        capture_output=True,
        text=True,
    )


def _envelope(proc: subprocess.CompletedProcess) -> dict:
    assert proc.stdout.strip(), f"empty stdout; stderr={proc.stderr}"
    return json.loads(proc.stdout)


def _build(tmp_path: Path) -> Path:
    design = tmp_path / "d.yaml"
    design.write_text(DESIGN)
    mapped = tmp_path / "mapped.json"
    mapped.write_text(MAPPED)
    out = tmp_path / "out"
    proc = _run(
        "build", str(design), "--library", str(LIBRARY_CSV),
        "--out", str(out), "--mapped", str(mapped), "--json",
    )
    assert proc.returncode == 0, proc.stderr
    return out


def test_packed_netlist_json_envelope(tmp_path):
    out = _build(tmp_path)
    proc = _run("packed-netlist", str(out), "--json")
    assert proc.returncode == 0, proc.stderr
    env = _envelope(proc)
    assert env["ok"] is True
    assert env["command"] == "packed-netlist"
    assert env["schema"] == 1
    assert env["warnings"] == []
    data = env["data"]
    assert set(data) == {"packages"}
    assert len(data["packages"]) == 2
    for pkg in data["packages"]:
        assert set(pkg) == {
            "refdes", "partNumber", "cells", "instanceCells",
            "capacity", "spare", "rationale",
        }
        assert isinstance(pkg["capacity"], int)
        assert isinstance(pkg["spare"], int)
        assert pkg["spare"] >= 0
        assert pkg["capacity"] == len(pkg["cells"]) + pkg["spare"]
        assert len(pkg["cells"]) == len(pkg["instanceCells"])


def test_packed_netlist_instance_cells_index_mapped_netlist(tmp_path):
    out = _build(tmp_path)
    proc = _run("packed-netlist", str(out), "--json")
    assert proc.returncode == 0, proc.stderr
    packages = _envelope(proc)["data"]["packages"]

    mapped = json.loads((tmp_path / "mapped.json").read_text())
    instance_names = set(mapped["modules"]["t"]["cells"])

    for pkg in packages:
        # `instanceCells` are the ABC instance names the SVG is keyed by, so
        # every one must appear in the mapped netlist's cell table.
        assert set(pkg["instanceCells"]) <= instance_names, pkg
        # and the STABLE names (force_groups) must NOT leak into instanceCells —
        # a stable name is not an instance name, so it never appears in the
        # mapped netlist's cell table (this is the four-defect boundary).
        for stable in pkg["cells"]:
            assert stable not in instance_names, pkg
            assert "__" in stable, pkg


def test_packed_netlist_no_build_is_error_not_faked(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    proc = _run("packed-netlist", str(empty), "--json")
    assert proc.returncode == 1
    env = _envelope(proc)
    assert env["ok"] is False
    assert env["command"] == "packed-netlist"
    assert env["error"]["severity"] == "error"
    assert "packed view" in env["error"]["message"]
    # never a fabricated empty package list
    assert "data" not in env
    assert "error:" in proc.stderr


def test_packed_netlist_stdout_is_exactly_one_object(tmp_path):
    out = _build(tmp_path)
    proc = _run("packed-netlist", str(out), "--json")
    stripped = proc.stdout.strip()
    assert stripped.count("\n") == 0
    json.loads(stripped)


def test_packed_netlist_human_output(tmp_path):
    out = _build(tmp_path)
    proc = _run("packed-netlist", str(out))
    assert proc.returncode == 0
    assert "2 package(s)" in proc.stdout
