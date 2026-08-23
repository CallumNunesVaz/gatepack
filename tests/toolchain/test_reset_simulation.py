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


# --- DFF_SR set-path family ---------------------------------------------------
#
# ``down_counter`` is the first bundled example to instantiate ``DFF_SR``: its
# initial state D3 has binary code 3 (2'b11), so both state bits preset to 1 on
# reset and Yosys reaches for the set-and-reset flop (the set-only ``DFF_S`` is
# single-sourced and excluded from the library, so ``$_DFFSR_PNN_`` is the only
# legal flop that can preset).  That is what makes the set-path mutations
# *applicable* at all; before this example they reported ``not_applicable`` on
# every design and measured nothing.
_SET_FAMILY = (
    "set_never_asserts",
    "set_becomes_synchronous",
    "set_value_flips",
)


def _mutation_state(stdout: str, name: str) -> str | None:
    """The rendered verdict for ``name`` (e.g. ``"detected"``), padding-insensitive."""
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith(f"mutation {name}:"):
            return stripped.split(":", 1)[1].strip()
    return None


@requires_toolchain
def test_set_mutations_detected_on_down_counter() -> None:
    build = ".gpout/set_detected"
    try:
        proc = run_repo(
            "python3", "-m", "gatepack", "verify",
            "examples/down_counter/design.yaml",
            "--library", "libraries/74aup.csv",
            "--build", build,
        )
        combined = proc.stdout + proc.stderr
        assert proc.returncode == 0, combined
        for name in _SET_FAMILY:
            assert _mutation_state(proc.stdout, name) == "detected", combined
    finally:
        run_repo("rm", "-rf", build)


@requires_toolchain
def test_set_mutations_not_applicable_on_dff_r_only_design() -> None:
    """A design with no ``DFF_SR`` must report the set mutations as
    ``not applicable``, never "NOT DETECTED" — that rendering confusion was a
    real defect once (M5, defect 3).  ``sequence_detector`` is one-hot and uses
    only ``DFF_R``.
    """
    build = ".gpout/set_not_applicable"
    try:
        proc = run_repo(
            "python3", "-m", "gatepack", "verify",
            "examples/sequence_detector/design.yaml",
            "--library", "libraries/74aup.csv",
            "--build", build,
        )
        combined = proc.stdout + proc.stderr
        assert proc.returncode == 0, combined
        for name in _SET_FAMILY:
            assert _mutation_state(proc.stdout, name) == "not applicable", combined
        assert "NOT DETECTED" not in proc.stdout, combined
    finally:
        run_repo("rm", "-rf", build)


@requires_toolchain
def test_the_set_family_are_three_distinct_faults() -> None:
    """Each set mutation must be a *different* fault, not a renamed one.

    Runs the three set mutations against ``down_counter`` and requires three
    distinct failure traces.  ``set_becomes_synchronous`` must fail only the
    async-assert check ("during reset") and *not* the held-edge check, because a
    synchronous set does preset on the held edge; the other two fail both.  The
    two remaining are separated by their step lines: ``set_never_asserts``
    leaves the state at ``x`` (no set at all), while ``set_value_flips`` presets
    to the wrong *determinate* code and fails with numeric step values.
    """
    work = REPO / ".gpout" / "set_family"
    try:
        work.mkdir(parents=True, exist_ok=True)
        rel = work.relative_to(REPO)
        built = run_repo(
            "python3", "-m", "gatepack", "verify",
            "examples/down_counter/design.yaml",
            "--library", "libraries/74aup.csv",
            "--build", f"{rel}/b",
        )
        assert built.returncode == 0, built.stdout + built.stderr

        build = work / "b"
        sim0 = (build / "cells_sim.v").read_text()
        lib0 = (build / "cells.lib").read_text()
        by_name = {m.name: m for m in mutation.MUTATIONS}

        traces: dict[str, frozenset[str]] = {}
        for name in _SET_FAMILY:
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

        assert len(set(traces.values())) == len(_SET_FAMILY), (
            "set mutations collapsed into the same fault: "
            + repr({k: sorted(v) for k, v in traces.items()})
        )

        held = "FAIL: c1 held in reset"
        assert held in traces["set_never_asserts"], sorted(traces["set_never_asserts"])
        assert held in traces["set_value_flips"], sorted(traces["set_value_flips"])
        assert held not in traces["set_becomes_synchronous"], sorted(
            traces["set_becomes_synchronous"]
        )

        # The two that do fail the held-edge check are still distinct: only the
        # never-asserts fault leaves the state at x (no set at all); the value
        # flip presets to a wrong *determinate* code.
        assert "FAIL: c1 at step x" in traces["set_never_asserts"]
        assert "FAIL: c1 at step x" not in traces["set_value_flips"]
    finally:
        run_repo("rm", "-rf", str(work.relative_to(REPO)))
