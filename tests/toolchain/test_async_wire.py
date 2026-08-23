"""The asynchronous backend wired into the *real* CLI (z3 + Icarus, §7.3).

Where :mod:`test_async_hazard` proves the stages close under the toolchain, this
module proves the *wiring*: a user running ``gatepack verify`` on an async
design gets a real verdict, the specific refusal text survives the whole path,
and two clean builds of the async example are byte-identical (§5.5).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.toolchain.docker_runner import IMAGE, run_repo

LIBRARY = "libraries/74aup.csv"
EXAMPLE = "examples/async_latch/design.yaml"


def _toolchain_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return (
        subprocess.run(
            ["docker", "image", "inspect", IMAGE], capture_output=True, text=True
        ).returncode
        == 0
    )


requires_toolchain = pytest.mark.skipif(
    not _toolchain_available(),
    reason=f"toolchain image {IMAGE} not available; see Dockerfile.probe",
)


def _run(*argv: str) -> subprocess.CompletedProcess[str]:
    return run_repo("python3", "-m", "gatepack", *argv, timeout=600)


@requires_toolchain
def test_verify_async_example_is_green_and_reports_both_hazard_checks():
    proc = _run("verify", EXAMPLE, "--library", LIBRARY, "--build", ".gpout/async_wire/verify")
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, combined
    assert "verification: passed" in combined, combined
    assert re.search(r"hazard \(ternary\):\s+passed", combined), combined
    assert re.search(r"hazard \(glitch sim\):\s+passed", combined), combined
    assert re.search(r"functional \(fundamental mode\):\s+passed", combined), combined
    assert "not run" not in combined, combined


@requires_toolchain
def test_verify_refusals_name_the_construct_through_the_cli():
    for name, needle in (
        ("async_no_svc", "single-variable-change"),
        ("async_4literal", "a & b & c & d"),
        ("async_two_input", "simultaneously"),
    ):
        proc = _run(
            "verify", f"tests/golden/designs/{name}.yaml",
            "--library", LIBRARY, "--build", f".gpout/async_wire/{name}",
        )
        assert proc.returncode == 3, f"{name}: {proc.stdout}{proc.stderr}"
        assert needle in proc.stderr, f"{name}: {proc.stderr}"


@requires_toolchain
def test_async_build_emits_artefacts_and_reports_the_guarantee():
    proc = _run(
        "build", EXAMPLE, "--library", LIBRARY,
        "--out", ".gpout/async_wire/build",
    )
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, combined
    out = Path(".gpout/async_wire/build")
    for name in ("mapped.json", "mapped.v", "bom.csv", "netlist.net", "report.md"):
        assert (out / name).exists(), f"missing {name}"
    report = (out / "report.md").read_text()
    # §C8: the guarantee and its limits are stated every time.
    for needle in (
        "fundamental mode",
        "mutually exclusive",
        "product-term literal",
        "privileged-cube",
        "concurrent",
        "hazard (ternary)",
        "hazard (glitch sim)",
    ):
        assert needle in report, f"report missing {needle!r}"


@requires_toolchain
def test_two_async_builds_are_byte_identical():
    _ARTEFACTS = (
        "mapped.json", "mapped.v", "bom.csv", "netlist.net",
        "netlist.unpacked.net", "report.md", "refdes.json", "packed.json",
    )
    for n in ("a", "b"):
        proc = _run(
            "build", EXAMPLE, "--library", LIBRARY,
            "--out", f".gpout/async_wire/repro/{n}",
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
    base = Path(".gpout/async_wire/repro")
    for name in _ARTEFACTS:
        a = (base / "a" / name).read_bytes()
        b = (base / "b" / name).read_bytes()
        assert a == b, f"{name} differs between two clean builds"
