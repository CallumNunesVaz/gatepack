#!/usr/bin/env python3
"""Measure whether the packaged installers are byte-reproducible (§5.5).

``scripts/repro_check.py`` proves the *core* build is deterministic (netlist,
BOM, manifest).  This script measures the *packaging* layer: it runs
electron-builder twice into two output directories and compares every produced
file byte-for-byte.  The honest answer is expected to be "not reproducible" —
AppImage and deb embed the build date, and electron-builder stamps metadata —
but this script does not assume that either way; it measures it and names which
files differ.

The experiment holds the app build constant (``npm run build`` is run once; its
output is an input to electron-builder, and the question here is the installer,
not the renderer).  Two clean electron-builder runs then differ only in what the
packager itself produces.

This is a *report*, not a gate: it exits 0 in every case where it could run,
and prints an explicit verdict.  When electron-builder is unavailable it prints
``NOT MEASURED`` — never a fabricated "reproducible" and never an assumed
"not reproducible".
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
APP = REPO / "app"


def _npx_available() -> bool:
    try:
        proc = subprocess.run(
            ["npx", "--version"], capture_output=True, text=True, timeout=60
        )
        return proc.returncode == 0
    except FileNotFoundError:
        return False


def _run(cmd: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)


def _hash_tree(root: Path) -> dict[str, str]:
    """Map rel-path -> sha256 for every regular file under ``root``."""
    out: dict[str, str] = {}
    if not root.is_dir():
        return out
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def _compare(a: dict[str, str], b: dict[str, str]) -> dict:
    """Compare two rel-path -> sha256 maps. Pure, so the verdict is testable."""
    paths = sorted(set(a) | set(b))
    identical: list[str] = []
    differing: list[str] = []
    missing: list[str] = []
    for p in paths:
        x, y = a.get(p), b.get(p)
        if x is None or y is None:
            missing.append(p)
        elif x == y:
            identical.append(p)
        else:
            differing.append(p)
    return {
        "total": len(paths),
        "identical": identical,
        "differing": differing,
        "missing": missing,
    }


def measure(targets: list[str], output_root: Path, timeout: int) -> dict:
    """Build twice and compare. Returns a verdict dict (never raises)."""
    if not _npx_available():
        return {"measured": False, "reason": "electron-builder unavailable (npx not on PATH)"}

    build = _run(["npm", "run", "build"], APP, timeout)
    if build.returncode != 0:
        return {
            "measured": False,
            "reason": f"app build failed: {build.stdout}\n{build.stderr}",
        }

    output_root.mkdir(parents=True, exist_ok=True)
    runs: dict[str, dict[str, str]] = {}
    for label in ("a", "b"):
        out_dir = output_root / label
        argv = [
            "npx",
            "electron-builder",
            "--linux",
            *targets,
            f"--config.directories.output={out_dir}",
        ]
        proc = _run(argv, APP, timeout)
        if proc.returncode != 0:
            return {
                "measured": False,
                "reason": f"electron-builder failed ({label}):\n{proc.stdout}\n{proc.stderr}",
            }
        runs[label] = _hash_tree(out_dir)

    result = _compare(runs["a"], runs["b"])
    return {"measured": True, **result}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="measure whether the packaged installers are byte-reproducible"
    )
    parser.add_argument(
        "--targets",
        nargs="*",
        default=["dir", "AppImage", "deb"],
        help="electron-builder --linux targets (default: dir AppImage deb)",
    )
    parser.add_argument(
        "--output-root",
        default=str(REPO / ".gpout" / "repro-installer"),
        help="parent dir for the two build outputs (default: %(default)s)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=1800,
        help="per-build timeout in seconds (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    result = measure(args.targets, Path(args.output_root).resolve(), args.timeout)

    if not result["measured"]:
        print(f"installer reproducibility: NOT MEASURED ({result['reason']})")
        return 0

    total = result["total"]
    differing = result["differing"]
    identical = result["identical"]
    missing = result["missing"]

    for p in missing:
        print(f"missing from one run: {p}", file=sys.stderr)
    for p in differing:
        print(f"differs between builds: {p}", file=sys.stderr)

    if not differing and not missing:
        print(
            f"installer reproducibility: REPRODUCIBLE ({total} file(s) byte-identical)"
        )
    else:
        print(
            "installer reproducibility: NOT REPRODUCIBLE "
            f"({len(differing)} of {total} file(s) differ, {len(missing)} missing) "
            "- electron-builder embeds non-deterministic metadata (e.g. timestamps)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
