"""Unit tests for the core bundler's cross-platform naming and scrub logic.

The full bundle is built and proven by ``tests/toolchain/test_core_bundle.py``
(needs PyInstaller).  This module pins the parts that are *not* exercised by a
Linux-only build but that a Windows/macOS release depends on: the ``.exe``
suffix and the environment scrub detecting ``python.exe``/``gatepack.exe``.
A scrub that misses the ``.exe`` variant leaks a host interpreter through on
Windows, which would make the bundled-core acceptance test measure nothing.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BUNDLER = REPO / "scripts" / "bundle_core.py"


def _load_bundler():
    spec = importlib.util.spec_from_file_location("bundle_core_under_test", BUNDLER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_binary_name_is_platform_aware(monkeypatch):
    mod = _load_bundler()
    # On a POSIX host the bundle is bare-named; on Windows it carries .exe.
    assert mod.binary_name() == "gatepack"
    monkeypatch.setattr(mod.os, "name", "nt")
    assert mod.binary_name() == "gatepack.exe"


def test_has_executable_detects_exe_variant(tmp_path):
    mod = _load_bundler()
    assert not mod._has_executable(tmp_path, "gatepack")
    (tmp_path / "gatepack.exe").write_text("x")
    assert mod._has_executable(tmp_path, "gatepack")
    (tmp_path / "python3").write_text("x")
    assert mod._has_executable(tmp_path, "python3")


def test_scrubbed_env_removes_interpreter_dirs(tmp_path, monkeypatch):
    mod = _load_bundler()
    py3 = tmp_path / "py3"
    py3.mkdir()
    (py3 / "python3").write_text("x")
    winpy = tmp_path / "winpy"
    winpy.mkdir()
    (winpy / "python.exe").write_text("x")
    clean = tmp_path / "clean"
    clean.mkdir()

    monkeypatch.setenv("PATH", os.pathsep.join([str(py3), str(winpy), str(clean)]))
    env = mod._scrubbed_env()
    kept = env["PATH"].split(os.pathsep)
    assert str(clean) in kept
    assert str(py3) not in kept
    assert str(winpy) not in kept
