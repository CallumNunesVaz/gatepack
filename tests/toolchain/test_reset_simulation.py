"""The reset-assertion phase is *verified*, not just emitted — real toolchain.

The unit layer proves the testbench contains reset-assert probes and that the
reference model computes the emitter's reset value.  This layer proves the two
things that only a real Yosys + Icarus run can:

1. ``gatepack verify`` on ``sequence_detector`` now reports ``reset_polarity_flip``
   as **detected** — the fault flips the ``DFF_R`` clear condition, so the state
   does not clear on reset, and the new stimulus catches the stuck ``match``
   output during reset (previously the simulation treated reset as a §9.6 setup
   step and never looked, so the fault was "caught by equivalence only").

2. The **falsification**: running the exhaustive simulation against a
   hand-mutated ``cells_sim.v`` genuinely fails, with the reset-phase mismatch
   message — not by virtue of the verdict logic, but because Icarus observes the
   stuck output.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from gatepack.frontend import compile_design_file
from gatepack.verify import mutation, simulation
from gatepack.verify.base import VerifyConfig
from tests.toolchain.docker_runner import IMAGE, run_repo

REPO = Path(__file__).resolve().parents[2]


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


def _verify(build: str) -> subprocess.CompletedProcess[str]:
    return run_repo(
        "python3", "-m", "gatepack", "verify",
        "examples/sequence_detector/design.yaml",
        "--library", "examples/sequence_detector/parts.csv",
        "--build", build,
    )


@requires_toolchain
def test_reset_polarity_flip_is_detected() -> None:
    build = ".gpout/reset_detected"
    try:
        proc = _verify(build)
        combined = proc.stdout + proc.stderr
        assert proc.returncode == 0, combined
        assert "mutation reset_polarity_flip: detected" in proc.stdout, combined
        # nand_to_and is a *different* case: genuinely unobservable at any
        # output, so it must stay "caught by equivalence only", not flip to
        # detected (the brief's canary for over-eager stimulus).
        assert "mutation nand_to_and:      caught by equivalence only" in proc.stdout, combined
    finally:
        run_repo("rm", "-rf", build)


@requires_toolchain
def test_mutated_reset_fails_exhaustive_simulation() -> None:
    """The new stimulus catches a reset fault; the reference model does not.

    The mutated ``cells_sim.v`` (reset polarity flipped) leaves ``match`` high
    while reset is asserted from S3, so the reset-assert probe fails.  The
    reference model still computes ``match = 0`` during reset, which is the
    whole point: it is derived from the emitter, not from the mutated model.
    """
    build = ".gpout/reset_falsified"
    try:
        proc = _verify(build)
        assert proc.returncode == 0, proc.stderr or proc.stdout

        sim_path = REPO / build / "cells_sim.v"
        sim_text = sim_path.read_text()
        # The reset_polarity_flip transform, applied to the sim model only.
        _lib, mutated_sim = mutation._reset_polarity_flip("", sim_text)
        assert mutated_sim != sim_text
        sim_path.write_text(mutated_sim)

        compiled = compile_design_file(
            REPO / "examples" / "sequence_detector" / "design.yaml"
        ).compiled
        tb = simulation.build_testbench(compiled, VerifyConfig(top="sequence_detector"))
        (REPO / build / "exhaustive_tb.v").write_text(tb)

        compiled_ok = run_repo(
            "bash", "-c",
            f"iverilog -o {build}/tb.vvp {build}/mapped.v {build}/cells_sim.v "
            f"{build}/exhaustive_tb.v",
        )
        assert compiled_ok.returncode == 0, compiled_ok.stderr or compiled_ok.stdout

        ran = run_repo("bash", "-c", f"vvp {build}/tb.vvp")
        combined = ran.stdout + ran.stderr
        assert "EXHAUSTIVE_SIM_FAIL" in combined, (
            "the mutated reset was NOT caught by the exhaustive simulation:\n" + combined
        )
        assert "during reset" in combined, (
            "the failure did not come from the reset-assert probe:\n" + combined
        )
    finally:
        run_repo("rm", "-rf", build)


# The §9.3 default puts a two-flop synchroniser between the reset pin and the
# state flops, and on that topology every reset fault degenerates to the same
# observable behaviour — measured: all four reset mutations produce byte-identical
# Icarus traces on all six bundled examples.  This design takes the raw pin
# (`sync_deassert: false`) and moves into its output-true state on the next edge,
# which is what makes the reset family separable at all.
_HOLD_PROBE = """name: holdprobe
timing_model: synchronous
clock: {signal: clk, freq_hz: 1000, source: OSC}
reset: {signal: rst_n, active: low, sync_deassert: false, source: SUPERVISOR}
encoding: one_hot
inputs:
  - {name: go, sync: false}
