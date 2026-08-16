"""`estimate` vs `build` on the goldens (§6 verdict, §C5 packing).

The §6 verdict is what an engineer commits to a design on, so the number it
classifies must be the number the board ends up with.  ``estimate`` used to
count *mapped cells* as its ``packageCount`` while ``build`` counted *packed
packages*: with a one-gate-per-package library the two coincided and the gap was
invisible, and once the library gained multi-gate parts (M9) they diverged —
measured on the pelican showcase, ``estimate`` said 23 where ``build`` said 20.

``estimate`` now runs the same packer, so this is the agreement check.  It runs
the real toolchain against the real showcase, which is the only place the two
numbers can be compared honestly.

A second, separate defect is pinned here too: ``estimate`` ran Yosys with
``cwd=build_dir.parent``, which is correct only for a single-segment build dir.
For a nested ``--build a/b/c`` it made Yosys look for ``a/b/a/b/c/generated.v``,
fail, and leave ``packageCount`` as a silent ``None`` — no error, no zeros, just
an absence that reads like "unknown" beside a verdict computed without it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
IMAGE = "gatepack-toolchain:m6"
DESIGN = "examples/pelican/design.yaml"
LIBRARY = "libraries/74aup.csv"


def _toolchain_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(
        ["docker", "image", "inspect", IMAGE], capture_output=True
    ).returncode == 0


requires_toolchain = pytest.mark.skipif(
    not _toolchain_available(),
    reason=f"toolchain image {IMAGE} not available; see Dockerfile.probe",
)


def _run(*argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "docker", "run", "--rm", "-v", f"{REPO}:/repo", "-w", "/repo", IMAGE,
            "python3", "-m", "gatepack", *argv,
        ],
        capture_output=True,
        text=True,
    )


def _build_package_count(out: str) -> int:
    # The shipped library's multi-gate parts are placeholder data, so `build`
    # refuses them by default; these tests measure packing, not the data gate,
    # so they acknowledge the unverified gates-per-package explicitly.
    proc = subprocess.run(
        [
            "docker", "run", "--rm", "-v", f"{REPO}:/repo", "-w", "/repo", IMAGE,
            "python3", "-c",
            "from gatepack.build import run_build; "
            f"r, _ = run_build({DESIGN!r}, {LIBRARY!r}, out_dir={out!r}, "
            "allow_unverified_gates_per_pkg=True); "
            "print(r.packed_stats.package_count)",
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    return int(proc.stdout.strip())


def _rm(*paths: str) -> None:
    subprocess.run(
        ["docker", "run", "--rm", "-v", f"{REPO}:/repo", "-w", "/repo", IMAGE,
         "rm", "-rf", *paths],
        capture_output=True,
        text=True,
    )


def _data(proc: subprocess.CompletedProcess) -> dict:
    assert proc.returncode == 0, proc.stderr or proc.stdout
    return json.loads(proc.stdout)["data"]


@requires_toolchain
def test_estimate_package_count_agrees_with_build():
    est_dir = "dv_est_showcase"
    out_dir = ".gpout/est_build_showcase"
    try:
        est = _data(_run("estimate", DESIGN, "--library", LIBRARY, "--build", est_dir, "--json"))
        build_packages = _build_package_count(out_dir)
    finally:
        _rm(est_dir, out_dir)

    estimate_packages = est["packageCount"]

    assert build_packages > 0
    assert estimate_packages == build_packages, (
        "estimate's packageCount must be the number build produces; a verdict "
        "over the gate count is a verdict over the wrong number"
    )

    # And it must be the *packed* number, not the gate count that happens to
    # equal it for a single-gate library — the showcase maps 23 cells into 20
    # packages, so agreement here is only possible if the packer ran.
    assert build_packages < sum(est["cellCounts"].values())

    assert est["verdict"] in ("green", "amber", "red")


@requires_toolchain
def test_estimate_nested_build_dir_silently_reports_none():
    """A nested ``--build`` path must produce the same number as a flat one.

    This fails if the `cwd` override comes back: Yosys then resolves the
    script's relative paths one level too deep, fails, and `packageCount`
    becomes `None` with no error and exit 0.
    """
    nested = ".gpout/a/b/est_nested"
    flat = "dv_est_flat"
    try:
        deep = _data(_run("estimate", DESIGN, "--library", LIBRARY, "--build", nested, "--json"))
        shallow = _data(_run("estimate", DESIGN, "--library", LIBRARY, "--build", flat, "--json"))
    finally:
        _rm(".gpout/a", flat)

    assert deep["packageCount"] is not None, "nested --build silently lost the count"
    assert deep["packageCount"] == shallow["packageCount"]
