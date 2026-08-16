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


def _run_sby(workdir: Path, sby_file: str) -> subprocess.CompletedProcess[str]:
    """Run one generated `.sby` file against real sby in the toolchain image."""
    return subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{workdir}:/work",
            IMAGE,
            "bash", "-c", f"cd /work && sby -f {sby_file}",
        ],
        capture_output=True,
        text=True,
    )


def _discharge_properties(design: str, workdir: Path):
    """Run every property task for a design through real sby; return the checks."""
    from gatepack.verify import properties as props

    result = compile_design_file(DESIGNS / f"{design}.yaml")
    compiled = result.compiled
    build = workdir / "build"
    build.mkdir(parents=True, exist_ok=True)
    (build / "generated.v").write_text(result.verilog)
    (build / "properties.sv").write_text(result.properties)

    tasks = props.property_tasks(compiled)
    results: dict[str, props.TaskResult] = {}
    for task in tasks:
        name = f"properties_{task.label}.sby"
        (build / name).write_text(
            props.build_sby_file(
                compiled.design.name, "build/generated.v", "build/properties.sv", task
            )
        )
        proc = _run_sby(workdir, f"build/{name}")
        assert proc.returncode in (0, 2), (
            f"sby rejected the generated task {name} (rc={proc.returncode}):\n"
            f"{proc.stdout}\n{proc.stderr}"
        )
        results.update(props.parse_sby(proc.stdout, [task]))
    return props.checks_from_sby(compiled, tasks, results)


@requires_toolchain
def test_properties_discharge_end_to_end(tmp_path: Path) -> None:
    """The generated `.sby` files must run against real sby, not just parse.

    This is the end-to-end discharge M6-FINDINGS never had: a correct mutex
    proves (PASSED with its antecedent reachable), and a vacuously-true mutex
    is reported as a FAILURE, never a pass.
    """
    from gatepack.verify.base import CheckStatus

    good = {c.name: c for c in _discharge_properties("traffic_light", tmp_path / "good")}
    assert good["property one_light_only"].status is CheckStatus.PASSED

    vacuous = {
        c.name: c for c in _discharge_properties("vacuous_mutex", tmp_path / "vacuous")
    }
    assert vacuous["property never_both"].status is CheckStatus.FAILED
    assert "vacuous" in vacuous["property never_both"].detail


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
@pytest.mark.parametrize(
    "design",
    ["property_violating", "traffic_light", "liveness", "liveness_violating", "vacuous_mutex"],
)
def test_properties_file_is_accepted_by_yosys(design: str, tmp_path: Path) -> None:
    """The emitted properties must parse under `read_verilog -formal`.

    M6-FINDINGS §1: open-source Yosys does not implement SVA concurrent
    assertions — `assert property (@(posedge clk) ...)` is a syntax error, and
    that path requires the commercial Verific front end. Assertions must be
    emitted as immediate assertions inside a clocked `always` block.

    This is the check that distinguishes "we emit assertions" from "the prover
    can read our assertions".
    """
    path = DESIGNS / f"{design}.yaml"
    if not path.exists():  # pragma: no cover - golden set changed
        pytest.skip("no golden design carrying a properties block")

    result = compile_design_file(path)
    if not result.properties or not result.properties.strip():
        pytest.skip("golden design emitted no properties")

    (tmp_path / "generated.v").write_text(result.verilog)
    (tmp_path / "properties.sv").write_text(result.properties)

    # properties.sv is `include`d into the design module under GP_FORMAL, so
    # only generated.v is read and the top is the design itself.  GP_PROVE and
    # GP_COVER select the assertion and cover statements respectively; both must
    # be defined here or the property body is compiled out and this test would
    # "pass" while checking nothing.
    proc = _run_yosys(
        tmp_path,
        "read_verilog -sv -formal -DGP_FORMAL -DGP_PROVE -DGP_COVER generated.v\n"
        f"prep -top {design}\n",
    )
    assert proc.returncode == 0, (
        "Yosys rejected the emitted properties file. If the error is "
        "`syntax error, unexpected '@'`, the emitter is producing SVA "
        "concurrent assertions, which open-source Yosys cannot parse — see "
        f"docs/M6-FINDINGS.md §1.\n{proc.stderr or proc.stdout}"
    )

    # M6-FINDINGS §6: a property over an undriven wire is the purest vacuous
    # pass there is. Yosys only *warns* about it, so the warning must be
    # treated as a hard failure here or the check silently means nothing.
    log = proc.stdout + proc.stderr
    for marker in ("implicitly declared", "used but has no driver"):
        assert marker not in log, (
            f"a property references a signal Yosys could not resolve ({marker!r}); "
            "the assertion would be checked against a free variable connected to "
            f"nothing - see docs/M6-FINDINGS.md §6.\n{log}"
        )
