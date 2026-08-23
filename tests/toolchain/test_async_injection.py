"""The functional check closes over the *real* toolchain: the injection fails.

Package L's acceptance criterion: with one z3-selected product term dropped from
the cover (a stage-4 bug's fingerprint), the asynchronous verification must
report a **failed** functional check and no netlist may be obtainable.  This runs
the injection probe inside ``gatepack-toolchain:m6`` (real z3 + Icarus) and
asserts exactly that, where before Package L the same probe shipped green.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from tests.toolchain.docker_runner import IMAGE, run_repo

PROBE = "tests/toolchain/_async_hazard_injection.py"


def _toolchain_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return (
        subprocess.run(
            ["docker", "image", "inspect", IMAGE], capture_output=True
        ).returncode
        == 0
    )


requires_toolchain = pytest.mark.skipif(
    not _toolchain_available(),
    reason=f"toolchain image {IMAGE} not available; see Dockerfile.probe",
)


@requires_toolchain
def test_injected_cube_fails_functional_check_and_gates_netlist():
    proc = run_repo("python3", PROBE, timeout=600)
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    import json

    out = json.loads(proc.stdout)
    control = dict(out["control_checks"])
    faulty = dict(out["faulty_checks"])

    # Control run is green and the new check passes by name.
    assert out["control_hazard_passed"] is True, control
    assert control["functional (fundamental mode)"] == "passed", control
    assert control["hazard (ternary)"] == "passed", control
    assert control["hazard (glitch sim)"] == "passed", control

    # The injection fired (a cube really was dropped)...
    assert out["injection_calls"] == 1
    assert out["cover_cubes_faulty"] != out["cover_cubes_clean"]

    # ...and the hazard checks still pass (hazards are not what the fault breaks)...
    assert faulty["hazard (ternary)"] == "passed", faulty
    assert faulty["hazard (glitch sim)"] == "passed", faulty

    # ...but the functional check fails, and the netlist is not obtainable.
    assert faulty["functional (fundamental mode)"] == "failed", faulty
    assert out["faulty_hazard_passed"] is False
    assert out["netlist_accessor"] == "HazardFailed", out
    assert "functional (fundamental mode)" in out.get("netlist_reason", "")
