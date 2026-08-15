"""Exhaustive simulation (§12 C4.3, [R4-17], §21.4).

Runs the mapped netlist (``write_verilog`` output) under Icarus Verilog, using
``cells_sim.v`` as the cell model, and compares it against the specification —
every ``2**n`` input vector (combinational) or every (state × input) transition
(sequential).  The expected outputs are computed from the compiled design, not
from the mapped netlist, so the comparison is independent of synthesis.

Above the runtime cap the result is **not applicable** and correctness rests on
formal equivalence; the tool **never** falls back to random vectors with a
coverage figure (§21.4, [R4-18]).
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
# Testbench generation
# ---------------------------------------------------------------------------


def _all_assignments(inputs: list[str]) -> list[dict[str, bool]]:
    n = len(inputs)
    out: list[dict[str, bool]] = []
    for code in range(1 << n):
        out.append(
            {name: bool(code & (1 << (n - 1 - i))) for i, name in enumerate(inputs)}
        )
    return out


def _eval_with_state(ast: expr_mod.Expr, env: dict[str, bool], state: str) -> bool:
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
        return ast.state == state
    raise TypeError(ast)


def _expected_outputs(
    compiled: CompiledDesign, state: str, assignment: dict[str, bool]
) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for name in compiled.output_names:
        ast = expr_mod.expand(compiled.output_asts[name], compiled.expression_asts)
        out[name] = _eval_with_state(ast, assignment, state)
    return out


def _next_state(
    compiled: CompiledDesign, state: str, assignment: dict[str, bool]
) -> str:
    for index, tr in enumerate(compiled.design.transitions):
        if tr.from_ == state:
            if expr_mod.evaluate(compiled.transition_guards[index], assignment):
                return tr.to
    return state  # unreachable under totality; total transition set guarantees a hit


def _witness(guard: expr_mod.Expr, inputs: list[str]) -> dict[str, bool] | None:
    for assignment in _all_assignments(inputs):
        if expr_mod.evaluate(guard, assignment):
            return assignment
    return None


def _paths(compiled: CompiledDesign) -> tuple[dict[str, str | None], dict[str, dict[str, bool]]]:
    """BFS tree from the initial state: parent map and the input that reaches it."""
    initial = compiled.design.initial
    parent: dict[str, str | None] = {initial: None}
    parent_input: dict[str, dict[str, bool]] = {}
    queue: deque[str] = deque([initial])
    while queue:
        src = queue.popleft()
        for index, tr in enumerate(compiled.design.transitions):
            if tr.from_ != src or tr.to in parent:
                continue
            witness = _witness(compiled.transition_guards[index], compiled.input_names)
            if witness is None:
                continue
            parent[tr.to] = src
            parent_input[tr.to] = witness
            queue.append(tr.to)
    return parent, parent_input


def _stimulus(compiled: CompiledDesign) -> list[tuple[str, dict[str, bool] | None, dict[str, bool] | None]]:
    """Linear stimulus: ``(kind, inputs, expected)`` where kind is ``reset`` or ``trans``.

    ``expected`` is ``None`` for path-driving steps (reaching a state); every
    (state × input) transition carries the expected outputs of its *next* state.
    """
    parent, parent_input = _paths(compiled)
    steps: list[tuple[str, dict[str, bool] | None, dict[str, bool] | None]] = []
    for state in compiled.state_order:
        steps.append(("reset", None, None))
        drive: list[dict[str, bool]] = []
        s = state
        while parent[s] is not None:
            drive.append(parent_input[s])
            s = parent[s]
        drive.reverse()
        for assignment in drive:
            steps.append(("trans", assignment, None))
        for assignment in _all_assignments(compiled.input_names):
            nxt = _next_state(compiled, state, assignment)
            steps.append(("trans", assignment, _expected_outputs(compiled, nxt, assignment)))
    return steps


def build_testbench(compiled: CompiledDesign, config: VerifyConfig) -> str:
    """Emit a self-checking exhaustive testbench for the mapped netlist."""
    design = compiled.design
    reset = design.reset
    active_low = reset.active == "low"
    clock_name = design.clock.signal if design.clock else "clk"
    reset_name = reset.signal
    assert_val = "1'b0" if active_low else "1'b1"
    release_val = "1'b1" if active_low else "1'b0"

    lines = [
        "// Exhaustive simulation testbench (C4 §C4.3).",
        "// Every 2^n input vector / (state x input) transition through the mapped",
        "// netlist, compared against the spec. No random vectors, no coverage.",
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
            lines.append(f"    {reset_name} = {assert_val};")
            lines.append("    #10;")
            lines.append(f"    {reset_name} = {release_val};")
            lines.append("    #10;")
            # flush reset de-assert + input synchronisers before checking
            for _ in range(4):
                lines.append(f"    {clock_name} = 1'b1; #1; {clock_name} = 1'b0; #1;")
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
