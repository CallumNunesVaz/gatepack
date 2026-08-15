"""Tests for the S-cell and infrastructure checks (gatepack.infra) — §9.5, §9.7."""

from __future__ import annotations

from gatepack.infra import (
    SupervisorSpec,
    check_all_flops_reset_connected,
    check_supervisor,
    check_supervisor_reset_width,
    check_supervisor_vcc,
    find_unreset_flops,
    identity_value,
    identity_values,
    worst_flop_reset_recovery_ns,
)
from gatepack.parts import Part


def _part(cell: str, tier: str, tpd: float | None) -> Part:
    return Part(
        cell=cell,
        tier=tier,
        family="AUP",
        part_suffix="X",
        inputs=2,
        gates_per_pkg=1,
        package="SOT-353",
        mfrs=["TI", "Nexperia"],
        vcc_min=0.8,
        vcc_max=3.6,
        area=1.0,
        tpd_ns=tpd,
    )


# --- SUPERVISOR ---------------------------------------------------------------


def test_supervisor_vcc_check():
    spec = SupervisorSpec()
    assert check_supervisor_vcc(spec, 3.3) is None
    assert check_supervisor_vcc(spec, 1.8) is None
    assert "does not include" in (check_supervisor_vcc(spec, 7.0) or "")


def test_supervisor_reset_width_unknown_is_not_a_pass():
    # §21.5: a check that cannot run must not read as a green pass.
    spec = SupervisorSpec()
    finding = check_supervisor_reset_width(spec, None)
    assert finding is not None and "cannot be checked" in finding


def test_supervisor_reset_width_ok_and_too_short():
    spec = SupervisorSpec()
    assert check_supervisor_reset_width(spec, 7.5) is None  # ns << ms
    too_short = SupervisorSpec(reset_assert_min_ns=5.0)
    assert "shorter than" in (check_supervisor_reset_width(too_short, 7.5) or "")


def test_worst_flop_reset_recovery_is_max_tpd():
    parts = [_part("DFF", "F", 7.2), _part("DFF_R", "F", 7.5), _part("NAND2", "G", 5.1)]
    assert worst_flop_reset_recovery_ns(parts) == 7.5
    assert worst_flop_reset_recovery_ns([_part("NAND2", "G", 5.1)]) is None


# --- reset connectivity -------------------------------------------------------


def test_unreset_flop_detected():
    v = "module m(input clk, input d, output reg q);\n" \
        "  always @(posedge clk) begin q <= d; end\nendmodule\n"
    findings = find_unreset_flops(v)
    assert findings and "q" in findings[0]


def test_reset_connected_flop_passes():
    v = "module m(input clk, input rst_n, input d, output reg q);\n" \
        "  always @(posedge clk or negedge rst_n) begin\n" \
        "    if (!rst_n) q <= 1'b0; else q <= d;\n" \
        "  end\nendmodule\n"
    assert find_unreset_flops(v) == []


def test_generated_sync_design_has_no_unreset_flops():
    from gatepack.frontend import compile_design_text

    from .helpers import sync_design

    result = compile_design_text(sync_design())
    assert check_all_flops_reset_connected(result.verilog) == []


# --- tie-off ------------------------------------------------------------------


def test_tieoff_identity_values():
    assert identity_value("!(A&B)", 2, 0) == 1  # NAND spare input -> high
    assert identity_value("!(A&B)", 2, 1) == 1
    assert identity_value("!(A|B)", 2, 0) == 0  # NOR spare input -> low
    assert identity_value("A&B", 2, 0) == 1  # AND -> high
    assert identity_value("A|B", 2, 0) == 0  # OR -> low
    assert identity_value("A^B", 2, 0) == 0  # XOR -> 0 (buffer identity)
    assert identity_value("!(A^B)", 2, 0) == 1  # XNOR -> 1 (buffer identity)


def test_tieoff_single_input_has_no_identity():
    assert identity_value("!A", 1, 0) is None
    assert identity_values("!A", 1) == {}


def test_tieoff_identity_values_map():
    assert identity_values("A&B", 2) == {"A": 1, "B": 1}
    assert identity_values("A|B", 2) == {"A": 0, "B": 0}
