"""CLI contract for the asynchronous path (§7.3, §C6).

The asynchronous path keeps the same exit-code contract as the rest of the CLI:
``0`` success, ``1`` error, ``3`` async-refused.  What is new here is that the
*specific* construct name in a stage refusal must reach the terminal intact, and
that a hazard-failing design is a *failed verification* (exit 1) with no netlist
written — never a green "passed" beside an unverified netlist.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from gatepack.cli import (
    EXIT_ASYNC_REFUSED,
    EXIT_ERROR,
    EXIT_OK,
    main,
)
from gatepack.verify.base import CheckResult, CheckStatus

REPO = Path(__file__).resolve().parents[2]
LIBRARY_CSV = REPO / "libraries" / "74aup.csv"
DESIGNS = REPO / "tests" / "golden" / "designs"


def _write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text)
    return p


def _no_fundamental_mode(tmp_path: Path) -> Path:
    return _write(
        tmp_path,
        "async.yaml",
        "name: a\n"
        "timing_model: asynchronous\n"
        "reset: {signal: rst_n, active: low}\n"
        "inputs: [{name: x, sync: false}]\n"
        "states: [A, B]\n"
        "initial: A\n"
        "transitions:\n"
        '  - {from: A, to: B, when: "x"}\n'
        '  - {from: A, to: A, when: "!x"}\n'
        '  - {from: B, to: B, when: "1"}\n'
        "output_logic: {}\n",
    )


def _admitted_async(tmp_path: Path) -> Path:
    return _write(
        tmp_path,
        "async_latch.yaml",
        "name: async_latch\n"
        "timing_model: asynchronous\n"
        "reset: {signal: rst_n, active: low}\n"
        "inputs: [{name: req, sync: false}, {name: ack, sync: false}]\n"
        "states: [IDLE, BUSY]\n"
        "initial: IDLE\n"
        "transitions:\n"
        '  - {from: IDLE, to: BUSY, when: "req"}\n'
        '  - {from: IDLE, to: IDLE, when: "!req"}\n'
        '  - {from: BUSY, to: IDLE, when: "ack"}\n'
        '  - {from: BUSY, to: BUSY, when: "!ack"}\n'
        "outputs: [{name: q}]\n"
        'output_logic: {q: "state == BUSY"}\n'
        "fundamental_mode: {mutually_exclusive: [[req, ack]]}\n",
    )


def test_compile_admitted_async_exits_zero(tmp_path):
    design = _admitted_async(tmp_path)
    assert main(["compile", str(design), "-o", str(tmp_path / "build")]) == EXIT_OK


def test_verify_admission_refusal_names_the_construct(tmp_path, capsys):
    design = _no_fundamental_mode(tmp_path)
    assert (
        main(
            ["verify", str(design), "--library", str(LIBRARY_CSV),
             "--build", str(tmp_path / "b")]
        )
        == EXIT_ASYNC_REFUSED
    )
    assert "fundamental_mode is required" in capsys.readouterr().err


def test_estimate_async_refused_with_reason(tmp_path, capsys):
    design = _admitted_async(tmp_path)
    assert (
        main(["estimate", str(design), "--library", str(LIBRARY_CSV),
              "--build", str(tmp_path / "b")])
        == EXIT_ASYNC_REFUSED
    )
    assert "§6" in capsys.readouterr().err


def test_verify_admissibility_refusal_names_both_inputs(tmp_path, capsys):
    # stage 2 (admissibility) refuses before z3 is needed, so the specific
    # "change simultaneously" message reaches the CLI even without the solver.
    assert (
        main(
            ["verify", str(DESIGNS / "async_two_input.yaml"),
             "--library", str(LIBRARY_CSV), "--build", str(tmp_path / "b")]
        )
        == EXIT_ASYNC_REFUSED
    )
    assert "simultaneously" in capsys.readouterr().err


def test_build_async_refusal_writes_no_artefacts(tmp_path, capsys):
    design = _no_fundamental_mode(tmp_path)
    out = tmp_path / "out"
    assert (
        main(
            ["build", str(design), "--library", str(LIBRARY_CSV),
             "--out", str(out)]
        )
        == EXIT_ERROR
    )
    assert "fundamental_mode is required" in capsys.readouterr().err
    assert not (out / "bom.csv").exists()
    assert not (out / "netlist.net").exists()
    assert not (out / "report.md").exists()
    assert not (out / "mapped.json").exists()


def test_hazard_failing_verify_is_failed_and_writes_no_netlist(
    tmp_path, monkeypatch, capsys
):
    # A stage-5 failure must surface as a *failed verification* (exit 1), with
    # the failing check named, and must leave no netlist file behind.
    design = _admitted_async(tmp_path)
    failed = CheckResult(
        "hazard (ternary)",
        CheckStatus.FAILED,
        "potential static hazard: q (static-1, changing req)",
        kind="hazard",
    )
    fake = SimpleNamespace(hazard_checks=[failed], hazard_passed=False)

    monkeypatch.setattr(
        "gatepack.verify.run.run_async_pipeline", lambda *a, **k: fake
    )

    build_dir = tmp_path / "b"
    assert (
        main(
            ["verify", str(design), "--library", str(LIBRARY_CSV),
             "--build", str(build_dir)]
        )
        == EXIT_ERROR
    )
    out = capsys.readouterr().out
    assert "verification: failed" in out
    assert "hazard (ternary)" in out
    assert "static-1" in out
    assert not (build_dir / "mapped.json").exists()
    assert not (build_dir / "mapped.v").exists()
