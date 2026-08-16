"""M-cell coverage (§9.4, M8, §19 R25) against the real toolchain.

Two things are established here, both of which the existing green suite does not
measure:

1. The M-cell behavioural model is genuinely *shared* between C4's equivalence
   and its exhaustive simulation (R25) — one ``CNT4.v`` under
   ``gatepack/macros/models/``, appended to ``cells_sim.v``, read by both checks.
2. A **deliberately wrong** M-cell model is caught.

The second is the finding.  The equivalence script reads ``cells_sim.v`` on *both*
the golden and the mapped side when a macro is a black box, so a wrong model
cancels itself out — mutation of ``CNT4.v`` changes both sides identically and
the equivalence check still reports "successfully proven".  The M-cell mutation
path is therefore **unverified**: R25's "one shared file" control satisfies only
the trivial no-drift half of the requirement, not the "a wrong model is caught"
half.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DESIGNS = REPO / "tests" / "golden" / "designs"
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


def _run_yosys(workdir: Path, script: str) -> subprocess.CompletedProcess[str]:
    (workdir / "probe.ys").write_text(script)
    return subprocess.run(
        [
            "docker", "run", "--rm", "-v", f"{workdir}:/work", IMAGE,
            "bash", "-c", "cd /work && yosys probe.ys",
        ],
        capture_output=True,
        text=True,
    )


def _run_cli(*argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "docker", "run", "--rm", "-v", f"{REPO}:/repo", "-w", "/repo", IMAGE,
            "python3", "-m", "gatepack", *argv,
        ],
        capture_output=True,
        text=True,
    )


def test_mcell_model_is_shared_between_equivalence_and_simulation():
    # R25 (structural): there is exactly one model file per M-cell, and it is the
    # same text appended to cells_sim.v that both C4 checks read.
    from gatepack.macros import load_models, model_files
    from gatepack.verify.equivalence import build_equivalence_script
    from gatepack.verify.simulation import build_compile_command
    from gatepack.verify.base import VerifyConfig

    paths = model_files()
    assert [Path(p).name for p in paths] == ["CNT4.v"]

    models = load_models()
    assert models.count("module CNT4") == 1

    config = VerifyConfig(top="t")
    script = build_equivalence_script(config)
    assert config.cells_sim_v in script  # equivalence reads cells_sim.v
    compile_cmd = build_compile_command(config, "out.vvp")
    assert config.cells_sim_v in compile_cmd  # simulation reads the same file


@requires_toolchain
def test_verify_on_macro_design_fails_before_reaching_the_model():
    """`gatepack verify` on a macro design fails at C3, before C4 can run.

    The front-end emits the macro as a dangling `(* gp_src *)` attribute with no
    instantiation (only a comment), so Yosys rejects ``generated.v`` with
    "syntax error, unexpected TOK_ENDMODULE".  The M-cell path cannot even reach
    synthesis — the shared model is never exercised by a real design.
    """
    build_dir = ".gpout/mcell_verify"
    try:
        proc = _run_cli(
            "verify",
            str(DESIGNS / "cnt4_macro.yaml"),
            "--library", "libraries/74aup.csv",
            "--build", build_dir,
        )
        # The build must fail (Yosys rejects the dangling attribute); if it ever
        # succeeds, this test's message is the loud part of the finding.
        assert proc.returncode == 1, (
            "verify unexpectedly passed on the macro golden. If the front-end now "
            "instantiates CNT4, this test must be replaced with one that asserts the "
            "macro IS exercised — see the mutation experiment below.\n"
            f"{proc.stdout}\n{proc.stderr}"
        )
    finally:
        subprocess.run(
            ["docker", "run", "--rm", "-v", f"{REPO}:/repo", "-w", "/repo", IMAGE,
             "rm", "-rf", build_dir],
            capture_output=True,
            text=True,
        )


@requires_toolchain
def test_wrong_mcell_model_is_not_caught_by_equivalence(tmp_path: Path) -> None:
    """The R25 finding, measured: a wrong CNT4 model still proves equivalent.

    Both equivalence sides read the same ``cells_sim.v``, so mutating the CNT4
    model changes them identically and the mutation cancels out.  This is not a
    green tick — it is the M-cell mutation path being unverified, stated as a
    test so a future independent reference model flips it.
    """
    top = (
        "module cnt_top(input wire clk, input wire rst_n, input wire en, "
        "output wire [3:0] q);\n"
        "  CNT4 c0 (.CLK(clk), .RST_N(rst_n), .EN(en), .Q(q));\n"
        "endmodule\n"
    )
    (tmp_path / "cnt_top.v").write_text(top)

    script = "\n".join(
        [
            "read_verilog cnt_top.v cells_sim.v",
            "proc; flatten; opt; async2sync; opt",
            "design -stash goldstash",
            "read_verilog cnt_top.v cells_sim.v",
            "proc; flatten; opt; async2sync; opt",
            "design -stash gatestash",
            "design -copy-from goldstash -as golden cnt_top",
            "design -copy-from gatestash -as mapped cnt_top",
            "equiv_make golden mapped equiv",
            "prep -top equiv",
            "equiv_simple",
            "equiv_induct -seq 16 equiv",
            "equiv_status -assert",
        ]
    )

    def run() -> str:
        proc = _run_yosys(tmp_path, script)
        return proc.stdout + proc.stderr

    def write_model(step: str) -> None:
        (tmp_path / "cells_sim.v").write_text(
            "module CNT4 (input wire CLK, input wire RST_N, input wire EN, "
            "output reg [3:0] Q);\n"
            "  always @(posedge CLK or negedge RST_N) begin\n"
            "    if (!RST_N) Q <= 4'd0;\n"
            f"    else if (EN) Q <= Q + {step};\n"
            "  end\n"
            "endmodule\n"
        )

    write_model("4'd1")
    correct = run()
    assert "successfully proven" in correct.lower(), correct

    # The deliberately wrong model: counts by two instead of one.
    write_model("4'd2")
    mutated = run()

    assert "successfully proven" in mutated.lower(), (
        "the wrong CNT4 model was NOT caught by equivalence: both sides read the "
        "same cells_sim.v, so the mutation cancels itself out (the R25 risk). "
        "The M-cell mutation path is unverified.\n"
        f"{mutated}"
    )
