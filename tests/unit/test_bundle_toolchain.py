"""Unit tests for the toolchain bundler's cross-platform refusal.

The full bundle is built and proven by ``tests/toolchain/test_toolchain_bundle.py``
(needs the pinned ``gatepack-toolchain:m6`` image).  This module pins the part
that is *not* exercised by a Linux-only build but that the Windows/macOS release
paths depend on: ``bundle_toolchain.py`` must refuse — with an actionable message
naming what that platform does instead — rather than silently shipping Linux ELF
binaries in a Windows or macOS installer.  The refusal is exercised by injecting
``platform``, the same pattern ``scripts/bundle_core.py`` and ``gatepack.doctor``
already use.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BUNDLER = REPO / "scripts" / "bundle_toolchain.py"


def _load_bundler():
    spec = importlib.util.spec_from_file_location("bundle_toolchain_under_test", BUNDLER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_refusal_reason_is_none_on_linux():
    mod = _load_bundler()
    assert mod.refusal_reason("linux") is None
    # On this Linux host the default (host) platform is not refused either.
    assert mod.refusal_reason() is None


def test_refusal_reason_names_the_macos_route():
    mod = _load_bundler()
    reason = mod.refusal_reason("darwin")
    assert reason is not None
    # What a macOS machine would have to do, not a silent Linux-only assumption.
    assert "macOS" in reason
    assert "Homebrew" in reason
    assert "OSS CAD Suite" in reason
    assert "docs/MACOS.md" in reason


def test_refusal_reason_names_the_windows_route():
    mod = _load_bundler()
    reason = mod.refusal_reason("win32")
    assert reason is not None
    assert "Windows" in reason
    assert "OSS CAD Suite" in reason
    assert "WSL2" in reason
    assert "docs/WINDOWS.md" in reason


def test_bundle_refuses_before_touching_docker(monkeypatch):
    mod = _load_bundler()

    calls = {"n": 0}

    def image_available(image=mod.IMAGE):
        calls["n"] += 1
        raise AssertionError("image_available must not run before the refusal")

    monkeypatch.setattr(mod, "image_available", image_available)

    for platform, needle in (("darwin", "Homebrew"), ("win32", "WSL2")):
        with pytest.raises(RuntimeError) as excinfo:
            mod.bundle(platform=platform)
        assert needle in str(excinfo.value)

    assert calls["n"] == 0, "the refusal must fire before any docker call"


def test_bundle_linux_passes_the_refusal(monkeypatch):
    # On Linux the refusal is skipped and the script proceeds to the next check
    # (the toolchain image), which is a *different* failure than the refusal.
    mod = _load_bundler()
    monkeypatch.setattr(mod, "image_available", lambda: False)
    with pytest.raises(RuntimeError) as excinfo:
        mod.bundle(platform="linux")
    message = str(excinfo.value)
    assert "Homebrew" not in message
    assert "WSL2" not in message
    assert "image" in message
