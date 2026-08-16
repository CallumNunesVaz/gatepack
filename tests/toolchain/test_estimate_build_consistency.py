"""`estimate` vs `build` on the goldens (§6 verdict, §C5 packing).

The §6 verdict is what an engineer commits to a design on, so the number it
classifies must be the number the board ends up with.  ``estimate`` counts
*mapped cells* as its ``packageCount``; ``build`` counts *packed packages*.  With
a one-gate-per-package library the two coincide and the gap was invisible; since
the library gained multi-gate parts (M9) they diverge.

Measured on the pelican showcase (``libraries/74aup.csv``):

* ``estimate`` reports ``packageCount`` = 23 (mapped cells);
* ``build`` reports ``packageCount`` = 20 (packed packages, 3 spare gates).

The verdict classifies the 23, not the 20 — both happen to be in the green band
(<= 25) here, so no verdict flips, but a design near the boundary would get a
"green, ~24 packages" verdict and build to fewer, or an "amber" verdict for a
board that is comfortably green.  This is the finding the task asks to report:
``estimate`` does not model multi-gate packing at all.

A second, separate defect is also pinned: ``estimate`` runs Yosys with
``cwd=build_dir.parent``, so a nested ``--build`` path makes Yosys fail silently
and ``packageCount`` becomes ``None`` — no error, no zeros, just an absence that
reads like "unknown" beside a verdict that was computed without it.
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
def test_estimate_package_count_diverges_from_build():
    # `estimate` needs a single-segment build dir (see the cwd defect below), so
    # use `dv_est_showcase` at the repo root; `build` is happy with any path.
    est_dir = "dv_est_showcase"
    out_dir = ".gpout/est_build_showcase"
    try:
        est = _data(_run("estimate", DESIGN, "--library", LIBRARY, "--build", est_dir, "--json"))
        bld = _data(_run("build", DESIGN, "--library", LIBRARY, "--out", out_dir, "--json"))
    finally:
        _rm(est_dir, out_dir)

    estimate_packages = est["packageCount"]
    build_packages = bld["packageCount"]

    # Packing can only reduce or leave the count unchanged, so this invariant
    # must hold for every design.  The *finding* is that they are not equal for
    # the showcase: estimate counts 23 mapped cells, build packs them to 20.
    assert estimate_packages >= build_packages
    assert estimate_packages != build_packages, (
        "estimate packageCount == build packageCount for the showcase. If "
        "`estimate` now models multi-gate packing, this test becomes the "
        "agreement check it was meant to be and this assertion should be "
        "flipped to equality."
    )

    # The estimate verdict classifies estimate_packages, not build_packages.
    # Both are in the green band (<= 25) here, so the verdict is unchanged —
    # but it is a verdict over the wrong number.
    assert est["verdict"] in ("green", "amber", "red")
    assert 0 < build_packages < estimate_packages


@requires_toolchain
def test_estimate_nested_build_dir_silently_reports_none():
    """The second defect: a nested ``--build`` path makes estimate's Yosys run
    fail silently (its ``cwd=build_dir.parent`` resolves the script's relative
    paths one level too deep), so ``packageCount`` is ``None`` with no error."""
    nested = ".gpout/est_nested"
    try:
        proc = _run("estimate", DESIGN, "--library", LIBRARY, "--build", nested, "--json")
        data = json.loads(proc.stdout)["data"]
        # the command itself succeeds (exit 0) while the number is silently absent
        assert proc.returncode == 0
        assert data["packageCount"] is None
    finally:
        _rm(nested)
