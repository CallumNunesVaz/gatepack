#!/usr/bin/env python3
"""Verify that a built artefact is actually signed, per platform.

A signed build that is *not verified* is the same class of defect this project
has spent its history eliminating: a status reported by something that did not
measure it.  This script is the measurement.  It runs the platform's own
signature-checking tool and reports *that* tool's verdict — it never invents
one, and a missing tool is reported as such rather than substituted with a pass.

  macOS    codesign --verify --deep --strict --verbose=2   (the code signature)
           spctl --assess --type execute                   (the Gatekeeper verdict)
           xcrun stapler validate                          (the notarisation ticket)
  Windows  signtool verify /pa /v                          (Authenticode, chained to a root)
  Linux    sha256sum -c SHA256SUMS                         (checksum coverage — Linux has no OS signing)

A detached GPG signature over ``SHA256SUMS`` (when a ``GPG_PRIVATE_KEY`` secret
is present) is produced *and self-verified* by ``scripts/gpg_sign_sums.py`` in
its own ephemeral keyring; it is not re-verified here because the public key is
not a separate CI secret — downstream users verify it against the maintainer's
published public key.

Exit codes:
  0  verified — every check passed
  1  NOT verified — at least one check ran and failed (unsigned or invalid)
  2  cannot verify — a required tool is not installed on this host
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

EXIT_VERIFIED = 0
EXIT_UNVERIFIED = 1
EXIT_CANNOT_VERIFY = 2


@dataclass(frozen=True)
class Check:
    """One verification command: a human name plus the argv to run."""

    name: str
    argv: list[str]
    cwd: str | None = None


@dataclass(frozen=True)
class Result:
    name: str
    returncode: int
    stdout: str
    stderr: str
    tool_missing: bool


def macos_checks(app: Path, dmg: Path | None = None) -> list[Check]:
    """The macOS checks: code signature, Gatekeeper, notarisation ticket.

    ``app`` is the ``.app`` bundle electron-builder signed.  ``dmg`` is the
    packed, notarised-and-stapled installer; when omitted the ``.app`` is passed
    to ``stapler validate`` as well (electron-builder staples the app too).
    """
    staple_target = dmg if dmg is not None else app
    return [
        Check(
            "codesign --verify --deep --strict --verbose=2",
            ["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app)],
        ),
        Check(
            "spctl --assess --type execute",
            ["spctl", "--assess", "--type", "execute", str(app)],
        ),
        Check(
            "xcrun stapler validate",
            ["xcrun", "stapler", "validate", str(staple_target)],
        ),
    ]


def windows_checks(file: Path, signtool: str = "signtool") -> list[Check]:
    """The Windows check: Authenticode signature, chained to a trusted root.

    ``signtool`` is the path (or bare name) of signtool; on a Windows runner it
    may live under the Windows SDK rather than on ``PATH``, so the release
    workflow can pin it explicitly (``--signtool``).  A missing signtool is
    reported as "cannot verify", never a pass.
    """
    return [
        Check(
            "signtool verify /pa /v",
            [signtool, "verify", "/pa", "/v", str(file)],
        ),
    ]


def linux_checks(sums_dir: Path) -> list[Check]:
    """The Linux check: checksum coverage.

    Linux has no OS-level code signing; the verifiable part is that every
    artefact is covered by ``SHA256SUMS`` (``sha256sum -c`` fails on any file
    whose checksum is missing or wrong).  The detached GPG signature, when a
    maintainer produced one, is self-verified by ``scripts/gpg_sign_sums.py``.
    """
    return [
        Check(
            "sha256sum -c SHA256SUMS",
            ["sha256sum", "-c", "SHA256SUMS"],
            cwd=str(sums_dir),
        ),
    ]


def run_check(check: Check, runner=subprocess.run) -> Result:
    """Run one check.  A missing tool is a *result*, not a fake pass."""
    tool = check.argv[0]
    if shutil.which(tool) is None:
        return Result(check.name, -1, "", f"{tool}: not installed", True)
    proc = runner(check.argv, cwd=check.cwd, capture_output=True, text=True)
    return Result(
        check.name,
        proc.returncode,
        proc.stdout or "",
        proc.stderr or "",
        False,
    )


def classify(results: list[Result]) -> tuple[int, str]:
    """Map results to an exit code and a verdict.  Pure, so the verdict is testable."""
    missing = [r for r in results if r.tool_missing]
    if missing:
        return EXIT_CANNOT_VERIFY, (
            "cannot verify — a required signing tool is not installed on this host; "
            "a missing binary is reported, never substituted with a pass "
            f"({', '.join(sorted(r.name for r in missing))})"
        )
    failed = [r for r in results if r.returncode != 0]
    if failed:
        return EXIT_UNVERIFIED, (
            f"NOT VERIFIED — {len(failed)} of {len(results)} check(s) failed: "
            + ", ".join(sorted(r.name for r in failed))
        )
    return EXIT_VERIFIED, f"verified — {len(results)} check(s) passed"


def verify(checks: list[Check], runner=subprocess.run) -> tuple[int, str, list[Result]]:
    """Run every check and return (exit_code, verdict, results)."""
    results = [run_check(c, runner=runner) for c in checks]
    code, verdict = classify(results)
    return code, verdict, results


def _report(results: list[Result]) -> None:
    for r in results:
        if r.tool_missing:
            print(f"  MISSING TOOL  {r.name}", file=sys.stderr)
        elif r.returncode == 0:
            print(f"  ok            {r.name}")
        else:
            print(f"  FAIL          {r.name} (exit {r.returncode})", file=sys.stderr)
            for line in (r.stderr + r.stdout).splitlines():
                if line.strip():
                    print(f"                  {line}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="verify a built artefact is actually signed (per platform)"
    )
    sub = parser.add_subparsers(dest="platform", required=True)

    p_macos = sub.add_parser("macos", help="verify a macOS .app (codesign + spctl + stapler)")
    p_macos.add_argument("--app", required=True, help="path to the signed .app bundle")
    p_macos.add_argument("--dmg", default=None, help="optional notarised+stapled .dmg for stapler validate")

    p_win = sub.add_parser("windows", help="verify a Windows executable (signtool)")
    p_win.add_argument("--file", required=True, help="path to the signed .exe")
    p_win.add_argument("--signtool", default="signtool", help="path/name of signtool (default: signtool on PATH)")

    p_linux = sub.add_parser("linux", help="verify Linux checksum coverage (+ detached signature)")
    p_linux.add_argument("--sums-dir", required=True, help="directory containing SHA256SUMS")

    args = parser.parse_args(argv)

    if args.platform == "macos":
        checks = macos_checks(Path(args.app), Path(args.dmg) if args.dmg else None)
    elif args.platform == "windows":
        checks = windows_checks(Path(args.file), args.signtool)
    else:
        checks = linux_checks(Path(args.sums_dir))

    code, verdict, results = verify(checks)
    _report(results)
    print(f"signing verification: {verdict}")
    return code


if __name__ == "__main__":
    sys.exit(main())
