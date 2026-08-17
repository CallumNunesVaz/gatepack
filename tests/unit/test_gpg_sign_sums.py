"""Tests for ``scripts/gpg_sign_sums.py`` — the optional detached GPG
signature over ``SHA256SUMS``.

The signing key is read from ``GPG_PRIVATE_KEY`` (environment), never from a
file in the repo and never printed.  These tests exercise the three outcomes
with the real ``gpg`` (which IS present on this host):

  1. a valid armored key produces ``SHA256SUMS.sig`` *and* the script verifies
     its own signature before reporting success;
  2. a garbage key fails — never a silent "signed";
  3. an absent key is announced (checksum-only), not hidden.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "gpg_sign_sums.py"


def _load():
    spec = importlib.util.spec_from_file_location("gpg_sign_sums_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _gpg_available() -> bool:
    return shutil.which("gpg") is not None


def _make_armored_key() -> str:
    """Generate a throwaway key (clearly test-only) and return its armored private key."""
    home = Path(tempfile.mkdtemp(prefix="gatepack-gpg-test-"))
    os.chmod(home, 0o700)
    env = dict(os.environ)
    env["GNUPGHOME"] = str(home)
    params = (
        "%no-protection\n"
        "Key-Type: RSA\n"
        "Key-Length: 2048\n"
        "Subkey-Type: RSA\n"
        "Name-Real: gatepack test\n"
        "Name-Email: test@gatepack.invalid\n"
        "Expire-Date: 0\n"
        "%commit\n"
    )
    try:
        gen = subprocess.run(
            ["gpg", "--batch", "--generate-key"],
            input=params, capture_output=True, text=True, env=env,
        )
        assert gen.returncode == 0, gen.stderr
        exp = subprocess.run(
            ["gpg", "--batch", "--armor", "--export-secret-keys"],
            capture_output=True, text=True, env=env,
        )
        assert exp.returncode == 0, exp.stderr
        assert "-----BEGIN PGP PRIVATE KEY BLOCK-----" in exp.stdout
        return exp.stdout
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_sign_produces_and_self_verifies_a_signature(tmp_path):
    if not _gpg_available():
        pytest.skip("gpg not on PATH; cannot exercise the detached-signature path")
    sums = tmp_path / "SHA256SUMS"
    sums.write_text("abc123  foo\n")

    mod = _load()
    ok, message = mod.sign(sums, _make_armored_key())

    assert ok, message
    sig = tmp_path / "SHA256SUMS.sig"
    assert sig.is_file()
    assert sig.read_text().startswith("-----BEGIN PGP SIGNATURE-----")
    assert "verified" in message


def test_sign_rejects_a_garbage_key(tmp_path):
    if not _gpg_available():
        pytest.skip("gpg not on PATH; cannot exercise the detached-signature path")
    sums = tmp_path / "SHA256SUMS"
    sums.write_text("abc123  foo\n")

    mod = _load()
    ok, message = mod.sign(sums, "this is not a PGP private key\n")

    assert not ok
    assert not (tmp_path / "SHA256SUMS.sig").exists()


def test_sign_absent_key_is_announced_not_hidden(tmp_path):
    sums = tmp_path / "SHA256SUMS"
    sums.write_text("abc123  foo\n")

    mod = _load()
    ok, message = mod.sign(sums, "")

    assert ok
    assert "no GPG_PRIVATE_KEY" in message
    assert not (tmp_path / "SHA256SUMS.sig").exists()


def test_main_reports_missing_sums_file():
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(REPO / "does-not-exist-SHA256SUMS")],
        capture_output=True, text=True,
    )
    assert proc.returncode == 1
    assert "not a file" in proc.stderr
