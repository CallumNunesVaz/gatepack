"""Contract tests for the ``--json`` machine-output envelope (app/shared/api.ts).

The ``--json`` flag makes ``compile``/``estimate``/``verify``/``build`` print
exactly one JSON object to stdout and nothing else.  These tests parse that
object and pin the envelope shape field-for-field, including a failing case
(``ok: false``).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LIBRARY_CSV = REPO / "libraries" / "74aup.csv"


def _run(*argv: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "gatepack.cli", *argv],
        cwd=str(cwd or REPO),
        capture_output=True,
        text=True,
    )


def _design(tmp_path: Path, *, with_property: bool = False) -> Path:
    text = (
        "name: t\n"
        "timing_model: synchronous\n"
        "clock: {signal: clk, freq_hz: 1, source: OSC}\n"
        "reset: {signal: rst_n, active: low, source: SUPERVISOR}\n"
        "inputs:\n  - {name: x, sync: false}\n"
        "states: [A, B]\n"
        "initial: A\n"
        "transitions:\n"
        '  - {from: A, to: B, when: "x"}\n'
        '  - {from: A, to: A, when: "!x"}\n'
        '  - {from: B, to: A, when: "1"}\n'
        "output_logic: {}\n"
    )
    if with_property:
        text += 'properties:\n  - {name: never_both, kind: mutex, expr: "1"}\n'
    path = tmp_path / "d.yaml"
    path.write_text(text)
    return path


def _envelope(proc: subprocess.CompletedProcess) -> dict:
    assert proc.stdout.strip(), f"empty stdout; stderr={proc.stderr}"
    return json.loads(proc.stdout)


def test_compile_json_envelope(tmp_path):
    design = _design(tmp_path)
    proc = _run("compile", str(design), "-o", str(tmp_path / "build"), "--json")
    assert proc.returncode == 0, proc.stderr
    env = _envelope(proc)
    assert env["ok"] is True
    assert env["command"] == "compile"
    assert env["schema"] == 1
    assert env["warnings"] == []
    data = env["data"]
    assert set(data) == {
        "verilogPath", "propertiesPath", "flopCount", "stateCount",
        "encoding", "johnsonSuggestion",
    }
    assert data["encoding"] == "one_hot"
    assert data["stateCount"] == 2
    assert data["flopCount"] >= 2
    assert data["verilogPath"].endswith("generated.v")
    assert data["propertiesPath"].endswith("properties.sv")


def test_estimate_json_envelope(tmp_path):
    design = _design(tmp_path)
    proc = _run(
        "estimate", str(design), "--library", str(LIBRARY_CSV),
        "--build", str(tmp_path / "b"), "--json",
    )
    assert proc.returncode == 0, proc.stderr
    data = _envelope(proc)["data"]
    assert set(data) == {
        "verdict", "reasons", "packageCount", "flopCount", "cellCounts",
        "alternative",
    }
    assert data["verdict"] == "green"
    assert data["alternative"] is None
    # Yosys is absent -> packageCount/cellCounts are honestly empty, never faked.
    assert data["packageCount"] is None
    assert data["cellCounts"] == {}


def test_verify_json_envelope_and_four_way_status(tmp_path):
    design = _design(tmp_path, with_property=True)
    proc = _run(
        "verify", str(design), "--library", str(LIBRARY_CSV),
        "--build", str(tmp_path / "b"), "--json",
    )
    assert proc.returncode == 1  # not-run is never a pass (§14)
    data = _envelope(proc)["data"]
    assert set(data) == {"checks", "allPassed"}
    assert data["allPassed"] is False
    checks = {c["name"]: c for c in data["checks"]}
    assert "equivalence" in checks
    for check in data["checks"]:
        assert check["kind"] in ("equivalence", "simulation", "mutation", "property", "hazard")
        assert check["status"] in ("passed", "bounded", "failed", "not_run")
        assert isinstance(check["durationMs"], int)
    # the property check is not_run with an explicit reason, never a pass
    prop = checks["property never_both"]
    assert prop["kind"] == "property"
    assert prop["status"] == "not_run"
    assert prop["skippedReason"] == "sby not found on PATH"
    # every not_run check names a missing tool
    for check in data["checks"]:
        if check["status"] == "not_run":
            assert "skippedReason" in check


def test_verify_properties_only_json(tmp_path):
    design = _design(tmp_path, with_property=True)
    proc = _run(
        "verify", str(design), "--library", str(LIBRARY_CSV),
        "--build", str(tmp_path / "b"), "--properties-only", "--json",
    )
    assert proc.returncode == 1
    data = _envelope(proc)["data"]
    assert [c["name"] for c in data["checks"]] == ["property never_both"]
    assert data["checks"][0]["status"] == "not_run"
    assert data["checks"][0]["skippedReason"] == "sby not found on PATH"


_MAPPED = (
    '{"modules": {"t": {'
    '"ports": {"x": {"direction": "input", "bits": [2]}},'
    '"cells": {'
    '"$1": {"type": "INV", "port_directions": {"A": "input", "Y": "output"},'
    '"connections": {"A": [2], "Y": [4]}}'
    "},"
    '"netnames": {"x": {"bits": [2]}, "n1": {"bits": [4]}}'
    "}}}"
)


def test_build_json_envelope(tmp_path):
    design = _design(tmp_path)
    mapped = tmp_path / "mapped.json"
    mapped.write_text(_MAPPED)
    proc = _run(
        "build", str(design), "--library", str(LIBRARY_CSV),
        "--out", str(tmp_path / "out"), "--mapped", str(mapped), "--json",
    )
    assert proc.returncode == 0, proc.stderr
    data = _envelope(proc)["data"]
    assert set(data) == {
        "bomPath", "netlistPath", "reportPath", "mappedJsonPath",
        "packageCount", "spareCount", "packCost", "bom", "analysis",
    }
    assert data["packageCount"] == 1
    assert data["spareCount"] == 0
    assert isinstance(data["packCost"], (int, float))
    # BOM lines carry the §C13 fields
    assert data["bom"]
    line = data["bom"][0]
    assert set(line) == {
        "partNumber", "manufacturers", "package", "quantity", "refdes",
        "tier", "singleSourced",
    }
    assert isinstance(line["manufacturers"], list)
    assert isinstance(line["refdes"], list)
    assert isinstance(line["singleSourced"], bool)
    # analysis shape
    analysis = data["analysis"]
    assert set(analysis) == {"metrics", "scoap", "faults", "cpldBlockers"}
    assert analysis["scoap"] == []  # §13.1 not computed — honest empty
    assert set(analysis["faults"]) == {"detected", "undetected", "redundant", "untestable"}
    assert analysis["cpldBlockers"] == []  # clean golden
    for metric in analysis["metrics"]:
        assert set(metric) == {"name", "value", "unit", "limit", "violated"}
        assert isinstance(metric["violated"], bool)


def test_compile_json_failure_envelope(tmp_path):
    proc = _run("compile", str(tmp_path / "missing.yaml"), "--json")
    assert proc.returncode == 1
    env = _envelope(proc)
    assert env["ok"] is False
    assert env["command"] == "compile"
    assert env["schema"] == 1
    err = env["error"]
    assert set(err) == {"severity", "code", "message"}
    assert err["severity"] == "error"
    assert err["code"] == "GP1003"
    # human diagnostics still go to stderr, never stdout
    assert "error:" in proc.stderr


def test_compile_json_stdout_is_exactly_one_object(tmp_path):
    design = _design(tmp_path)
    proc = _run("compile", str(design), "-o", str(tmp_path / "build"), "--json")
    # exactly one JSON document, nothing else on stdout
    stripped = proc.stdout.strip()
    assert stripped.count("\n") == 0
    json.loads(stripped)
