"""Packaging test: the unpacked app really contains the bundled core.

Builds the bundle (via ``scripts/bundle_core.py``), runs ``npx electron-builder
--linux dir`` (output ``../.gpout/dist`` per ``app/electron-builder.yml``), then
greps the unpacked tree: ``resources/resources/bin/gatepack`` must be present,
executable, and outside the asar.  This is a real check on real output, not a
config read.

Gated behind ``GATEPACK_PACKAGING=1`` because electron-builder takes minutes;
the bundle acceptance test (``tests/toolchain/test_core_bundle.py``) runs in the
normal suite.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "app"
BUNDLE = APP / "resources" / "bin" / "gatepack"
BUNDLER = REPO / "scripts" / "bundle_core.py"
DIST = REPO / ".gpout" / "dist"

pytestmark = pytest.mark.skipif(
    os.environ.get("GATEPACK_PACKAGING") != "1",
    reason="set GATEPACK_PACKAGING=1 to run the slow electron-builder packaging test",
)


def _npx_available() -> bool:
    try:
        proc = subprocess.run(
            ["npx", "--version"], capture_output=True, text=True, timeout=60
        )
        return proc.returncode == 0
    except FileNotFoundError:
        return False


def _ensure_bundle() -> None:
    if BUNDLE.is_file():
        return
    proc = subprocess.run(
        [sys.executable, str(BUNDLER)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"bundler failed:\n{proc.stdout}\n{proc.stderr}"


def test_unpacked_app_contains_bundled_core():
    if not _npx_available():
        pytest.skip("npx is not on PATH (electron-builder unavailable)")
    _ensure_bundle()

    # electron-builder needs the compiled app (dist/main + dist/renderer) to
    # exist first; `npm run build` is the documented build step (RELEASING.md).
    build = subprocess.run(
        ["npm", "run", "build"],
        cwd=str(APP),
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert build.returncode == 0, f"app build failed:\n{build.stdout}\n{build.stderr}"

    proc = subprocess.run(
        ["npx", "electron-builder", "--linux", "dir"],
        cwd=str(APP),
        capture_output=True,
        text=True,
        timeout=1200,
    )
    assert proc.returncode == 0, (
        f"electron-builder failed:\n{proc.stdout}\n{proc.stderr}"
    )

    unpacked = DIST / "linux-unpacked"
    assert unpacked.is_dir(), f"no linux-unpacked tree at {unpacked}"

    target = unpacked / "resources" / "resources" / "bin" / "gatepack"
    assert target.is_file(), f"bundled core not present at {target}"
    assert os.access(target, os.X_OK), "bundled core is not executable"
    # outside the asar: a real file in the unpacked tree, not inside app.asar
    assert "app.asar" not in target.parts
