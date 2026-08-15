"""Tests that run the emitted artefacts through the *real* toolchain.

These exist because of the failure this project has already hit once: 219 tests
passed while `gatepack compile` emitted Verilog that Yosys rejected outright.
Every test above this layer checks what the front-end *says*; only these check
that a real tool will accept it.

They skip cleanly when the toolchain container is unavailable — never faked,
never silently passed.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from gatepack.frontend import compile_design_file

DESIGNS = Path(__file__).resolve().parents[1] / "golden" / "designs"
IMAGE = "gatepack-toolchain:m6"


def _toolchain_available() -> bool:
    if shutil.which("docker") is None:
        return False
    probe = subprocess.run(
        ["docker", "image", "inspect", IMAGE],
        capture_output=True,
        text=True,
    )
    return probe.returncode == 0


requires_toolchain = pytest.mark.skipif(
    not _toolchain_available(),
    reason=f"toolchain image {IMAGE} not available; see Dockerfile.probe",
)


def _run_yosys(workdir: Path, script: str) -> subprocess.CompletedProcess[str]:
    (workdir / "probe.ys").write_text(script)
    return subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{workdir}:/work",
            IMAGE,
            "bash", "-c", "cd /work && yosys -q probe.ys",
        ],
        capture_output=True,
        text=True,
    )


@requires_toolchain
@pytest.mark.parametrize("design", ["traffic_light", "xor2", "decoder_3to8"])
def test_generated_verilog_is_accepted_by_yosys(design: str, tmp_path: Path) -> None:
    """The emitted behavioural Verilog must actually parse and elaborate."""
    result = compile_design_file(DESIGNS / f"{design}.yaml")
    (tmp_path / "generated.v").write_text(result.verilog)

    proc = _run_yosys(
        tmp_path,
        f"read_verilog -sv generated.v\n"
        f"hierarchy -check -top {design}\n"
        f"proc; opt\n",
    )
    assert proc.returncode == 0, (
        f"Yosys rejected the generated Verilog for {design}:\n"
        f"{proc.stderr or proc.stdout}"
    )


@requires_toolchain
def test_properties_file_is_accepted_by_yosys(tmp_path: Path) -> None:
    """The emitted properties must parse under `read_verilog -formal`.

    M6-FINDINGS §1: open-source Yosys does not implement SVA concurrent
    assertions — `assert property (@(posedge clk) ...)` is a syntax error, and
    that path requires the commercial Verific front end. Assertions must be
    emitted as immediate assertions inside a clocked `always` block.

    This is the check that distinguishes "we emit assertions" from "the prover
    can read our assertions".
    """
    design = DESIGNS / "property_violating.yaml"
    if not design.exists():  # pragma: no cover - golden set changed
        pytest.skip("no golden design carrying a properties block")

    result = compile_design_file(design)
    if not result.properties or not result.properties.strip():
        pytest.skip("golden design emitted no properties")

    (tmp_path / "generated.v").write_text(result.verilog)
    (tmp_path / "properties.sv").write_text(result.properties)

    proc = _run_yosys(
        tmp_path,
        "read_verilog -sv -formal generated.v properties.sv\n"
        "prep -top property_violating\n",
    )
    assert proc.returncode == 0, (
        "Yosys rejected the emitted properties file. If the error is "
        "`syntax error, unexpected '@'`, the emitter is producing SVA "
        "concurrent assertions, which open-source Yosys cannot parse — see "
        f"docs/M6-FINDINGS.md §1.\n{proc.stderr or proc.stdout}"
    )