outputs:
  - {name: o}
states: [A, B]
initial: A
transitions:
  - {from: A, to: B, when: "1"}
  - {from: B, to: A, when: "1"}
output_logic:
  o: "state == B"
"""

_RESET_FAMILY = (
    "reset_polarity_flip",
    "reset_never_asserts",
    "reset_becomes_synchronous",
    "reset_value_flips",
)


def _fail_lines(text: str) -> frozenset[str]:
    return frozenset(l for l in text.splitlines() if l.startswith("FAIL"))


@requires_toolchain
def test_the_reset_family_are_four_distinct_faults() -> None:
    """Each reset mutation must be a *different* fault, not a renamed one.

    A mutation suite that grows without gaining discrimination costs runtime and
    buys nothing.  This runs all four reset mutations against one design and
    requires four distinct failure traces — in particular that
    ``reset_becomes_synchronous`` does **not** fail the reset-hold check (a
    synchronous reset clears on the held edge) while ``reset_never_asserts``
    does (an absent reset takes ``D``).  That single line is what separates
    them; drop the held-edge check and these two collapse into one fault.
    """
    work = REPO / ".gpout" / "reset_family"
    try:
        work.mkdir(parents=True, exist_ok=True)
        (work / "design.yaml").write_text(_HOLD_PROBE)
        rel = work.relative_to(REPO)
        built = run_repo(
            "python3", "-m", "gatepack", "verify", f"{rel}/design.yaml",
            "--library", "libraries/74aup.csv", "--build", f"{rel}/b",
        )
        assert built.returncode == 0, built.stdout + built.stderr

        build = work / "b"
        sim0 = (build / "cells_sim.v").read_text()
        lib0 = (build / "cells.lib").read_text()
        by_name = {m.name: m for m in mutation.MUTATIONS}

        traces: dict[str, frozenset[str]] = {}
        for name in _RESET_FAMILY:
            _lib, mutated = by_name[name].mutate(lib0, sim0)
            assert mutated != sim0, f"{name} did not change cells_sim.v"
            (build / "cells_sim.v").write_text(mutated)
            compiled_ok = run_repo(
                "bash", "-c",
                f"iverilog -o {rel}/b/t.vvp {rel}/b/mapped.v {rel}/b/cells_sim.v "
                f"{rel}/b/exhaustive_tb.v",
            )
            assert compiled_ok.returncode == 0, compiled_ok.stderr or compiled_ok.stdout
            ran = run_repo("bash", "-c", f"vvp {rel}/b/t.vvp")
            traces[name] = _fail_lines(ran.stdout + ran.stderr)
            (build / "cells_sim.v").write_text(sim0)

        for name, lines in traces.items():
            assert lines, f"{name} was not caught by the simulation at all"

        assert len(set(traces.values())) == len(_RESET_FAMILY), (
            "reset mutations collapsed into the same fault: "
            + repr({k: sorted(v) for k, v in traces.items()})
        )

        held = "FAIL: o held in reset"
        assert held in traces["reset_never_asserts"], sorted(traces["reset_never_asserts"])
        assert held not in traces["reset_becomes_synchronous"], sorted(
            traces["reset_becomes_synchronous"]
        )
    finally:
        run_repo("rm", "-rf", str(work.relative_to(REPO)))
