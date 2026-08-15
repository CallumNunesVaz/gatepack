"""CLI contract tests (§C6).

The public API of gatepack is its CLI plus the JSON/CSV artefacts it emits.
These tests pin the contract: exact exit codes, stable manifest.json keys,
deterministic sorted output, and no timestamps in the payload.  A change in any
of these must fail a test, because downstream tooling and the future GUI both
depend on the shape.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from gatepack.cli import (
    EXIT_ASYNC_REFUSED,
    EXIT_ERROR,
    EXIT_OK,
    EXIT_USAGE,
    main,
)

REPO = Path(__file__).resolve().parents[2]
LIBRARY_CSV = REPO / "libraries" / "74aup.csv"


def _write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text)
    return p


def _valid_design(tmp_path: Path) -> Path:
    return _write(
        tmp_path,
        "d.yaml",
        "name: t\n"
        "timing_model: synchronous\n"
        "clock: {signal: clk, freq_hz: 1, source: OSC}\n"
        "reset: {signal: rst_n, active: low}\n"
        "inputs:\n  - {name: x, sync: false}\n"
        "states: [A, B]\n"
        "initial: A\n"
        "transitions:\n"
        '  - {from: A, to: B, when: "x"}\n'
        '  - {from: A, to: A, when: "!x"}\n'
        '  - {from: B, to: A, when: "1"}\n'
        "output_logic: {}\n",
    )


def test_exit_codes_are_named_constants():
    # the contract is encoded in one place (gatepack.cli)
    assert (EXIT_OK, EXIT_ERROR, EXIT_USAGE, EXIT_ASYNC_REFUSED) == (0, 1, 2, 3)


def test_version_exits_zero():
    import pytest

    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == EXIT_OK


def test_no_args_is_usage_error():
    with __import__("pytest").raises(SystemExit) as exc:
        main([])
    assert exc.value.code == EXIT_USAGE


def test_lib_check_valid_exits_zero():
    assert main(["lib", "check", str(LIBRARY_CSV)]) == EXIT_OK


def test_compile_valid_writes_both_artefacts(tmp_path):
    design = _valid_design(tmp_path)
    out = tmp_path / "build"
    assert main(["compile", str(design), "-o", str(out)]) == EXIT_OK
    assert (out / "generated.v").exists()
    assert (out / "properties.sv").exists()


def test_compile_async_exits_async_refused(tmp_path):
    design = _write(
        tmp_path,
        "async.yaml",
        "name: a\n"
        "timing_model: asynchronous\n"
        "reset: {signal: rst_n, active: low}\n"
        "states: [A, B]\n"
        "initial: A\n"
        "transitions:\n"
        '  - {from: A, to: B, when: "1"}\n'
        '  - {from: B, to: A, when: "1"}\n'
        "output_logic: {}\n",
    )
    assert main(["compile", str(design)]) == EXIT_ASYNC_REFUSED


def test_compile_must_fail_design_exits_error(tmp_path):
    design = _write(
        tmp_path,
        "overlap.yaml",
        "name: o\n"
        "timing_model: synchronous\n"
        "clock: {signal: clk, freq_hz: 1, source: OSC}\n"
        "reset: {signal: rst_n, active: low}\n"
        "inputs:\n  - {name: x, sync: false}\n"
        "states: [A, B]\n"
        "initial: A\n"
        "transitions:\n"
        '  - {from: A, to: B, when: "x"}\n'
        '  - {from: A, to: B, when: "x"}\n'
        '  - {from: B, to: A, when: "1"}\n'
        "output_logic: {}\n",
    )
    assert main(["compile", str(design)]) == EXIT_ERROR


def test_compile_missing_file_exits_error(tmp_path):
    assert main(["compile", str(tmp_path / "nope.yaml")]) == EXIT_ERROR


def test_estimate_writes_deterministic_manifest(tmp_path):
    design = _valid_design(tmp_path)
    b1 = tmp_path / "b1"
    b2 = tmp_path / "b2"
    assert main(["estimate", str(design), "--library", str(LIBRARY_CSV), "--build", str(b1)]) == EXIT_OK
    assert main(["estimate", str(design), "--library", str(LIBRARY_CSV), "--build", str(b2)]) == EXIT_OK

    m1 = json.loads((b1 / "manifest.json").read_text())
    m2 = json.loads((b2 / "manifest.json").read_text())
    assert m1 == m2
    assert list(m1.keys()) == sorted(m1.keys())
    for key in ("tool", "tool_version", "design", "timing_model", "encoding", "verdict", "yosys", "schema_version"):
        assert key in m1
    assert "timestamp" not in str(m1)


def test_cli_contract_via_subprocess(tmp_path):
    # the "real installed CLI" exit-code path (module entry point)
    proc = subprocess.run(
        [sys.executable, "-m", "gatepack.cli", "--version"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == EXIT_OK
    assert proc.stdout.startswith("gatepack ")


_MAPPED = (
    '{"modules": {"t": {'
    '"ports": {"x": {"direction": "input", "bits": [2]}, "y": {"direction": "output", "bits": [4]}},'
    '"cells": {'
    '"$1": {"type": "INV", "port_directions": {"A": "input", "Y": "output"},'
    '"connections": {"A": [2], "Y": [4]}}'
    "},"
    '"netnames": {"x": {"bits": [2]}, "y": {"bits": [4]}}'
    "}}}"
)


def test_build_with_mapped_writes_artefacts(tmp_path):
    design = _valid_design(tmp_path)
    mapped = tmp_path / "mapped.json"
    mapped.write_text(_MAPPED)
    out = tmp_path / "out"
    assert (
        main(
            ["build", str(design), "--library", str(LIBRARY_CSV),
             "--out", str(out), "--mapped", str(mapped)]
        )
        == EXIT_OK
    )
    assert (out / "bom.csv").exists()
    assert (out / "netlist.net").exists()
    assert (out / "netlist.unpacked.net").exists()
    assert (out / "report.md").exists()
    assert (out / "refdes.json").exists()


def test_build_without_synthesis_exits_error(tmp_path):
    design = _valid_design(tmp_path)
    out = tmp_path / "out"
    # no --mapped and no yosys -> refuses rather than faking a result
    assert (
        main(
            ["build", str(design), "--library", str(LIBRARY_CSV),
             "--out", str(out)]
        )
        == EXIT_ERROR
    )
