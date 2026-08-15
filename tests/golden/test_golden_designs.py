"""§18 golden reference designs.

The passing designs run through C1 without Yosys.  The must-fail designs assert
that the front-end *rejects* them; the property-violating and latch-inferring
entries need sby/Yosys and are skipped with an explicit reason (Yosys is not
installed here, and results are never faked).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gatepack.estimate import VccIncompatibleError, run_estimate
from gatepack.frontend import AsyncRefused, CompileError, compile_design_file

DESIGNS = Path(__file__).parent / "designs"
LIBRARY_CSV = Path(__file__).resolve().parents[2] / "libraries" / "74aup.csv"


def test_traffic_light_compiles_one_hot():
    result = compile_design_file(DESIGNS / "traffic_light.yaml")
    c = result.compiled
    assert c.encoding == "one_hot"
    assert c.state_order == ["RED", "GREEN", "AMBER"]
    assert "reg state_RED;" in result.verilog
    assert '(* gp_src = "traffic_light.yaml:' in result.verilog
    assert "(* src =" not in result.verilog  # Yosys's own attribute (M0 §2)
    # every transition carries its own gp_src attribute
    for i in range(5):
        assert f"transitions[{i}]" in result.verilog


def test_xor2_combinational():
    result = compile_design_file(DESIGNS / "xor2.yaml")
    assert "wire y_int = (a ^ b);" in result.verilog
    assert "assign y = y_int;" in result.verilog


def test_decoder_3to8_combinational():
    result = compile_design_file(DESIGNS / "decoder_3to8.yaml")
    v = result.verilog
    for i in range(8):
        assert f"assign y{i} = y{i}_int;" in v
    assert "wire y7_int = ((s0 & s1) & s2);" in v


def test_no_attribute_immediately_precedes_assign():
    # M0-FINDINGS §1: an attribute before a continuous assign is a syntax error
    # in Yosys 0.23.  Every provenance attribute must sit on a wire/reg
    # declaration; no line of emitted Verilog may be an attribute immediately
    # followed by an `assign`.
    import re

    result = compile_design_file(DESIGNS / "traffic_light.yaml")
    lines = result.verilog.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("assign"):
            prev = lines[i - 1].strip() if i > 0 else ""
            assert not prev.endswith("*)"), (
                f"attribute immediately precedes an assign at line {i + 1}: {prev!r}"
            )
    # and the output logic specifically rides on a declared net, not the assign
    assert "wire red_int = state_RED;" in result.verilog
    assert "assign red = red_int;" in result.verilog


@pytest.mark.parametrize(
    ("filename", "exc", "match"),
    [
        ("overlapping_guards.yaml", CompileError, "overlapping guards"),
        ("unreachable_state.yaml", CompileError, "unreachable"),
        ("non_exhaustive.yaml", CompileError, "non-exhaustive"),
        ("async_handshake.yaml", AsyncRefused, "asynchronous"),
        ("duplicate_key.yaml", CompileError, "duplicate mapping key"),
    ],
)
def test_must_fail_designs(filename, exc, match):
    with pytest.raises(exc, match=match):
        compile_design_file(DESIGNS / filename)


def test_property_violating_fsm_skipped_without_sby():
    # C1 only *emits* the property; it is discharged by sby at M6.  Skipped.
    pytest.skip("property discharging needs sby (M6); not installed here")


def test_latch_inferring_design_skipped_without_yosys():
    # The latch ban is a C3 Yosys-level assertion (§9.2), not a C1 check.
    pytest.skip("latch-inferring golden needs a real Yosys run (C3); not installed")


def test_vcc_incompatible_part_must_fail(tmp_path):
    # 74HC CNT4 at vcc 1.8: the macro's supply range (2.0..6.0 V) excludes 1.8 V.
    design = DESIGNS / "traffic_light.yaml"
    library = tmp_path / "hc.csv"
    library.write_text(
        "cell,tier,family,part_suffix,equivalents,function,inputs,gates_per_pkg,"
        "package,mfrs,vcc_min,vcc_max,area,tpd_ns,iq_ua\n"
        'INV,G,AUP,1G04,,!A,1,1,SOT-353,"TI;Nexperia",0.8,3.6,1.0,4.6,0.9\n'
        'DFF,F,AUP,1G79,,,2,1,SOT-353,"TI;Nexperia",0.8,3.6,1.0,7.2,0.9\n'
        'CNT4,M,HC,HC161,,,3,1,SO-16,"TI;Nexperia",2.0,6.0,8.0,,4.0\n'
    )
    # the traffic_light design has no macro; add one referencing CNT4 at vcc 1.8
    text = (DESIGNS / "traffic_light.yaml").read_text()
    text = text.replace("constraints:\n  vcc: 3.3\n", "constraints:\n  vcc: 1.8\n")
    text += "macros:\n  - {instance: dwell, cell: CNT4, clock: clk, enable: \"state == GREEN\"}\n"
    design_copy = tmp_path / "d.yaml"
    design_copy.write_text(text)

    with pytest.raises(VccIncompatibleError, match="CNT4"):
        run_estimate(design_copy, library, build_dir=tmp_path / "build")


def test_single_source_part_requires_override(tmp_path):
    # A single-sourced cell is excluded from the Liberty file (§10.1 [R4-9]);
    # with only single-sourced cells the generator refuses entirely.
    from gatepack.liberty.generator import generate as generate_liberty
    from gatepack.liberty.validate import LibertyError
    from gatepack.parts import Part

    single = [
        Part(
            cell="INV", tier="G", family="AUP", part_suffix="1G04",
            inputs=1, gates_per_pkg=1, package="SOT-353", mfrs=["TI"],
            vcc_min=0.8, vcc_max=3.6, area=1.0,
        )
    ]
    with pytest.raises(LibertyError, match="no cells eligible"):
        generate_liberty(single, library_name="t", project_vcc=3.3)


def test_verify_reaches_combinational_golden(tmp_path):
    # C4 now reaches the §18 designs: the full verify pipeline runs without the
    # toolchain, reporting the tool-dependent checks as "not run" (never a pass)
    # while the pure-Python §9.5 checks pass.
    from gatepack.verify.base import CheckStatus
    from gatepack.verify.run import run_verify

    result = run_verify(
        DESIGNS / "xor2.yaml",
        LIBRARY_CSV,
        build_dir=tmp_path / "vb",
    )
    statuses = {c.name: c.status for c in result.report.checks}
    assert statuses["equivalence"] is CheckStatus.NOT_RUN
    assert statuses["flop reset connectivity"] is CheckStatus.PASSED
    assert statuses["supervisor parameters"] is CheckStatus.PASSED
    assert result.manifest["verification"]["overall"] == "not run"


def test_verify_reaches_sequential_golden(tmp_path):
    from gatepack.verify.base import CheckStatus
    from gatepack.verify.run import run_verify

    result = run_verify(
        DESIGNS / "traffic_light.yaml",
        LIBRARY_CSV,
        build_dir=tmp_path / "vb",
    )
    assert (tmp_path / "vb" / "cells_sim.v").exists()
    assert (tmp_path / "vb" / "yosys.ys").exists()
    assert result.manifest["design"] == "traffic_light"
    # sync inputs (go, emergency) -> input synchronisers; they must be
    # reset-connected for the §9.5 check to pass.
    statuses = {c.name: c.status for c in result.report.checks}
    assert statuses["flop reset connectivity"] is CheckStatus.PASSED
