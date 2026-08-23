"""Every bundled example builds and verifies against the *real* toolchain.

The unit half (``tests/unit/test_examples.py``) proves each example parses and
has a summary; this is the half that catches the failure mode the unit layer
cannot: an example whose YAML looks right but whose emitted Verilog Yosys
rejects, or whose synthesis produces an empty BOM, or whose verification does
not close.

Each test parametrises over ``gatepack.examples.list_examples()`` — never a
hand-written list — so a future example is exercised the moment it lands, and
a broken one fails here instead of shipping. It skips cleanly when the
toolchain container is unavailable, exactly like the other ``tests/toolchain``
modules.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from gatepack.examples import list_examples
from tests.toolchain.docker_runner import IMAGE, run_repo

LIBRARY = "libraries/74aup.csv"

REPO = Path(__file__).resolve().parents[2]


def _timing_model(name: str) -> str:
    text = (REPO / "examples" / name / "design.yaml").read_text()
    for line in text.splitlines():
        if line.strip().startswith("timing_model:"):
            return line.split("timing_model:")[1].strip()
    return "synchronous"


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


def _example_names() -> list[str]:
    return [e.name for e in list_examples()]


def _run(*argv: str) -> subprocess.CompletedProcess[str]:
    # As the invoking user, not root: the container writes into the developer's
    # own checkout, and a root-owned `.gpout`/`build` left behind makes the next
    # *local* run fail with EACCES.  `run_repo` supplies that `-u` flag centrally.
    return run_repo("python3", "-m", "gatepack", *argv, timeout=600)


@requires_toolchain
@pytest.mark.parametrize("name", _example_names())
def test_every_example_builds(name: str) -> None:
    proc = _run(
        "build", f"examples/{name}/design.yaml",
        "--library", LIBRARY,
        "--out", f".gpout/examples-check/{name}",
        "--json",
    )
    assert proc.returncode == 0, (
        f"build failed for {name}:\n{proc.stderr or proc.stdout}"
    )
    envelope = json.loads(proc.stdout)
    assert envelope["ok"] is True
    assert envelope["data"]["packageCount"] >= 1, (
        f"{name}: build succeeded but produced an empty BOM (0 packages)"
    )


@requires_toolchain
@pytest.mark.parametrize("name", _example_names())
def test_every_example_builds_with_its_own_project_library(name: str) -> None:
    """The path the *app* takes: build against the project's own parts.csv.

    Building against `libraries/74aup.csv` proves the design synthesises; it
    does not prove the example works when opened in the GUI, which passes
    `<project>/parts.csv` instead. The two differ — a project library with no
    `parts.refs.md` beside it has no packaging citations, so the multi-gate
    parts read as unverified and the build is refused. That refusal is correct;
    an example that trips it is not shippable.
    """
    proc = _run(
        "build", f"examples/{name}/design.yaml",
        "--library", f"examples/{name}/parts.csv",
        "--out", f".gpout/examples-project-check/{name}",
        "--json",
    )
    assert proc.returncode == 0, (
        f"build with the project's own library failed for {name} — this is the "
        f"path the GUI takes:\n{proc.stderr or proc.stdout}"
    )
    envelope = json.loads(proc.stdout)
    assert envelope["ok"] is True
    assert envelope["data"]["packageCount"] >= 1, (
        f"{name}: built from its own library but produced an empty BOM"
    )


@requires_toolchain
@pytest.mark.parametrize("name", _example_names())
def test_every_example_verifies(name: str) -> None:
    proc = _run(
        "verify", f"examples/{name}/design.yaml",
        "--library", LIBRARY,
    )
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, f"verify failed for {name}:\n{combined}"
    # A verification that leaves any check "not run" is not a pass (§14); the
    # built-in verify reports that status verbatim, so assert it is absent.
    assert "not run" not in combined, combined
    if _timing_model(name) == "asynchronous":
        # The asynchronous path verifies via the two hazard checks, each its own
        # check; equivalence is not-applicable (no synchronous golden netlist).
        assert "hazard (ternary)" in combined, combined
        assert "hazard (glitch sim)" in combined, combined
        assert "equivalence:" in combined, combined
    else:
        assert "equivalence:               passed" in combined, combined
