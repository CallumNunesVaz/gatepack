"""Exhaustive simulation (§12 C4.3, [R4-17], §21.4).

Runs the mapped netlist (``write_verilog`` output) under Icarus Verilog, using
``cells_sim.v`` as the cell model, and compares it against the specification —
every ``2**n`` input vector (combinational) or every (state × input) transition
(sequential).  The expected outputs are computed from the compiled design, not
from the mapped netlist, so the comparison is independent of synthesis.

The specification is *the design with its synchronisers*.  C1 puts every ``sync``
input through a two-flop synchroniser and the reset through a two-flop
de-assert synchroniser (§9.3), so the FSM sees each input two clock edges after
it is presented.  The expected-value model below reproduces that latency
faithfully (a ``_ReferenceDesign`` simulates the synchroniser flops), and the
testbench drives each input long enough for the synchroniser to settle before
comparing — a single-cycle input pulse never reaches the FSM, which is exactly
the trap that made ``traffic_light`` fail before this was modelled (M6-FINDINGS
§2 is the same trap on the reset side).

Above the runtime cap the result is **not applicable** and correctness rests on
formal equivalence; the tool **never** falls back to random vectors with a
coverage figure (§21.4, [R4-18]).

The reset is *not* only a setup step.  In addition to the transition traces,
the stimulus asserts reset from every reachable state while the clock is low and
compares every output against the emitter's reset value before the next rising
edge — pinning both that reset drives the specified outputs and that it is
asynchronous (§9.3) — and then takes one edge with reset still held to pin that
reset *holds* the design cleared rather than only clearing it once.  The reset value is derived from the emitter: one-hot
clears every state bit (no ``state == S`` predicate is true), binary/gray loads
the initial code, and every ``sync`` input's synchroniser clears to 0.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from gatepack.frontend import expr as expr_mod
from gatepack.frontend.model import CompiledDesign
from gatepack.toolchain import iverilog_command, vvp_command
from gatepack.verify.base import CheckStatus, VerifyConfig

_PASS_MARK = "EXHAUSTIVE_SIM_PASS"
_FAIL_MARK = "EXHAUSTIVE_SIM_FAIL"


def exhaustive_vector_count(inputs: int, states: int) -> int:
    """Number of (state × input) transitions to check exhaustively."""
    return states * (1 << inputs)


def is_feasible(inputs: int, states: int, cap: int) -> bool:
    return exhaustive_vector_count(inputs, states) <= cap


@dataclass(frozen=True)
class SimulationOutcome:
    status: CheckStatus
    detail: str = ""


def decide(inputs: int, states: int, cap: int) -> SimulationOutcome:
    """Return NOT_APPLICABLE above the cap, else a runnable status."""
    count = exhaustive_vector_count(inputs, states)
    if count > cap:
        return SimulationOutcome(
            CheckStatus.NOT_APPLICABLE,
            f"{count} vectors exceed the exhaustive cap {cap}; correctness rests "
            f"on formal equivalence (§21.4)",
        )
    return SimulationOutcome(CheckStatus.NOT_RUN, f"{count} vectors to check")


def parse_run(stdout: str) -> SimulationOutcome:
    if _PASS_MARK in stdout:
        return SimulationOutcome(CheckStatus.PASSED)
    if _FAIL_MARK in stdout:
        return SimulationOutcome(CheckStatus.FAILED, "exhaustive simulation mismatched")
    return SimulationOutcome(CheckStatus.NOT_RUN, "unrecognized simulation output")


def build_compile_command(config: VerifyConfig, vvp: str) -> list[str]:
    return iverilog_command(
        vvp, [config.mapped_v, config.cells_sim_v, config.testbench_v]
    )


def build_run_command(vvp: str) -> list[str]:
    return vvp_command(vvp)


# ---------------------------------------------------------------------------
# Expected-value model (the design with its two-flop input synchronisers)
# ---------------------------------------------------------------------------


def _all_assignments(inputs: list[str]) -> list[dict[str, bool]]:
    n = len(inputs)
    out: list[dict[str, bool]] = []
    for code in range(1 << n):
        out.append(
            {name: bool(code & (1 << (n - 1 - i))) for i, name in enumerate(inputs)}
        )
    return out


def _eval_with_state(ast: expr_mod.Expr, env: dict[str, bool], state: str | None) -> bool:
    if isinstance(ast, expr_mod.Var):
        return env[ast.name]
    if isinstance(ast, expr_mod.Const):
        return ast.value
    if isinstance(ast, expr_mod.Not):
        return not _eval_with_state(ast.x, env, state)
    if isinstance(ast, expr_mod.Bin):
        left = _eval_with_state(ast.left, env, state)
        right = _eval_with_state(ast.right, env, state)
        if ast.op == "&":
            return left and right
        if ast.op == "|":
            return left or right
        if ast.op == "^":
            return left != right
        raise expr_mod.ExprError(f"unknown operator {ast.op!r}")
    if isinstance(ast, expr_mod.StateEq):
        # ``state`` is ``None`` while reset is asserted on the one-hot path: no
        # state bit is set, so no ``state == S`` predicate is true.
        return state is not None and ast.state == state
    raise TypeError(ast)


def _next_state(
    compiled: CompiledDesign, state: str, eff: dict[str, bool]
) -> str:
    for index, tr in enumerate(compiled.design.transitions):
        if tr.from_ == state:
            if expr_mod.evaluate(compiled.transition_guards[index], eff):
                return tr.to
    return state  # unreachable under totality; total transition set guarantees a hit


def _outputs(
    compiled: CompiledDesign, state: str | None, eff: dict[str, bool]
) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for name in compiled.output_names:
        ast = expr_mod.expand(compiled.output_asts[name], compiled.expression_asts)
        out[name] = _eval_with_state(ast, eff, state)
    return out


def expected_outputs(
    compiled: CompiledDesign, state: str, env: dict[str, bool]
) -> dict[str, bool]:
    """The specification's outputs for ``state`` under input assignment ``env``.

    Public on purpose. `gatepack.simulate` needs exactly this to build C11's
    divergence column, and it must be *this* evaluator rather than a second
    one, or the truth table could disagree with the verified result. It first
    depended on the private `_expected_outputs`, which was then renamed during
    an unrelated fix and broke every caller — a private cross-module
    dependency with no contract to protect it.
    """
    return _outputs(compiled, state, env)


def _reset_state(compiled: CompiledDesign) -> str | None:
    """The logical state the FSM occupies while reset is asserted.

    Derived from the emitter (:mod:`gatepack.frontend.verilog`), not guessed:

    * ``one_hot`` — every state bit clears, so *no* ``state == S`` predicate is
      true while reset is asserted.  The initial state is not loaded until the
      third clock edge after release, by set-via-feedback (M0-FINDINGS §6
      option 2), so "during reset" and "in the initial state" are genuinely
      different conditions.  ``None`` means "no state active".
    * ``binary`` / ``gray`` — the state vector resets to the initial code,
      which *is* a real state (an all-zero code may well be a real state here).
    """
    if compiled.encoding == "one_hot":
        return None
    return compiled.design.initial


def _reset_outputs(
    compiled: CompiledDesign, raw: dict[str, bool]
) -> dict[str, bool]:
    """The specification's outputs while reset is asserted (the reset phase).

    Derived from the emitter: the state flops are cleared (see
    :func:`_reset_state`); every ``sync`` input's two-flop synchroniser is
    cleared on the reset edge, so its effective value is 0; a non-``sync``
    input passes through combinationally and keeps whatever the testbench is
    driving (``raw``).
    """
    eff = dict(raw)
    for name in compiled.input_names:
        if compiled.input_sync[name]:
            eff[name] = False
    return _outputs(compiled, _reset_state(compiled), eff)


def _outputs_reference_state(compiled: CompiledDesign) -> bool:
    """True when any primary output depends on the state register.

    A reset fault reaches a primary output only through a state-dependent
    output.  When every output is a pure function of the inputs (parity,
    mux2to1), asserting reset cannot change any output and a reset-assertion
    probe would be vacuous — it is skipped rather than emitted to pass.
    """
    for name in compiled.output_names:
        ast = expr_mod.expand(compiled.output_asts[name], compiled.expression_asts)
        if expr_mod.states_referenced(ast):
            return True
    return False


class _ReferenceDesign:
    """The compiled FSM with the two-flop input-synchroniser latency of §9.3.

    For every ``sync`` input C1 emits ``s1 <= raw; s2 <= raw_s1`` on the clock
    edge, and the FSM reads ``s2``.  The FSM therefore sees the value of a sync
    input from **two** clock edges ago; non-sync inputs apply immediately.

    The reset *phase* is modelled by :meth:`reset_outputs`: while reset is
    asserted the state flops and the input synchronisers are cleared, so the
    outputs are those of the cleared state with every sync input forced to 0.
    That is distinct from the post-reset initial state, which the testbench's
    reset flush (§9.6) reaches on the third clock edge after release.
    """

    def __init__(self, compiled: CompiledDesign) -> None:
        self.compiled = compiled
        self.sync_names = [n for n in compiled.input_names if compiled.input_sync[n]]
        self.s1 = {n: False for n in self.sync_names}
        self.s2 = {n: False for n in self.sync_names}
        self.state = compiled.design.initial

    def _effective(self, raw: dict[str, bool]) -> dict[str, bool]:
        eff = dict(raw)
        for n in self.sync_names:
            eff[n] = self.s2[n]
        return eff

    def edge(self, raw: dict[str, bool]) -> dict[str, bool]:
        """Apply one clock edge; return the outputs observed just after it."""
        eff = self._effective(raw)  # FSM reads the OLD s2 (two-edge lag)
        self.state = _next_state(self.compiled, self.state, eff)
        old_s1 = self.s1
        self.s1 = {n: raw[n] for n in self.sync_names}
        self.s2 = dict(old_s1)  # s2 <= old s1 (non-blocking)
        return _outputs(self.compiled, self.state, self._effective(raw))

    def reset_outputs(self, raw: dict[str, bool]) -> dict[str, bool]:
        """Outputs while reset is asserted, independent of the current state.

        Asserting reset clears the state flops and the sync-input
        synchronisers; the pre-reset state is irrelevant, so this delegates to
        :func:`_reset_outputs` rather than reading ``self.state``.
        """
        return _reset_outputs(self.compiled, raw)

    def _key(self) -> tuple:
        return (
            self.state,
            tuple(sorted(self.s1.items())),
            tuple(sorted(self.s2.items())),
        )


def _drive_paths(
    compiled: CompiledDesign,
) -> dict[tuple[str, tuple], list[dict[str, bool]]]:
    """Shortest raw-input paths from the post-reset state to every reachable
    (logical state, s2) pair.

    Returns ``{(state, s2_tuple): [raw_dict, ...]}``.  ``s2_tuple`` covers only
    the sync inputs (non-sync inputs have no latency and are applied on the
    final edge).  A (state, s2) pair with no entry is unreachable — its logical
    transition can never fire in the real design, so it is not checked.
    """
    sync_names = [n for n in compiled.input_names if compiled.input_sync[n]]
    inputs = compiled.input_names

    start_state = compiled.design.initial
    start_s1 = {n: False for n in sync_names}
    start_s2 = {n: False for n in sync_names}

    def key(state: str, s1: dict, s2: dict) -> tuple:
        return (state, tuple(sorted(s1.items())), tuple(sorted(s2.items())))

    start_key = key(start_state, start_s1, start_s2)
    parent: dict[tuple, tuple | None] = {start_key: None}
    parent_raw: dict[tuple, dict[str, bool]] = {}
    queue: deque[tuple] = deque([start_key])

    def reconstruct(k: tuple) -> list[dict[str, bool]]:
        raw_path: list[dict[str, bool]] = []
        while parent[k] is not None:
            raw_path.append(parent_raw[k])
            k = parent[k]
        raw_path.reverse()
        return raw_path

    paths: dict[tuple[str, tuple], list[dict[str, bool]]] = {
        (start_state, tuple(sorted(start_s2.items()))): []
    }

    while queue:
        k = queue.popleft()
        st, s1t, s2t = k
        s1 = dict(s1t)
        s2 = dict(s2t)
        for raw in _all_assignments(inputs):
            eff = dict(raw)
            for n in sync_names:
                eff[n] = s2[n]
            nst = _next_state(compiled, st, eff)
            ns1 = {n: raw[n] for n in sync_names}
            ns2 = dict(s1)
            nk = key(nst, ns1, ns2)
            if nk not in parent:
                parent[nk] = k
                parent_raw[nk] = raw
                queue.append(nk)
            logical_key = (nst, tuple(sorted(ns2.items())))
            if logical_key not in paths:
                paths[logical_key] = reconstruct(nk)
    return paths


def _path_to_state(
    paths: dict[tuple[str, tuple], list[dict[str, bool]]], state: str
) -> list[dict[str, bool]]:
    """The shortest drive path to ``state``, from any settled-input variant.

    ``_drive_paths`` keys paths by ``(state, s2)``; a reset probe only needs to
    *reach* the state, not a specific synchroniser value (reset clears the
    synchronisers anyway), so the first (BFS-shortest) path for the state wins.
    """
    for (st, _s2), path in paths.items():
        if st == state:
            return path
    return []


def _stimulus(
    compiled: CompiledDesign,
) -> list[tuple[str, dict[str, bool] | None, dict[str, bool] | None]]:
    """Linear stimulus: ``(kind, inputs, expected)`` with kind ``reset``, ``edge``
    or ``reset_assert``.

    For every reachable logical transition ``(state, input)`` the trace resets,
    drives the synchronised design to that state with the synchroniser settled
    on that input, and takes the transition edge.  ``expected`` is the reference
    model's output after *every* edge (drive edges included), so any netlist
    deviation anywhere in the trace is a failure.

    A ``reset_assert`` step follows the transition traces: one per reachable
    state, asserting reset from that state while the clock is low and checking
    the outputs against the reset phase before the next rising edge.
    """
    steps: list[tuple[str, dict[str, bool] | None, dict[str, bool] | None]] = []
    paths = _drive_paths(compiled)

    for state in compiled.state_order:
        for assignment in _all_assignments(compiled.input_names):
            s2_tuple = tuple(
                sorted(
                    (n, assignment[n])
                    for n in compiled.input_names
                    if compiled.input_sync[n]
                )
            )
            path = paths.get((state, s2_tuple))
            if path is None:
                # Unreachable (state, settled-input) pair: the transition cannot
                # fire in the real design, so there is nothing to simulate.
                continue
            steps.append(("reset", None, None))
            ref = _ReferenceDesign(compiled)
            for raw in path:
                steps.append(("edge", raw, ref.edge(raw)))
            steps.append(("edge", assignment, ref.edge(assignment)))

    # Reset-assertion probes (§9.3): one per reachable state.  From each
    # reachable state, assert reset while the clock is low and compare every
    # output against the emitter's reset value BEFORE the next rising edge.
    # This pins two properties at once — reset drives the specified outputs,
    # and it is asynchronous (a synchronous reset would still show the
    # pre-reset output here).  The expected value is the same for every state:
    # reset clears the state, so the pre-reset state matters only insofar as it
    # decides whether the pre-reset output differs from the reset value — which
    # is exactly where a fault shows.  Probes are skipped when no output
    # depends on state: there is then nothing for a reset fault to corrupt.
    if _outputs_reference_state(compiled):
        probe = {name: False for name in compiled.input_names}
        for state in compiled.state_order:
            path = _path_to_state(paths, state)
            steps.append(("reset", None, None))
            ref = _ReferenceDesign(compiled)
            for raw in path:
                steps.append(("edge", raw, ref.edge(raw)))
            steps.append(("reset_assert", probe, ref.reset_outputs(probe)))
    return steps


# ---------------------------------------------------------------------------
# Testbench generation
# ---------------------------------------------------------------------------


def build_testbench(compiled: CompiledDesign, config: VerifyConfig) -> str:
    """Emit a self-checking exhaustive testbench for the mapped netlist.

    Each input is held across enough clock edges for its two-flop synchroniser
    to settle; expected outputs come from :class:`_ReferenceDesign`, so they
    include the synchroniser latency the netlist actually has.  In addition to
    the transition traces, a reset-assertion probe per reachable state checks
    the outputs during reset while the clock is low (async-assert + specified
    reset outputs).
    """
    design = compiled.design
    reset = design.reset
    active_low = reset.active == "low"
    clock_name = design.clock.signal if design.clock else "clk"
    reset_name = reset.signal
    assert_val = "1'b0" if active_low else "1'b1"
    release_val = "1'b1" if active_low else "1'b0"

    lines = [
        "// Exhaustive simulation testbench (C4 §C4.3).",
        "// Every reachable (state x input) transition through the mapped netlist,",
        "// compared against the spec including its input synchronisers. No random",
        "// vectors, no coverage.",
        "`timescale 1ns/1ps",
        "",
        "module exhaustive_tb;",
        f"  reg {clock_name};",
        f"  reg {reset_name};",
    ]
    for name in compiled.input_names:
        lines.append(f"  reg {name};")
    for name in compiled.output_names:
        lines.append(f"  wire {name};")
    lines.append("  integer _failures;")
    lines.append("")
    conn = [f".{clock_name}({clock_name})", f".{reset_name}({reset_name})"]
    conn += [f".{name}({name})" for name in compiled.input_names]
    conn += [f".{name}({name})" for name in compiled.output_names]
    lines.append(f"  {design.name} dut ({', '.join(conn)});")
    lines.append("")
    lines.append("  initial begin")
    lines.append("    _failures = 0;")
    lines.append(f"    {clock_name} = 1'b0;")
    for name in compiled.input_names:
        lines.append(f"    {name} = 1'b0;")
    lines.append("")

    for kind, assignment, expected in _stimulus(compiled):
        if kind == "reset":
            # Drive inputs to their post-reset rest value *before* the flush so
            # the input synchronisers settle at zero during the flush, matching
            # the reference model's post-reset start state.  Without this the
            # held inputs leak through the flush and the reference model drifts.
            for name in compiled.input_names:
                lines.append(f"    {name} = 1'b0;")
            lines.append(f"    {reset_name} = {assert_val};")
            lines.append("    #10;")
            lines.append(f"    {reset_name} = {release_val};")
            lines.append("    #10;")
            # Flush the reset de-assert synchroniser and load the initial
            # state (§9.6). The count is exact and must not carry "margin":
            #
            #   edge 1  rst_n_s1 <- 1
            #   edge 2  rst_n_s2 <- 1, so the internal reset releases
            #   edge 3  all-zero state feeds set-via-feedback, loading `initial`
            #
            # A fourth edge would advance the machine one transition PAST the
            # initial state, which the reference model does not do. That is a
            # real mismatch and it was masked for a long time: traffic_light's
            # initial state self-loops under all-zero inputs, so the extra edge
            # was invisible there. The pelican showcase, whose STOP state
            # advances unconditionally, is what exposed it.
            for _ in range(3):
                lines.append(f"    {clock_name} = 1'b1; #1; {clock_name} = 1'b0; #1;")
        elif kind == "reset_assert":
            # Assert reset while the clock is LOW and compare every output
            # BEFORE the next rising edge.  This pins both reset properties:
            #
            #   * async-assert (§9.3): the reset must take effect without a
            #     clock edge.  A synchronous reset would not have cleared the
            #     state yet and would still show the pre-reset output here.
            #   * reset drives the specified outputs: the comparison is against
            #     the emitter's reset value (cleared state + cleared sync
            #     inputs), NOT the initial state, which one-hot does not load
            #     until three edges after release.
            for name in compiled.input_names:
                bit = "1'b1" if assignment[name] else "1'b0"
                lines.append(f"    {name} = {bit};")
            lines.append("    #1;")
            lines.append(f"    {reset_name} = {assert_val};")
            lines.append("    #1;")
            for name in compiled.output_names:
                bit = "1'b1" if expected[name] else "1'b0"
                lines.append(f"    if ({name} !== {bit}) begin")
                lines.append(f'      $display("FAIL: {name} during reset");')
                lines.append("      _failures = _failures + 1;")
                lines.append("    end")
            # ...and reset must *hold* the design cleared across a clock edge,
            # not merely clear it at the instant of assertion.  §9.3 asserts
            # asynchronously and de-asserts synchronously, so any number of
            # edges taken while reset is held leaves the same reset outputs.
            #
            # This is the only check that clocks an edge with reset asserted,
            # and without it two distinct faults are indistinguishable: a reset
            # that never asserts (the flop is a plain DFF) and a reset that
            # became synchronous both leave the pre-edge comparison failing for
            # the same reason.  With the edge they separate — a synchronous
            # reset clears *on* it and matches the golden design from here,
            # while an absent reset takes D and does not.
            lines.append(f"    {clock_name} = 1'b1; #1; {clock_name} = 1'b0; #1;")
            for name in compiled.output_names:
                bit = "1'b1" if expected[name] else "1'b0"
                lines.append(f"    if ({name} !== {bit}) begin")
                lines.append(f'      $display("FAIL: {name} held in reset");')
                lines.append("      _failures = _failures + 1;")
                lines.append("    end")
        else:
            for name in compiled.input_names:
                bit = "1'b1" if assignment[name] else "1'b0"
                lines.append(f"    {name} = {bit};")
            lines.append("    #1;")
            lines.append(f"    {clock_name} = 1'b1; #1; {clock_name} = 1'b0; #1;")
            if expected is not None:
                for name in compiled.output_names:
                    bit = "1'b1" if expected[name] else "1'b0"
                    lines.append(f"    if ({name} !== {bit}) begin")
                    lines.append(f'      $display("FAIL: {name} at step %0d", {name});')
                    lines.append("      _failures = _failures + 1;")
                    lines.append("    end")
    lines.append("")
    lines.append("    if (_failures == 0) $display(\"EXHAUSTIVE_SIM_PASS\");")
    lines.append("    else $display(\"EXHAUSTIVE_SIM_FAIL (%0d)\", _failures);")
    lines.append("    $finish;")
    lines.append("  end")
    lines.append("endmodule")
    lines.append("")
    return "\n".join(lines)
