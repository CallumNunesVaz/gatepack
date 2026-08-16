"""Acceptance test: the bundled core is a real, self-contained gatepack.

This is the test that previous rounds got wrong seven times.  It builds the
bundle, then invokes it under an environment scrubbed of every escape hatch —
no ``GATEPACK_CORE``, ``PYTHONPATH``/``PYTHONHOME`` unset, and ``PATH`` stripped
of every directory that contains a ``gatepack`` or a ``python3`` — and asserts
it still returns a valid envelope.  The bundle is reached *by bare name through
the scrubbed ``PATH``* (the only directory left on it is ``app/resources/bin``),
so if a host venv answered the call this test would be measuring nothing.

The negative half moves the bundle aside and asserts the same scrubbed
invocation now fails: if it still succeeded, a host ``gatepack`` is leaking
through the scrub and the positive half proves nothing.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CORE_NAME = "gatepack.exe" if os.name == "nt" else "gatepack"
BUNDLE = REPO / "app" / "resources" / "bin" / CORE_NAME
BUNDLER = REPO / "scripts" / "bundle_core.py"


def _pyinstaller_available() -> bool:
    try:
        import PyInstaller  # noqa: F401

        return True
    except ImportError:
        return False


def _has(directory: Path, name: str) -> bool:
    """True when ``directory`` contains ``name`` or its ``.exe`` variant.

    A Windows host has ``python.exe``/``gatepack.exe``, not ``python3``/
    ``gatepack``; a scrub that checks only the bare name leaks a host
    interpreter through and this test measures nothing.
    """
    return (directory / name).exists() or (directory / (name + ".exe")).exists()


def _scrubbed_env() -> dict[str, str]:
    """PATH with every ``gatepack``/``python`` directory removed; no override."""
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("GATEPACK_CORE", "PYTHONPATH", "PYTHONHOME")
    }
    kept: list[str] = []
    for directory in env.get("PATH", "").split(os.pathsep):
        if not directory:
            continue
        d = Path(directory)
        if d.is_dir() and any(_has(d, n) for n in ("gatepack", "python3", "python")):
            continue
        kept.append(directory)
    env["PATH"] = os.pathsep.join(kept)
    return env


def _env_with_bundle_dir() -> dict[str, str]:
    env = _scrubbed_env()
    env["PATH"] = os.pathsep.join([str(BUNDLE.parent), env["PATH"]])
    return env


def _run(cwd: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess:
    # invoked by bare name: only the scrubbed PATH can resolve it
    return subprocess.run(
        [CORE_NAME, *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


@pytest.fixture(scope="session")
def bundled_core() -> Path:
    if not _pyinstaller_available():
        pytest.skip(
            "PyInstaller is not importable from the test interpreter "
            "(build-only dependency; install with `pip install pyinstaller`)"
        )
    proc = subprocess.run(
        [sys.executable, str(BUNDLER)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"bundler failed:\n{proc.stdout}\n{proc.stderr}"
    assert BUNDLE.is_file(), "bundler reported success but wrote no binary"
    assert os.access(BUNDLE, os.X_OK), "bundled core is not executable"
    return BUNDLE


def test_bundled_core_answers_doctor_under_scrubbed_env(bundled_core, tmp_path):
    proc = _run(tmp_path, _env_with_bundle_dir(), "doctor", "--json")
    assert proc.returncode == 0, proc.stderr
    envelope = json.loads(proc.stdout)
    assert envelope["ok"] is True
    assert envelope["command"] == "doctor"
    assert envelope["schema"] == 1
    # the package data must actually be inside the bundle
    assert envelope["data"]["resources"]["commonFrontendYs"] is True
    assert envelope["data"]["resources"]["mcellModels"] is True


def test_bundled_core_compiles_a_design_under_scrubbed_env(bundled_core, tmp_path):
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
    proc = _run(tmp_path, _env_with_bundle_dir(), "compile", "d.yaml", "-o", "build", "--json")
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)["data"]
    assert data["encoding"] == "one_hot"
    assert data["stateCount"] == 2
    assert (tmp_path / "build" / "generated.v").exists()


def test_bundled_core_lists_and_extracts_examples(bundled_core, tmp_path):
    # `examples list` exits 0 even when it finds nothing, so exit 0 proves
    # nothing — assert it *names* the showcase.
    proc = _run(tmp_path, _env_with_bundle_dir(), "examples", "list")
    assert proc.returncode == 0, proc.stderr
    assert "pelican" in proc.stdout, proc.stdout

    target = tmp_path / "extracted"
    proc = _run(
        tmp_path, _env_with_bundle_dir(), "examples", "extract", "pelican", "-o", str(target)
    )
    assert proc.returncode == 0, proc.stderr
    assert (target / "design.yaml").is_file()
    assert (target / "parts.csv").is_file()


def test_scrub_is_scrubbing(bundled_core, tmp_path):
    hidden = BUNDLE.with_suffix(".hidden")
    shutil.move(str(BUNDLE), str(hidden))
    try:
        env = _env_with_bundle_dir()
        try:
            proc = _run(tmp_path, env, "doctor", "--json")
        except FileNotFoundError:
            return  # nothing resolved `gatepack` — the scrub holds
        assert proc.returncode != 0, (
            "the scrubbed invocation still succeeded after the bundle was moved "
            "aside: a host gatepack is leaking through the scrub"
        )
    finally:
        shutil.move(str(hidden), str(BUNDLE))


def test_bundle_passes_licence_audit(bundled_core):
    """The §4 audit sees the bundle's real contents, not the declared list.

    This is the licence side of the same claim the rest of this module makes:
    the bundle is opened and enumerated, and the components that make it
    GPL-3.0-compatible — pydantic (MIT), CPython (PSF) and the PyInstaller
    bootloader's bootloader exception — must all be named by the audit, not
    assumed from ``pyproject.toml``.
    """
    proc = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "licence_audit.py"), "--bundle", str(BUNDLE)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "pyinstaller-bootloader" in proc.stdout
    assert "bootloader-exception" in proc.stdout
    assert "pydantic: 'mit'" in proc.stdout
    assert "cpython: 'python-2.0'" in proc.stdout
