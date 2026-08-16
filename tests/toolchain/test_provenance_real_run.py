"""Provenance coverage from a *real* synthesis run (M11b).

The golden fixtures under ``tests/fixtures/provenance/`` are real ``write_json``
output, but a fixture can drift from the live toolchain without anyone noticing
— the failure mode this project has already hit four times.  This test runs the
full ``gatepack build`` inside the pinned toolchain, regenerates the post-``abc``
capture, measures coverage with the same function the report generator and the
golden layer use, and asserts the numbers have not drifted.

It also asserts the post-``abc`` recovery is honest: the six opt_clean-dropped
nets come back as ``inferred``, never promoted to ``exact``, and the weak axis
is named (2 of 5 transitions exact on the traffic light).

Skips cleanly when the toolchain container is unavailable — never faked.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from gatepack.provenance.capture import read_netlist_json
from gatepack.provenance.coverage import CoverageReport, measure_coverage

REPO = Path(__file__).resolve().parents[2]
IMAGE = "gatepack-toolchain:m6"

GOLDEN_DESIGNS = REPO / "tests" / "golden" / "designs"
FIXTURES = REPO / "tests" / "fixtures" / "provenance"


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


def _run(command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{REPO}:/repo", "-w", "/repo", IMAGE,
            "bash", "-c", command,
        ],
        capture_output=True,
        text=True,
    )


def _build_and_measure(design: str, design_path: str) -> tuple[str, CoverageReport, CoverageReport]:
    """Build ``design``, add the post-abc capture, and measure coverage twice.

    Returns ``(out_dir, without_post_abc, with_post_abc)``.
    """
    out = f".gpout/prov_{design}"
    proc = _run(
        "python3 -c "
        f"\"from gatepack.build import run_build; "
        f"run_build('{design_path}', 'libraries/74aup.csv', out_dir='{out}', "
        f"allow_unverified_gates_per_pkg=True)\""
    )
    assert proc.returncode == 0, f"build failed for {design}:\n{proc.stderr or proc.stdout}"

    # Re-generate the post-abc, pre-opt_clean capture by inserting a write_json
    # immediately before `clean` and re-running the same script Yosys already ran.
    patch = (
        "import pathlib; "
        f"p = pathlib.Path('{out}/yosys.ys'); "
        f"t = p.read_text(); "
        f"p.write_text(t.replace('clean\\n', 'write_json {out}/post_abc.json  # M11b\\nclean\\n'))"
    )
    run_ys = _run(
        f"python3 -c \"{patch}\" && yosys -q -p \"$(cat {out}/yosys.ys)\""
    )
    assert run_ys.returncode == 0, (
        f"post-abc re-run failed for {design}:\n{run_ys.stderr or run_ys.stdout}"
    )

    premap = read_netlist_json(REPO / out / "premap.json")
    mapped = read_netlist_json(REPO / out / "mapped.json")
    post_abc = read_netlist_json(REPO / out / "post_abc.json")

    without = measure_coverage(premap, mapped)
    with_post = measure_coverage(premap, mapped, post_abc=post_abc)
    return out, without, with_post


def _fixture_report(design: str, *, post_abc: bool) -> CoverageReport:
    premap = read_netlist_json(FIXTURES / design / "premap.json")
    mapped = read_netlist_json(FIXTURES / design / "mapped.json")
    pa = read_netlist_json(FIXTURES / design / "post_abc.json") if post_abc else None
    return measure_coverage(premap, mapped, post_abc=pa)


def _assert_same_report(a: CoverageReport, b: CoverageReport, design: str) -> None:
    assert a.net == b.net, f"{design}: net carrier drifted: live {a.net} vs fixture {b.net}"
    assert a.cell == b.cell, f"{design}: cell carrier drifted"
    for kind, ka in a.by_kind.items():
        kb = b.by_kind.get(kind)
        assert kb is not None, f"{design}: kind {kind} missing from fixture"
        assert ka == kb, f"{design}: kind {kind} drifted: live {ka} vs fixture {kb}"
    assert abs(a.coverage - b.coverage) < 1e-9, (
        f"{design}: aggregate coverage drifted: {a.coverage} vs {b.coverage}"
    )


@requires_toolchain
@pytest.mark.parametrize(
    ("design", "path"),
    [
        ("traffic_light", "tests/golden/designs/traffic_light.yaml"),
        ("pelican", "examples/pelican/design.yaml"),
    ],
)
def test_real_run_matches_committed_fixtures(design: str, path: str) -> None:
    _, without, with_post = _build_and_measure(design, path)
    _assert_same_report(without, _fixture_report(design, post_abc=False), design)
    _assert_same_report(with_post, _fixture_report(design, post_abc=True), design)


@requires_toolchain
def test_real_run_reports_the_m0_finding() -> None:
    """16 of 22 nets exact, but only 2 of 5 transitions — and it is named."""
    _, without, _ = _build_and_measure("traffic_light", "tests/golden/designs/traffic_light.yaml")
    assert without.net.total == 22
    assert without.net.exact == 16
    assert without.net.absent == 6

    transitions = without.by_kind["transitions"]
    assert transitions.total == 5
    assert transitions.exact == 2
    assert transitions.absent == 3
    assert transitions.unlinked == (
        "transitions[0]",
        "transitions[1]",
        "transitions[3]",
    )

    # output logic and inputs stay fully exact — the weak axis is transitions
    assert without.by_kind["output_logic"].exact == without.by_kind["output_logic"].total
    assert without.by_kind["inputs"].exact == without.by_kind["inputs"].total


@requires_toolchain
def test_post_abc_recovery_is_inferred_never_exact() -> None:
    _, without, with_post = _build_and_measure("traffic_light", "tests/golden/designs/traffic_light.yaml")
    # the six dropped nets become inferred, and the exact count does not move
    assert with_post.net.exact == without.net.exact == 16
    assert with_post.net.inferred == 6
    assert with_post.net.absent == 0
    # the transitions recovered from the post-abc capture are inferred, not exact
    transitions = with_post.by_kind["transitions"]
    assert transitions.exact == 2
    assert transitions.inferred == 3
    # no entry is present-but-empty, and none is inflated to exact
    for entry in with_post.entries:
        assert entry.nets or entry.cells
