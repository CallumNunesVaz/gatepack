"""Semantic compilation of a :class:`~gatepack.frontend.schema.Design`.

Turns the validated pydantic model into a :class:`CompiledDesign` carrying
parsed expressions, the state encoding, and the results of the §12 C1 checks:
reachability, guard overlap (SAT-style), transition-set exhaustiveness, and the
Johnson-counter suggestion.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from gatepack.frontend import expr as expr_mod
from gatepack.frontend import johnson
from gatepack.frontend import sat
from gatepack.frontend.errors import CompileError
from gatepack.frontend.schema import Design

# M-cell internal flop counts, used by §6 flop-count / clock-fanout metrics.
# Each macro additionally presents a single clock input pin (one fanout load).
M_CELL_FLOP_COUNTS: dict[str, int] = {
    "CNT4": 4,
    "CNT12": 12,
    "SIPO8": 8,
    "PISO8": 8,
    "JOHN10": 10,
    "DIV2N": 4,
    "CELEM": 1,
}


@dataclass
class CompiledDesign:
    design: Design
    source_name: str
    provenance: Mapping[str, int]

    state_index: dict[str, int]
    state_order: list[str]
    state_width: int
    state_codes: dict[str, int]  # binary/gray code per state (0-based)
    encoding: str

    expression_asts: dict[str, expr_mod.Expr]
    transition_guards: list[expr_mod.Expr]  # expanded to inputs; parallel to transitions
    output_asts: dict[str, expr_mod.Expr]

    input_names: list[str]
    input_sync: dict[str, bool]
    output_names: list[str]

    johnson_suggestion: str | None = None
    reachable: list[str] = field(default_factory=list)

    @property
    def state_flops(self) -> int:
        return self.state_width

    @property
    def synchroniser_flops(self) -> int:
        sync_inputs = sum(1 for n in self.input_names if self.input_sync[n])
        reset_sync = 2 if self.design.reset.sync_deassert else 0
        return 2 * sync_inputs + reset_sync

    @property
    def macro_flops(self) -> int:
        return sum(
            M_CELL_FLOP_COUNTS.get(m.cell, 0) for m in self.design.macros
        )

    @property
    def flop_count(self) -> int:
        return self.state_flops + self.synchroniser_flops + self.macro_flops

    @property
    def clock_fanout(self) -> int:
        return self.flop_count + len(self.design.macros)


def _state_encoding(design: Design) -> tuple[dict[str, int], int, dict[str, int]]:
    states = design.states
    state_index = {name: i for i, name in enumerate(states)}
    if design.encoding == "one_hot":
        width = len(states)
        codes = {name: i for i, name in enumerate(states)}
    else:
        width = max(1, math.ceil(math.log2(len(states))))
        if design.encoding == "binary":
            codes = {name: i for i, name in enumerate(states)}
        else:  # gray
            codes = {name: i ^ (i >> 1) for i, name in enumerate(states)}
    return state_index, width, codes


def compile_design(
    design: Design,
    source_name: str,
    provenance: Mapping[str, int],
) -> CompiledDesign:
    """Validate and compile ``design``; raise :class:`CompileError` on failure."""
    input_names = [p.name for p in design.inputs]
    input_sync = {p.name: p.sync for p in design.inputs}
    output_names = [p.name for p in design.outputs]
    input_set = set(input_names)

    # --- parse named expressions -------------------------------------------------
    expression_asts: dict[str, expr_mod.Expr] = {}
    for name, text in design.expressions.items():
        try:
            expression_asts[name] = expr_mod.parse(text)
        except expr_mod.ExprError as exc:
            raise CompileError(f"expression {name!r}: {exc}") from exc

    for name, ast in expression_asts.items():
        _check_expression_references(name, ast, input_set, set(design.expressions))

    # --- transitions -------------------------------------------------------------
    transition_guards: list[expr_mod.Expr] = []
    state_set = set(design.states)
    transition_pairs: list[tuple[str, str]] = []
    for index, tr in enumerate(design.transitions):
        if tr.from_ not in state_set:
            raise CompileError(
                f"transitions[{index}] 'from' state {tr.from_!r} is not declared"
            )
        if tr.to not in state_set:
            raise CompileError(
                f"transitions[{index}] 'to' state {tr.to!r} is not declared"
            )
        try:
            ast = expr_mod.parse(tr.when)
        except expr_mod.ExprError as exc:
            raise CompileError(
                f"transitions[{index}] when {tr.when!r}: {exc}"
            ) from exc
        if expr_mod.states_referenced(ast):
            raise CompileError(
                f"transitions[{index}] guard {tr.when!r} must not reference "
                f"'state =='; the source state is the 'from' field"
            )
        try:
            guard = expr_mod.expand(ast, expression_asts)
        except expr_mod.ExprError as exc:
            raise CompileError(
                f"transitions[{index}] guard {tr.when!r}: {exc}"
            ) from exc
        free = expr_mod.free_vars(guard)
        unknown = free - input_set
        if unknown:
            raise CompileError(
                f"transitions[{index}] guard {tr.when!r} references unknown "
                f"signals {sorted(unknown)!r}"
            )
        transition_guards.append(guard)
        transition_pairs.append((tr.from_, tr.to))

    # --- output logic ------------------------------------------------------------
    output_asts: dict[str, expr_mod.Expr] = {}
    for name, text in design.output_logic.items():
        try:
            ast = expr_mod.parse(text)
        except expr_mod.ExprError as exc:
            raise CompileError(f"output_logic[{name!r}]: {exc}") from exc
        _check_expression_references(
            f"output_logic[{name!r}]", ast, input_set, set(design.expressions)
        )
        bad_states = expr_mod.states_referenced(ast) - state_set
        if bad_states:
            raise CompileError(
                f"output_logic[{name!r}] references unknown states {sorted(bad_states)!r}"
            )
        output_asts[name] = ast

    # --- macros ------------------------------------------------------------------
    for macro in design.macros:
        if macro.cell not in M_CELL_FLOP_COUNTS:
            raise CompileError(
                f"macro {macro.instance!r}: unknown M-cell {macro.cell!r} "
                f"(known: {sorted(M_CELL_FLOP_COUNTS)})"
            )
        if design.clock is not None and macro.clock != design.clock.signal:
            raise CompileError(
                f"macro {macro.instance!r} clocks from {macro.clock!r}; expected "
                f"the design clock {design.clock.signal!r}"
            )
        if macro.enable:
            try:
                ast = expr_mod.parse(macro.enable)
            except expr_mod.ExprError as exc:
                raise CompileError(f"macro {macro.instance!r} enable: {exc}") from exc
            bad_states = expr_mod.states_referenced(ast) - state_set
            if bad_states:
                raise CompileError(
                    f"macro {macro.instance!r} enable references unknown states "
                    f"{sorted(bad_states)!r}"
                )

    # --- reachability ------------------------------------------------------------
    reachable = _reachable(design.states, design.initial, transition_pairs)
    unreachable = [s for s in design.states if s not in reachable]
    if unreachable:
        raise CompileError(
            f"unreachable state(s): {', '.join(unreachable)} (not reachable from "
            f"initial state {design.initial!r})"
        )

    # --- guard overlap + exhaustiveness (SAT-style) ------------------------------
    guards_by_state: dict[str, list[tuple[int, expr_mod.Expr]]] = {}
    for index, (src, _dst) in enumerate(transition_pairs):
        guards_by_state.setdefault(src, []).append((index, transition_guards[index]))

    for state in design.states:
        indexed = guards_by_state.get(state, [])
        guards = [g for _i, g in indexed]
        try:
            result = sat.check_state_guards(state, guards, input_names)
        except sat.SatLimitError as exc:
            raise CompileError(str(exc)) from exc
        for (i, j, assignment) in result.overlaps:
            a, b = indexed[i][0], indexed[j][0]
            raise CompileError(
                f"state {state!r}: overlapping guards on transitions[{a}] "
                f"({design.transitions[a].when!r}) and transitions[{b}] "
                f"({design.transitions[b].when!r}) — both true for inputs "
                f"{sat.format_assignment(assignment)} (non-deterministic)"
            )
        if result.gaps:
            raise CompileError(
                f"state {state!r}: non-exhaustive transition set — no outgoing "
                f"transition fires for inputs "
                f"{sat.format_assignment(result.gaps[0])}. "
                f"Add an explicit self-loop {{from: {state}, to: {state}, "
                f'when: "1"}} or a covering guard.'
            )

    # --- Johnson suggestion ------------------------------------------------------
    suggestion = johnson.suggest_johnson(
        design.states, transition_pairs, design.initial
    )

    state_index, width, codes = _state_encoding(design)

    return CompiledDesign(
        design=design,
        source_name=source_name,
        provenance=provenance,
        state_index=state_index,
        state_order=list(design.states),
        state_width=width,
        state_codes=codes,
        encoding=design.encoding,
        expression_asts=expression_asts,
        transition_guards=transition_guards,
        output_asts=output_asts,
        input_names=input_names,
        input_sync=input_sync,
        output_names=output_names,
        johnson_suggestion=suggestion,
        reachable=reachable,
    )


def _check_expression_references(
    where: str,
    ast: expr_mod.Expr,
    input_set: set[str],
    expression_set: set[str],
) -> None:
    free = expr_mod.free_vars(ast)
    unknown = free - input_set - expression_set
    if unknown:
        raise CompileError(
            f"{where} references unknown signals {sorted(unknown)!r}"
        )


def _reachable(
    states: Sequence[str],
    initial: str,
    transitions: Sequence[tuple[str, str]],
) -> list[str]:
    graph: dict[str, list[str]] = {s: [] for s in states}
    for src, dst in transitions:
        graph.setdefault(src, []).append(dst)
    seen: list[str] = []
    visited: set[str] = set()
    stack = [initial]
    while stack:
        node = stack.pop()
        if node in visited:
            continue
        visited.add(node)
        seen.append(node)
        for nxt in graph.get(node, []):
            if nxt not in visited:
                stack.append(nxt)
    return seen
