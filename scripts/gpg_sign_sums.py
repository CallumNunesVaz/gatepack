#!/usr/bin/env python3
"""Produce a detached GPG signature over a SHA256SUMS file (§5.2, signing).

Linux has no OS-level code signing; the closest a maintainer can get is a
detached GPG signature over the checksum file, so a downloader can authenticate
the checksums before trusting the artefacts.  This script produces that
signature.

The signing key is read from ``GPG_PRIVATE_KEY`` in the environment (an
ASCII-armored private key block) — never from a file in the repository, and
never printed to a log.  It is imported into an ephemeral ``GNUPGHOME`` that is
deleted afterwards, and ``<sums>.sig`` is written beside the checksum file.

Absent ``GPG_PRIVATE_KEY`` the script prints that the release is checksum-only
and exits 0: a detached signature is optional, and its absence is announced
rather than hidden.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def import_key(armored: str, gpg_home: Path, runner=subprocess.run) -> subprocess.CompletedProcess:
    """Import the armored private key into ``gpg_home``."""
    return runner(
        ["gpg", "--batch", "--import"],
        cwd=None,
        capture_output=True,
        text=True,
        input=armored,
        env=_gpg_env(gpg_home),
    )


def detach_sign(sums_path: Path, gpg_home: Path, runner=subprocess.run) -> subprocess.CompletedProcess:
    """Write a detached ASCII-armored signature ``<sums>.sig`` beside ``sums_path``."""
    return runner(
        [
            "gpg", "--batch", "--yes", "--armor", "--detach-sign",
            "--output", f"{sums_path.name}.sig",
            sums_path.name,
        ],
        cwd=str(sums_path.parent),
        capture_output=True,
        text=True,
        env=_gpg_env(gpg_home),
    )


def verify_sig(sums_path: Path, gpg_home: Path, runner=subprocess.run) -> subprocess.CompletedProcess:
    """Self-verify the detached signature just produced, in the same keyring."""
    return runner(
        ["gpg", "--batch", "--verify", f"{sums_path.name}.sig", sums_path.name],
        cwd=str(sums_path.parent),
        capture_output=True,
        text=True,
        env=_gpg_env(gpg_home),
    )


def _gpg_env(gpg_home: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["GNUPGHOME"] = str(gpg_home)
    return env


def sign(sums_path: Path, armored: str, runner=subprocess.run) -> tuple[bool, str]:
    """Import the key and sign ``sums_path``.  Returns (ok, message)."""
    if not armored.strip():
        return True, "no GPG_PRIVATE_KEY — producing a checksum-only release (no detached signature)"

    if shutil.which("gpg") is None:
        return False, "gpg is not installed; cannot produce the detached signature"

    gpg_home = Path(tempfile.mkdtemp(prefix="gatepack-gpg-"))
    os.chmod(gpg_home, 0o700)
    try:
        imported = import_key(armored, gpg_home, runner=runner)
        if imported.returncode != 0:
            return False, f"gpg --import failed:\n{imported.stderr}"
        signed = detach_sign(sums_path, gpg_home, runner=runner)
        if signed.returncode != 0:
            return False, f"gpg --detach-sign failed:\n{signed.stderr}"
        verified = verify_sig(sums_path, gpg_home, runner=runner)
        if verified.returncode != 0:
            return False, f"gpg --verify failed on the signature it just made:\n{verified.stderr}"
        return True, f"wrote and verified {sums_path.name}.sig"
    finally:
        shutil.rmtree(gpg_home, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="detach-sign a SHA256SUMS file with GPG_PRIVATE_KEY from the environment"
    )
    parser.add_argument("sums", help="path to the SHA256SUMS file")
    args = parser.parse_args(argv)

    sums_path = Path(args.sums)
    if not sums_path.is_file():
        print(f"error: not a file: {sums_path}", file=sys.stderr)
        return 1

    armored = os.environ.get("GPG_PRIVATE_KEY", "")
    ok, message = sign(sums_path, armored)
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
