"""Stage 2 — primitive flow table and fundamental-mode admissibility (§7.3).

Builds the primitive flow table from the FSM spec: rows are states, columns are
input combinations, entries are ``(next state, outputs)`` with the entry marked
*stable* where ``next state == current state``.  Then checks fundamental-mode
admissibility: every declared transition must be reachable by a single input
change from a stable total state; a transition that can only fire through two
simultaneous input changes is a specification error and is refused, naming both
inputs.

State reduction (compatible-state merging) is deliberately **not** performed.
An unreduced table is correct, merely larger; a wrong merge is a silent
behaviour change, and merging is only safe when the reduction itself is tested —
which is out of scope here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from gatepack.frontend import expr as expr_mod
from gatepack.frontend.errors import AsyncRefused
from gatepack.frontend.model import CompiledDesign


@dataclass(frozen=True)
class FlowTable:
    """The primitive flow table of a compiled asynchronous design.

    ``combos`` lists the input combinations in a canonical order (the first
    input is the most significant bit, so ``combos[0]`` is all-zero).  For each
    ``(state, combo)`` the table records the next state and the outputs.
    """

    states: tuple[str, ...]
    input_names: tuple[str, ...]
    output_names: tuple[str, ...]
    combos: tuple[tuple[bool, ...], ...]
    #: ``next_state[s][c]`` is the next state name for state ``s`` at combo ``c``.
    next_state: tuple[tuple[str, ...], ...]
    #: ``outputs[s][c]`` is ``((name, bool), ...)`` sorted by output name.
    outputs: tuple[tuple[tuple[tuple[str, bool], ...], ...], ...]

    @property
    def transitions(self) -> tuple[tuple[str, str], ...]:
        """The distinct ``(source, target)`` state transitions with ``target != source``."""
        pairs = {
            (state, self.next_state[si][ci])
            for si, state in enumerate(self.states)
            for ci in range(len(self.combos))
            if self.next_state[si][ci] != state
        }
        return tuple(sorted(pairs))

    def stable_combos(self, state: str) -> tuple[int, ...]:
        """Combo indices where ``state`` is stable (next state == state)."""
        si = self.states.index(state)
        return tuple(
            ci for ci in range(len(self.combos)) if self.next_state[si][ci] == state
        )

    def fire_combos(self, state: str, target: str) -> tuple[int, ...]:
        """Combo indices where ``state`` transitions to ``target``."""
        si = self.states.index(state)
        return tuple(
            ci
            for ci in range(len(self.combos))
            if self.next_state[si][ci] == target
        )


def all_input_combos(input_names) -> tuple[tuple[bool, ...], ...]:
    """Every input combination in canonical (count) order, MSB first."""
    n = len(input_names)
    return tuple(
        tuple(bool((code >> (n - 1 - i)) & 1) for i in range(n))
        for code in range(1 << n)
    )


def build_flow_table(compiled: CompiledDesign) -> FlowTable:
    """Construct the primitive flow table from a compiled design."""
    states = tuple(compiled.state_order)
    input_names = tuple(compiled.input_names)
    output_names = tuple(compiled.output_names)
    combos = all_input_combos(input_names)

    next_state: list[tuple[str, ...]] = []
    outputs: list[tuple[tuple[tuple[str, bool], ...], ...]] = []
    for state in states:
        ns_row: list[str] = []
        out_row: list[tuple[tuple[str, bool], ...]] = []
        for combo in combos:
            env = dict(zip(input_names, combo))
            ns_row.append(_next_state(compiled, state, env))
            out_row.append(_outputs(compiled, state, env, output_names))
        next_state.append(tuple(ns_row))
        outputs.append(tuple(out_row))

    return FlowTable(
        states=states,
        input_names=input_names,
        output_names=output_names,
        combos=combos,
        next_state=tuple(next_state),
        outputs=tuple(outputs),
    )


def check_admissibility(compiled: CompiledDesign, table: FlowTable) -> None:
    """Refuse a transition that can only fire through two simultaneous input changes.

    For every ``(source, target)`` transition (``target != source``), the source
    state must have a stable input combination at Hamming distance 1 from some
    input combination that fires the transition.  If the minimum distance is 2
    or more, the transition requires two inputs to change at once and is a
    specification error (§7.3) — refused, naming the inputs that differ.
    """
    for source, target in table.transitions:
        stable = table.stable_combos(source)
        if not stable:
            raise AsyncRefused(
                f"asynchronous design {compiled.design.name!r} refused: state "
                f"{source!r} has no stable input (no self-loop); a fundamental-mode "
                "transition must leave from a settled state (§7.3)"
            )
        fire = table.fire_combos(source, target)
        best: tuple[int, tuple[bool, ...], tuple[bool, ...]] | None = None
        for a in stable:
            for b in fire:
                d = _hamming(table.combos[a], table.combos[b])
                if best is None or d < best[0]:
                    best = (d, table.combos[a], table.combos[b])
        assert best is not None
        distance, src_combo, dst_combo = best
        if distance >= 2:
            differing = sorted(
                name
                for name, x, y in zip(table.input_names, src_combo, dst_combo)
                if x != y
            )
            raise AsyncRefused(
                f"asynchronous design {compiled.design.name!r} refused: transition "
                f"{source} -> {target} requires inputs {differing!r} to change "
                "simultaneously; a fundamental-mode transition changes exactly "
                "one input (§7.3)"
            )


def _hamming(a: tuple[bool, ...], b: tuple[bool, ...]) -> int:
    return sum(1 for x, y in zip(a, b) if x != y)


def _next_state(compiled: CompiledDesign, state: str, env: Mapping[str, bool]) -> str:
    for index, tr in enumerate(compiled.design.transitions):
        if tr.from_ == state:
            if expr_mod.evaluate(compiled.transition_guards[index], env):
                return tr.to
    return state  # unreachable under totality; the guard set is exhaustive


def _outputs(
    compiled: CompiledDesign,
    state: str,
    env: Mapping[str, bool],
    output_names: tuple[str, ...],
) -> tuple[tuple[str, bool], ...]:
    out: list[tuple[str, bool]] = []
    for name in output_names:
        ast = expr_mod.expand(compiled.output_asts[name], compiled.expression_asts)
        out.append((name, _eval_output(ast, env, state)))
    return tuple(out)


def _eval_output(ast: expr_mod.Expr, env: Mapping[str, bool], state: str) -> bool:
    if isinstance(ast, expr_mod.Var):
        return env[ast.name]
    if isinstance(ast, expr_mod.Const):
        return ast.value
    if isinstance(ast, expr_mod.Not):
        return not _eval_output(ast.x, env, state)
    if isinstance(ast, expr_mod.Bin):
        left = _eval_output(ast.left, env, state)
        right = _eval_output(ast.right, env, state)
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
