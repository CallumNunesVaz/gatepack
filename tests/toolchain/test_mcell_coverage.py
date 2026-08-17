"""M-cell coverage (§9.4, M8, §19 R25) against the real toolchain.

Three things are established here, each of which the pure-Python suite does not
measure:

1. The M-cell *implementation* model is genuinely shared between C4's gate-side
   equivalence and its exhaustive simulation (R25) — one ``CNT4.v`` under
   ``gatepack/macros/models/``, appended to ``cells_sim.v``, read by both.
2. The M-cell *specification* side is independent: C1 emits a spec model
   (``cells_spec.v``) derived from the cell's declared semantics, and the golden
   side of equivalence reads that while the gate side keeps reading
   ``cells_sim.v``.  Reading the same implementation file on *both* sides is what
   made a wrong model cancel itself out (the R25 risk).
3. A **deliberately wrong** M-cell model is caught: mutating the implementation
   model to count by two while the spec still requires counting by one makes
   equivalence fail.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tests.toolchain.docker_runner import IMAGE, run_repo, run_work

REPO = Path(__file__).resolve().parents[2]
DESIGNS = REPO / "tests" / "golden" / "designs"


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
    return run_work(workdir, "bash", "-c", "cd /work && yosys probe.ys")


def _run_cli(*argv: str) -> subprocess.CompletedProcess[str]:
    return run_repo("python3", "-m", "gatepack", *argv)


def test_mcell_model_is_shared_between_equivalence_and_simulation():
    # R25 (structural): there is exactly one implementation model file per
    # M-cell, and it is the same text appended to cells_sim.v that both C4's
    # gate-side equivalence and its exhaustive simulation read.
    from gatepack.macros import load_models, load_spec_models, model_files
    from gatepack.verify.base import VerifyConfig
    from gatepack.verify.equivalence import build_equivalence_script
    from gatepack.verify.simulation import build_compile_command

    paths = model_files()
    assert [Path(p).name for p in paths] == ["CNT4.v", "SR4.v"]

    models = load_models()
    assert models.count("module CNT4") == 1

    config = VerifyConfig(top="t")
    script = build_equivalence_script(config)
    assert config.cells_sim_v in script  # the gate side reads the impl model
    assert config.cells_spec_v in script  # the golden side reads the spec model
    compile_cmd = build_compile_command(config, "out.vvp")
    assert config.cells_sim_v in compile_cmd  # simulation reads the same impl file

    # The two sides read *different* model files, or a wrong impl model would
    # change both sides identically and cancel itself out (the R25 risk, M8).
    golden_read = script.index(f"read_verilog {config.gold_v} {config.cells_spec_v}")
    gate_read = script.index(f"read_verilog {config.gate_v} {config.cells_sim_v}")
    assert golden_read < gate_read

    # The spec model exists and is generated from semantics (count by one), not
    # copied from the implementation model.
    assert load_spec_models().count("module CNT4") == 1
    assert "Q <= Q + 4'd1;" in load_spec_models()


@requires_toolchain
def test_verify_on_macro_design_reaches_c4():
    """`gatepack verify` on a macro design now reaches C4 instead of dying at C3.

    The front-end used to emit the macro as a dangling `(* gp_src *)` attribute
    with no instantiation, so Yosys rejected ``generated.v`` with "syntax error,
    unexpected TOK_ENDMODULE".  Now it emits a real `CNT4 dwell (...)` instance
    (plus a `(* blackbox *)` stub), so the design elaborates, synthesises, and the
    equivalence + exhaustive-simulation checks run and pass.
    """
    build_dir = ".gpout/mcell_verify"
    try:
        proc = _run_cli(
            "verify",
            "tests/golden/designs/cnt4_macro.yaml",
            "--library", "libraries/74aup.csv",
            "--build", build_dir,
        )
        combined = proc.stdout + proc.stderr
        # The old failure mode was a C3 syntax error; that must be gone.
        assert "syntax error" not in combined.lower(), combined
        assert "equivalence:               passed" in proc.stdout, combined
        assert "exhaustive simulation:     passed" in proc.stdout, combined

        generated = (REPO / build_dir / "generated.v").read_text()
        assert "CNT4 dwell (" in generated, "the macro is not instantiated"
        assert "(* blackbox *)" in generated
        assert ".EN(state_COUNT)" in generated
    finally:
        run_repo("rm", "-rf", build_dir)


@requires_toolchain
def test_wrong_mcell_model_is_caught_by_equivalence(tmp_path: Path) -> None:
    """The R25 finding, inverted: a wrong CNT4 model now fails equivalence.

    The golden side reads ``cells_spec.v`` (the specification model: count by
    one); the gate side reads ``cells_sim.v`` (the implementation model).  A
    mutation to ``cells_sim.v`` changes only the gate side, so the check fails —
    exactly what R25's "one shared file" alone could not establish.
    """
    from gatepack.macros import load_spec_models
    from gatepack.verify.base import VerifyConfig
    from gatepack.verify.equivalence import EquivStep, build_equivalence_script

    # A top module that *observes* the counter's Q, so the miter cannot optimize
    # it away.  The blackbox stub is what C1 emits; it lets `hierarchy -check`
    # pass in the shared front end.
    top = (
        "module cnt_top(input wire clk, input wire rst_n, input wire en, "
        "output wire [3:0] q);\n"
        "  CNT4 c0 (.CLK(clk), .RST_N(rst_n), .EN(en), .Q(q));\n"
        "endmodule\n"
    )
    blackbox = (
        "(* blackbox *)\n"
        "module CNT4 (input wire CLK, input wire RST_N, input wire EN, "
        "output wire [3:0] Q);\n"
        "endmodule\n"
    )
    (tmp_path / "generated.v").write_text(blackbox + "\n" + top)
    # mapped.v is the write_verilog output: the instantiation survives, the
    # blackbox stub does not (so reading the impl model next to it is clean).
    (tmp_path / "mapped.v").write_text(top)
    (tmp_path / "cells_spec.v").write_text(load_spec_models())

    config = VerifyConfig(
        top="cnt_top",
        generated_v="generated.v",
        mapped_v="mapped.v",
        gate_v="mapped.v",
        gold_v="gold.v",
        golden_json="golden.json",
        cells_sim_v="cells_sim.v",
        cells_spec_v="cells_spec.v",
    )
    script = build_equivalence_script(
        config, step=EquivStep.EQUIV_INDUCT, induction_steps=16
    )

    def run() -> subprocess.CompletedProcess[str]:
        return _run_yosys(tmp_path, script)

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
    assert "successfully proven" in (correct.stdout + correct.stderr).lower(), (
        correct.stdout + correct.stderr
    )

    # The deliberately wrong model: counts by two instead of one.  The spec side
    # still requires counting by one, so this must be caught.
    write_model("4'd2")
    mutated = run()
    combined = (mutated.stdout + mutated.stderr).lower()
    assert "successfully proven" not in combined, (
        "the wrong CNT4 model was NOT caught: the golden and gate sides must "
        "have read the same model file again. The M-cell mutation path is "
        f"unverified.\n{combined}"
    )


@requires_toolchain
def test_wrong_sr4_model_is_caught_by_equivalence(tmp_path: Path) -> None:
    """The second M-cell's mutation test (M8): a wrong SR4 model fails equivalence.

    A shift register's failure mode differs from a binary counter's — it corrupts
    *shifting*, not counting — so this demonstrates the spec/impl independence
    more than once, on a structurally different macro.
    """
    from gatepack.macros import load_spec_models
    from gatepack.verify.base import VerifyConfig
    from gatepack.verify.equivalence import EquivStep, build_equivalence_script

    top = (
        "module sr_top(input wire clk, input wire rst_n, input wire en, "
        "input wire si, output wire [3:0] q);\n"
        "  SR4 s0 (.CLK(clk), .RST_N(rst_n), .EN(en), .SI(si), .Q(q));\n"
        "endmodule\n"
    )
    blackbox = (
        "(* blackbox *)\n"
        "module SR4 (input wire CLK, input wire RST_N, input wire EN, "
        "input wire SI, output wire [3:0] Q);\n"
        "endmodule\n"
    )
    (tmp_path / "generated.v").write_text(blackbox + "\n" + top)
    (tmp_path / "mapped.v").write_text(top)
    (tmp_path / "cells_spec.v").write_text(load_spec_models())

    config = VerifyConfig(
        top="sr_top",
        generated_v="generated.v",
        mapped_v="mapped.v",
        gate_v="mapped.v",
        gold_v="gold.v",
        golden_json="golden.json",
        cells_sim_v="cells_sim.v",
        cells_spec_v="cells_spec.v",
    )
    script = build_equivalence_script(
        config, step=EquivStep.EQUIV_INDUCT, induction_steps=16
    )

    def run() -> subprocess.CompletedProcess[str]:
        return _run_yosys(tmp_path, script)

    def write_model(body: str) -> None:
        (tmp_path / "cells_sim.v").write_text(
            "module SR4 (input wire CLK, input wire RST_N, input wire EN, "
            "input wire SI, output reg [3:0] Q);\n"
            "  always @(posedge CLK or negedge RST_N) begin\n"
            "    if (!RST_N) Q <= 4'd0;\n"
            f"    else if (EN) Q <= {body};\n"
            "  end\n"
            "endmodule\n"
        )

    write_model("{Q[2:0], SI}")
    correct = run()
    assert "successfully proven" in (correct.stdout + correct.stderr).lower(), (
        correct.stdout + correct.stderr
    )

    # The deliberately wrong model: shifts in 0 instead of SI.  The spec still
    # requires shifting in SI, so the check must fail.
    write_model("{Q[2:0], 1'b0}")
    mutated = run()
    combined = (mutated.stdout + mutated.stderr).lower()
    assert "successfully proven" not in combined, (
        "the wrong SR4 model was NOT caught: the golden and gate sides must "
        "have read the same model file again. The SR4 mutation path is "
        f"unverified.\n{combined}"
    )
