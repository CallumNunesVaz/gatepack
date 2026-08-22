"""Unit tests for the reset-assertion phase of the exhaustive simulation.

The exhaustive testbench used to treat reset purely as a §9.6 *setup step* and
compare outputs only at transition edges, so a reset that never cleared the
state (the ``reset_polarity_flip`` mutation) was invisible to it and the fault
was reported "caught by equivalence only".  These tests pin the new behaviour:
the stimulus asserts reset from every reachable state while the clock is low
and compares every output against the emitter's reset value before the next
rising edge.  No Yosys/Icarus needed — everything here is a pure function of
the compiled design.
"""

from __future__ import annotations

from pathlib import Path

from gatepack.frontend import compile_design_file, compile_design_text
from gatepack.verify import simulation
from gatepack.verify.base import VerifyConfig

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _config(**overrides) -> VerifyConfig:
    base = dict(top="t")
    base.update(overrides)
    return VerifyConfig(**base)


def _binary_design() -> str:
    """A 3-state binary-encoded machine whose initial state is *not* all-zero.

    Binary codes A=0, B=1, C=2 and ``initial: B``: the reset value of the state
    vector is the code 1, which is a real state — the opposite of one-hot, where
    reset clears every state bit and no state predicate is true.
    """
    return (
        "name: bin\n"
        "timing_model: synchronous\n"
        "clock: {signal: clk, freq_hz: 1000, source: OSC}\n"
        "reset: {signal: rst_n, active: low, source: SUPERVISOR}\n"
        "encoding: binary\n"
        "inputs:\n"
        "  - {name: x, sync: false}\n"
        "outputs:\n"
        "  - {name: o}\n"
        "states: [A, B, C]\n"
        "initial: B\n"
        "transitions:\n"
        "  - {from: A, to: B, when: '1'}\n"
        "  - {from: B, to: C, when: '1'}\n"
        "  - {from: C, to: A, when: '1'}\n"
        "output_logic:\n"
        "  o: \"state == B\"\n"
    )


# --- reset state / reset outputs ---------------------------------------------


def test_one_hot_reset_outputs_have_no_state_active():
    compiled = compile_design_file(EXAMPLES / "sequence_detector" / "design.yaml").compiled
    assert simulation._reset_state(compiled) is None
    assert simulation._reset_outputs(compiled, {"din": False}) == {"match": False}
    assert simulation._reset_outputs(compiled, {"din": True}) == {"match": False}


def test_binary_reset_outputs_are_the_initial_state():
    compiled = compile_design_text(_binary_design()).compiled
    assert compiled.encoding == "binary"
    assert simulation._reset_state(compiled) == "B"
    assert simulation._reset_outputs(compiled, {"x": False}) == {"o": True}


def test_sync_input_is_forced_to_zero_during_reset():
    compiled = compile_design_text(
        "name: s\n"
        "timing_model: synchronous\n"
        "clock: {signal: clk, freq_hz: 1000, source: OSC}\n"
        "reset: {signal: rst_n, active: low, source: SUPERVISOR}\n"
        "encoding: one_hot\n"
        "inputs:\n"
        "  - {name: btn, sync: true}\n"
        "outputs:\n"
        "  - {name: o}\n"
        "states: [A]\n"
        "initial: A\n"
        "transitions:\n"
        "  - {from: A, to: A, when: '1'}\n"
        "output_logic:\n"
        "  o: \"state == A | btn\"\n"
    ).compiled
    # `btn` is a sync input: its synchroniser clears on the reset edge, so the
    # output is 0 during reset even though `state == A` would be false and the
    # raw pin is driven high.
    assert simulation._reset_outputs(compiled, {"btn": True}) == {"o": False}


# --- whether a reset probe is emitted ----------------------------------------


def test_outputs_reference_state_detects_moore_and_combinational():
    moore = compile_design_file(EXAMPLES / "sequence_detector" / "design.yaml").compiled
    assert simulation._outputs_reference_state(moore) is True

    comb = compile_design_file(EXAMPLES / "parity" / "design.yaml").compiled
    assert simulation._outputs_reference_state(comb) is False


def test_combinational_testbench_has_no_reset_probe():
    # A purely combinational output cannot observe a reset fault, so no probe is
    # emitted (and the pre-existing transition count is unchanged).
    compiled = compile_design_file(EXAMPLES / "parity" / "design.yaml").compiled
    tb = simulation.build_testbench(compiled, _config(top="parity"))
    assert "during reset" not in tb


def test_sequential_testbench_probes_reset_from_every_reachable_state():
    compiled = compile_design_file(EXAMPLES / "sequence_detector" / "design.yaml").compiled
    tb = simulation.build_testbench(compiled, _config(top="sequence_detector"))
    # one reset-assert probe per reachable state, checking the single output.
    assert tb.count("during reset") == len(compiled.state_order)
    assert "if (match !== 1'b0)" in tb


def test_stimulus_emits_one_reset_assert_per_reachable_state():
    compiled = compile_design_file(EXAMPLES / "sequence_detector" / "design.yaml").compiled
    steps = simulation._stimulus(compiled)
    assert sum(1 for kind, _, _ in steps if kind == "reset_assert") == len(
        compiled.state_order
    )


# --- the reset-hold edge ------------------------------------------------------


def test_combinational_testbench_has_no_reset_hold_check():
    compiled = compile_design_file(EXAMPLES / "parity" / "design.yaml").compiled
    tb = simulation.build_testbench(compiled, _config(top="parity"))
    assert "held in reset" not in tb


def test_reset_probe_clocks_one_edge_with_reset_still_asserted():
    """Reset must *hold* the design cleared, not merely clear it once.

    Without this edge two genuinely different faults are indistinguishable: a
    reset that never asserts (the flop is a plain ``DFF``) and a reset that
    became synchronous both fail the pre-edge comparison for the same reason,
    and nothing else in the testbench ever clocks an edge while reset is held.
    Measured, not assumed — see ``tests/toolchain/test_reset_simulation.py``.
    """
    compiled = compile_design_file(EXAMPLES / "sequence_detector" / "design.yaml").compiled
    tb = simulation.build_testbench(compiled, _config(top="sequence_detector"))
    assert tb.count("held in reset") == len(compiled.state_order)

    # The edge is taken between the two comparisons, with reset still asserted:
    # every "during reset" check is followed by a clock pulse and then the
    # matching "held in reset" check, and reset is never released in between.
    reset_name = compiled.design.reset.signal
    clock_name = compiled.design.clock.signal
    body = tb[tb.index("during reset") :]
    during = body.index("during reset")
    held = body.index("held in reset")
    between = body[during:held]
    assert f"{clock_name} = 1'b1;" in between, between
    assert f"{reset_name} = 1'b1" not in between, between
