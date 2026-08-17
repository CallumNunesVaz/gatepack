"""Acceptance test: the bundled toolchain is real, not a host-tool leak.

The same shape as ``test_core_bundle.py``, and both halves matter.  With the
toolchain bundled, a *scrubbed* environment (``env -i``, no ``PATH``) must run
``gatepack build`` on the pelican showcase and produce the same 19-package BOM
the toolchain container produces.  Then the bundled binaries are moved aside and
the same invocation must *fail* — without that negative half, a host yosys
answering the call would prove nothing.

The environment is scrubbed of every escape hatch: ``env -i`` leaves no
``PATH`` at all, so the only yosys/iverilog/z3/sby that can answer is the one in
``app/resources/bin`` reached through the frozen core's bundled-toolchain
resolution (``gatepack/toolchain.py``).  A host toolchain is absent from this
machine entirely, so a green build here is only possible through the bundle.
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
BIN = REPO / "app" / "resources" / "bin"
CORE = BIN / "gatepack"
BUNDLER = REPO / "scripts" / "bundle_toolchain.py"
CORE_BUNDLER = REPO / "scripts" / "bundle_core.py"
IMAGE = "gatepack-toolchain:m6"
DESIGN = "examples/pelican/design.yaml"
LIBRARY = "libraries/74aup.csv"


def _pyinstaller_available() -> bool:
    try:
        import PyInstaller  # noqa: F401

        return True
    except ImportError:
        return False


def _toolchain_image_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return (
        subprocess.run(
            ["docker", "image", "inspect", IMAGE], capture_output=True, text=True
        ).returncode
        == 0
    )


@pytest.fixture(scope="session")
def bundled_toolchain() -> Path:
    if not CORE.is_file():
        if not _pyinstaller_available():
            pytest.skip("PyInstaller missing; cannot build the bundled core")
        proc = subprocess.run(
            [sys.executable, str(CORE_BUNDLER)], cwd=str(REPO), capture_output=True, text=True
        )
        assert proc.returncode == 0, f"bundle_core failed:\n{proc.stdout}\n{proc.stderr}"

    if not (BIN / "yosys").is_file():
        if not _toolchain_image_available() or not _pyinstaller_available():
            pytest.skip(
                f"toolchain image {IMAGE} (or PyInstaller) unavailable; cannot "
                "produce the bundled toolchain — see Dockerfile.probe"
            )
        proc = subprocess.run(
            [sys.executable, str(BUNDLER)], cwd=str(REPO), capture_output=True, text=True
        )
        assert proc.returncode == 0, f"bundle_toolchain failed:\n{proc.stdout}\n{proc.stderr}"

    assert (BIN / "yosys").is_file()
    assert (BIN / "iverilog").is_file()
    assert (BIN / "sby").is_file()
    assert (BIN / "z3").is_file()
    return BIN


def _run(cwd: Path, home: Path, *args: str) -> subprocess.CompletedProcess:
    # PATH empty (scrubbed of every tool); HOME points at a scratch dir so
    # yosys's $HOME/.yosys_history does not land in the repo (the review caught
    # a stray one at the worktree root).
    env = {"PATH": "", "HOME": str(home)}
    return subprocess.run(
        [str(CORE), *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )


def test_bundled_toolchain_builds_pelican_under_scrubbed_env(bundled_toolchain, tmp_path):
    out = tmp_path / "out"
    home = tmp_path / "home"
    home.mkdir()
    proc = _run(
        REPO,
        home,
        "build",
        str(REPO / DESIGN),
        "--library",
        str(REPO / LIBRARY),
        "--out",
        str(out),
        "--json",
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    envelope = json.loads(proc.stdout)
    assert envelope["ok"] is True
    # the same 19-package BOM the toolchain container produces
    assert envelope["data"]["packageCount"] == 19


def test_bundled_toolchain_doctor_reports_bundled_copies(bundled_toolchain, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    proc = _run(REPO, home, "doctor", "--json")
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)["data"]
    by_name = {t["name"]: t for t in data["tools"]}
    for name in ("yosys", "sby", "iverilog", "vvp", "z3"):
        assert by_name[name]["found"] is True
        assert by_name[name]["source"] == "bundled", name
    assert data["allToolsPresent"] is True


def test_scrub_is_scrubbing(bundled_toolchain, tmp_path):
    """The negative half: move yosys aside and the same invocation must fail."""
    yosys = BIN / "yosys"
    hidden = BIN / "yosys.hidden"
    shutil.move(str(yosys), str(hidden))
    home = tmp_path / "home"
    home.mkdir()
    try:
        proc = _run(
            REPO,
            home,
            "build",
            str(REPO / DESIGN),
            "--library",
            str(REPO / LIBRARY),
            "--out",
            str(tmp_path / "out"),
            "--json",
        )
        assert proc.returncode == 1, (
            "build still succeeded after yosys was moved aside: a host yosys is "
            "leaking through the scrub"
        )
        assert "yosys" in (proc.stderr or proc.stdout)
    finally:
        shutil.move(str(hidden), str(yosys))


def test_sby_error_is_failed_with_the_cause_not_not_run(bundled_toolchain, tmp_path):
    """An sby ERROR is a *failed* check naming the cause, never a silent not_run.

    The review's exact regression: sby exits rc=16 and its message is discarded,
    reported as ``not_run`` / "unrecognized output".  This moves z3 aside so the
    smtbmc engine cannot find a solver, runs the real bundled verify, and asserts
    the property check is FAILED with the cause in its detail — an assertion that
    merely checked ``status == not_run`` would have passed on the broken code.
    """
    z3 = BIN / "z3"
    hidden = BIN / "z3.hidden"
    shutil.move(str(z3), str(hidden))
    home = tmp_path / "home"
    home.mkdir()
    try:
        proc = _run(
            REPO,
            home,
            "verify",
            str(REPO / "tests/golden/designs/traffic_light.yaml"),
            "--library",
            str(REPO / LIBRARY),
            "--build",
            str(tmp_path / "build"),
            "--json",
        )
        assert proc.returncode == 1
        envelope = json.loads(proc.stdout)
        prop = next(
            c for c in envelope["data"]["checks"] if c["name"].startswith("property")
        )
        assert prop["status"] == "failed"
        reason = prop.get("detail", "")
        assert "ERROR" in reason or "not found" in reason, reason
    finally:
        shutil.move(str(hidden), str(z3))
