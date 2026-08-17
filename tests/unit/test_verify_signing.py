"""Tests for ``scripts/verify_signing.py`` — the step that turns "built with a
signing secret" into "verified signed".

The one property that matters most: the verifier must **fail** when handed an
unsigned artefact, and must **not** fabricate a pass when the platform's
signing tool is missing.  Because no macOS/Windows signing tool exists on this
Linux host, the tests inject *fake* tools that mimic the real tools' contract —
``codesign --verify`` exits non-zero when the target carries no signature,
``signtool verify /pa /v`` does the same — and the fake tool measures something
(the presence of a signature marker) rather than always passing.  The Linux
path is exercised against the real ``sha256sum``.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "verify_signing.py"

MARKER = "GATEPACK_TEST_SIGNATURE"


def _load():
    spec = importlib.util.spec_from_file_location("verify_signing_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_fake_tool(bindir: Path, name: str) -> None:
    """A fake signing tool that exits 0 iff its last argument contains MARKER.

    This is the honest stand-in for codesign/signtool: it *measures* whether the
    artefact carries a signature (here, a magic marker) and returns the tool's
    real contract — non-zero on an unsigned target.
    """
    tool = bindir / name
    tool.write_text(
        "#!/bin/sh\n"
        "for last; do :; done\n"
        f"if grep -q '{MARKER}' \"$last\" 2>/dev/null; then exit 0; else exit 1; fi\n"
    )
    tool.chmod(0o755)


def _make_tools(bindir: Path) -> None:
    for name in ("codesign", "spctl", "xcrun", "signtool"):
        _write_fake_tool(bindir, name)


def _run(argv: list[str], *, path: str | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if path is not None:
        # Prepend, not replace: the stub tools are found via PATH, and they in
        # turn still need the real PATH (e.g. grep) to do their measuring.
        env["PATH"] = path + os.pathsep + env.get("PATH", "")
    return subprocess.run(
        [sys.executable, str(SCRIPT), *argv],
        capture_output=True,
        text=True,
        env=env,
    )


def _signed_file(root: Path, name: str) -> Path:
    p = root / name
    p.write_text(f"some binary bytes\n{MARKER}\n")
    return p


def _unsigned_file(root: Path, name: str) -> Path:
    p = root / name
    p.write_text("some binary bytes\n")
    return p


# ---------------------------------------------------------------------------
# The one that matters: unsigned is rejected, signed is accepted.
# ---------------------------------------------------------------------------


def test_macos_unsigned_artefact_is_rejected(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    _make_tools(bindir)
    app = _unsigned_file(tmp_path, "gatepack.app")

    proc = _run(["macos", "--app", str(app)], path=str(bindir))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "NOT VERIFIED" in proc.stdout


def test_macos_signed_artefact_is_verified(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    _make_tools(bindir)
    app = _signed_file(tmp_path, "gatepack.app")

    proc = _run(["macos", "--app", str(app)], path=str(bindir))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "verified" in proc.stdout


def test_windows_unsigned_exe_is_rejected(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    _make_tools(bindir)
    exe = _unsigned_file(tmp_path, "gatepack-setup.exe")

    proc = _run(["windows", "--file", str(exe)], path=str(bindir))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "NOT VERIFIED" in proc.stdout


# ---------------------------------------------------------------------------
# A missing tool is reported, never substituted with a pass.
# ---------------------------------------------------------------------------


def test_missing_tool_is_cannot_verify_not_passed(tmp_path):
    empty_bin = tmp_path / "empty"
    empty_bin.mkdir()
    app = _signed_file(tmp_path, "gatepack.app")

    proc = _run(["macos", "--app", str(app)], path=str(empty_bin))
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "cannot verify" in proc.stdout


# ---------------------------------------------------------------------------
# Linux: real sha256sum over a real SHA256SUMS.
# ---------------------------------------------------------------------------


def _write_sums(sums_dir: Path, name: str, data: bytes) -> str:
    (sums_dir / name).write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    (sums_dir / "SHA256SUMS").write_text(f"{digest}  {name}\n")
    return digest


def test_linux_checksum_coverage_passes_when_complete(tmp_path):
    sums_dir = tmp_path / "sums"
    sums_dir.mkdir()
    _write_sums(sums_dir, "gatepack.AppImage", b"appimage")

    proc = _run(["linux", "--sums-dir", str(sums_dir)])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "verified" in proc.stdout


def test_linux_checksum_coverage_fails_on_tamper(tmp_path):
    sums_dir = tmp_path / "sums"
    sums_dir.mkdir()
    _write_sums(sums_dir, "gatepack.AppImage", b"appimage")
    # Tamper with the artefact without updating the sums: sha256sum -c fails.
    (sums_dir / "gatepack.AppImage").write_bytes(b"tampered")

    proc = _run(["linux", "--sums-dir", str(sums_dir)])
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "NOT VERIFIED" in proc.stdout


def test_linux_checksum_coverage_fails_on_missing_entry(tmp_path):
    sums_dir = tmp_path / "sums"
    sums_dir.mkdir()
    # SHA256SUMS does not cover the artefact that is present.
    (sums_dir / "gatepack.deb").write_bytes(b"deb")
    (sums_dir / "SHA256SUMS").write_text("")  # no entries

    proc = _run(["linux", "--sums-dir", str(sums_dir)])
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "NOT VERIFIED" in proc.stdout


# ---------------------------------------------------------------------------
# Pure logic: command construction and verdict classification.
# ---------------------------------------------------------------------------


def test_macos_checks_argv():
    mod = _load()
    app = Path("/tmp/x.app")
    checks = mod.macos_checks(app)
    assert [c.name for c in checks] == [
        "codesign --verify --deep --strict --verbose=2",
        "spctl --assess --type execute",
        "xcrun stapler validate",
    ]
    assert checks[0].argv == ["codesign", "--verify", "--deep", "--strict", "--verbose=2", "/tmp/x.app"]
    assert checks[1].argv == ["spctl", "--assess", "--type", "execute", "/tmp/x.app"]


def test_windows_checks_argv():
    mod = _load()
    checks = mod.windows_checks(Path("/tmp/x.exe"))
    assert checks[0].argv == ["signtool", "verify", "/pa", "/v", "/tmp/x.exe"]


def test_linux_checks_are_run_in_the_sums_dir():
    mod = _load()
    checks = mod.linux_checks(Path("/tmp/sums"))
    assert checks[0].argv == ["sha256sum", "-c", "SHA256SUMS"]
    assert checks[0].cwd == "/tmp/sums"


def test_classify_three_verdicts():
    mod = _load()
    R = mod.Result
    ok = [R("a", 0, "", "", False)]
    assert mod.classify(ok) == (mod.EXIT_VERIFIED, "verified — 1 check(s) passed")

    bad = [R("a", 1, "", "unsigned", False)]
    code, verdict = mod.classify(bad)
    assert code == mod.EXIT_UNVERIFIED
    assert "NOT VERIFIED" in verdict

    missing = [R("a", -1, "", "not installed", True)]
    code, verdict = mod.classify(missing)
    assert code == mod.EXIT_CANNOT_VERIFY
    assert "cannot verify" in verdict


def test_run_check_reports_a_missing_tool():
    mod = _load()
    result = mod.run_check(mod.Check("x", ["definitely-not-a-real-tool-xyz", "arg"]))
    assert result.tool_missing is True
    assert result.returncode == -1
