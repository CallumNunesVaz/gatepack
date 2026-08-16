"""`gatepack build` against a real Yosys, at several output-path depths.

The bug this exists to catch: `_synthesize` ran Yosys with `cwd=out.parent`
while the generated script holds paths relative to the *invocation* directory.
`--out build` therefore worked and `--out x/y` did not — and the failure was
reported as "synthesis unavailable ... install yosys", blaming a missing tool
for a path bug while Yosys was installed and working.

Nothing caught it because every existing test used a single-segment output
path, and the unit layer drives a fake runner that has no working directory.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
IMAGE = "gatepack-toolchain:m6"


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


def _build(out: str) -> subprocess.CompletedProcess[str]:
    # Build through `run_build` with the unverified gates-per-package
    # acknowledgement, because the shipped library's multi-gate parts are all
    # placeholder data (§1.3) and the default gate refuses them.  These tests
    # exercise path handling and observability, not the data-verification gate.
    return subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{REPO}:/repo", "-w", "/repo", IMAGE,
            "python3", "-c",
            "from gatepack.build import run_build; "
            "run_build('examples/pelican/design.yaml', 'libraries/74aup.csv', "
            f"out_dir={out!r}, allow_unverified_gates_per_pkg=True); "
            "print('wrote')",
        ],
        capture_output=True,
        text=True,
    )


@requires_toolchain
@pytest.mark.parametrize(
    "out",
    [
        ".gpout/t_flat",
        ".gpout/t_nested/one",
        ".gpout/t_nested/one/two/three",
    ],
)
def test_build_succeeds_at_any_output_depth(out: str) -> None:
    proc = _build(out)
    assert proc.returncode == 0, (
        f"build failed for --out {out}:\n{proc.stderr or proc.stdout}"
    )
    assert "synthesis unavailable" not in (proc.stdout + proc.stderr)
    assert "wrote" in proc.stdout


@requires_toolchain
def test_missing_yosys_says_so_rather_than_blaming_something_else() -> None:
    """The refusal must name the real cause, not a generic unavailability.

    A message that says "install yosys" when yosys is installed sends the
    reader to the wrong place, which is how the path bug above survived.
    """
    proc = subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{REPO}:/repo", "-w", "/repo", IMAGE,
            "env", "PATH=/nonexistent", "/usr/bin/python3", "-m", "gatepack",
            "build", "examples/pelican/design.yaml",
            "--library", "libraries/74aup.csv", "--out", ".gpout/t_noyosys",
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    combined = proc.stdout + proc.stderr
    assert "yosys is not on PATH" in combined, combined
    # and it must still refuse rather than invent a netlist
    assert "never faked here" in combined


@requires_toolchain
def test_outputs_are_observable_on_a_real_netlist() -> None:
    """SCOAP must not call a design's own outputs unobservable.

    A bit can carry several net names, and C1 deliberately emits `<out>_int`
    intermediates to hold provenance. The parser's bit->name map was
    last-writer-wins, so cell connections resolved to `walk_int` while
    `netlist.outputs` held the port name `walk` — and every output-driving net
    came out unobservable. The report told the reader that all four of the
    showcase's outputs could not be observed, i.e. that the design was
    untestable.

    Only a real netlist has the alias pairs that trigger it; the hand-written
    fixtures do not.
    """
    out = ".gpout/t_observability"
    proc = _build(out)
    assert proc.returncode == 0, proc.stderr or proc.stdout

    report = subprocess.run(
        [
            "docker", "run", "--rm", "-v", f"{REPO}:/repo", "-w", "/repo", IMAGE,
            "cat", f"{out}/report.md",
        ],
        capture_output=True,
        text=True,
    ).stdout

    line = next(
        (ln for ln in report.splitlines() if ln.startswith("Unobservable nets")),
        "",
    )
    for output_net in ("walk", "traffic_red", "traffic_green", "traffic_amber"):
        assert output_net not in line, (
            f"{output_net!r} is a primary output and cannot be unobservable; "
            f"the bit->name resolution has regressed.\n{line}"
        )
