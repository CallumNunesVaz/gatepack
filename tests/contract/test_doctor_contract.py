"""Contract tests for ``gatepack doctor`` and the missing-tool error path.

Two things are pinned here, both of which previous rounds got wrong:

1. ``doctor --json`` emits the standard envelope (``ok``/``command``/
   ``schema``/``data``) and always exits 0, because it is a *report* — a
   bundled core with no toolchain must still answer a valid envelope.

2. The missing-binary path is legible: a user with a bundled core and no
   ``yosys`` gets a message that names the binary *and* what it is for, never a
   stack trace or a silent empty result.  This is exercised against a real
   resolver — ``PATH`` is pointed at an empty directory so ``shutil.which``
   genuinely finds nothing — not against a mock.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LIBRARY_CSV = REPO / "libraries" / "74aup.csv"


def _valid_design(tmp_path: Path) -> Path:
    design = tmp_path / "d.yaml"
    design.write_text(
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
    return design


def test_doctor_json_envelope():
    proc = subprocess.run(
        [sys.executable, "-m", "gatepack.cli", "doctor", "--json"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    env = json.loads(proc.stdout)
    assert env["ok"] is True
    assert env["command"] == "doctor"
    assert env["schema"] == 1
    assert env["warnings"] == []
    data = env["data"]
    assert set(data) == {"version", "tools", "resources", "allToolsPresent"}
    assert isinstance(data["allToolsPresent"], bool)
    # every tool entry names the binary and its purpose, and reports a version
    # string only when found
    for tool in data["tools"]:
        assert set(tool) == {"name", "found", "purpose", "direct", "path", "version"}
        assert tool["name"] in {"yosys", "sby", "iverilog", "vvp", "z3", "espresso"}
        assert tool["purpose"]
        if tool["found"]:
            assert tool["path"]
            assert tool["version"]
        else:
            assert tool["path"] is None
            assert tool["version"] is None
    # bundled resources are loadable from the source tree
    assert data["resources"]["commonFrontendYs"] is True
    assert data["resources"]["mcellModels"] is True


def test_doctor_exits_zero_even_with_no_toolchain(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    env = {**os.environ, "PATH": str(empty)}
    proc = subprocess.run(
        [sys.executable, "-m", "gatepack.cli", "doctor", "--json"],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)["data"]
    assert data["allToolsPresent"] is False
    assert all(t["found"] is False for t in data["tools"])


def test_build_without_yosys_names_tool_and_purpose(tmp_path):
    design = _valid_design(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()
    env = {**os.environ, "PATH": str(empty)}
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "gatepack.cli",
            "build",
            str(design),
            "--library",
            str(LIBRARY_CSV),
            "--out",
            str(tmp_path / "out"),
        ],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    combined = f"{proc.stdout}\n{proc.stderr}"
    assert "yosys" in combined
    assert "logic synthesis" in combined
    # not a stack trace
    assert "Traceback" not in combined


def test_build_without_yosys_json_error_is_stable(tmp_path):
    design = _valid_design(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()
    env = {**os.environ, "PATH": str(empty)}
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "gatepack.cli",
            "build",
            str(design),
            "--library",
            str(LIBRARY_CSV),
            "--out",
            str(tmp_path / "out"),
            "--json",
        ],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    envelope = json.loads(proc.stdout)
    assert envelope["ok"] is False
    assert envelope["command"] == "build"
    err = envelope["error"]
    assert err["severity"] == "error"
    assert err["code"] == "GP1006"
    assert "yosys" in err["message"]
    assert "logic synthesis" in err["message"]
