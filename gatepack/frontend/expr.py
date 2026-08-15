"""Boolean expression language for ``design.yaml`` (§10.2).

One language serves guards (transition ``when``), ``expressions``, ``output_logic``
and macro ``enable`` fields:

* identifiers reference inputs or named expressions,
* ``!`` (not), ``&`` (and), ``|`` (or), ``^`` (xor), parentheses,
* constants ``0`` / ``1``,
* ``state == NAME`` — a state-equality test used in ``output_logic`` and macro
  enables (Moore-style).

Precedence (tightest first): ``!``, ``&``, ``^``, ``|`` — matching
``gatepack.liberty.boolean``.  Emission fully parenthesises to remove any
precedence ambiguity.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


class ExprError(ValueError):
    """An expression is malformed or invalid for its context."""


@dataclass(frozen=True)
class Var:
    name: str


@dataclass(frozen=True)
class Const:
    value: bool


@dataclass(frozen=True)
class Not:
    x: "Expr"


@dataclass(frozen=True)
class Bin:
    op: str
    left: "Expr"
    right: "Expr"


@dataclass(frozen=True)
class StateEq:
    state: str


Expr = Var | Const | Not | Bin | StateEq


_OPERATORS = {"&", "|", "^", "!", "(", ")", "=="}


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
            continue
        if c in "&|^!()":
            tokens.append(c)
            i += 1
            continue
        if c == "=":
            if i + 1 < n and text[i + 1] == "=":
                tokens.append("==")
                i += 2
                continue
            raise ExprError(f"unexpected '=' in expression {text!r} (use '==')")
        if c.isdigit():
            j = i
            while j < n and text[j].isdigit():
                j += 1
            tokens.append(text[i:j])
            i = j
            continue
        if c.isalpha() or c == "_":
            j = i
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            tokens.append(text[i:j])
            i = j
            continue
        raise ExprError(f"unexpected character {c!r} in expression {text!r}")
    return tokens


def _parse_or(tokens: list[str], pos: int) -> tuple[Expr, int]:
    node, pos = _parse_xor(tokens, pos)
    while pos < len(tokens) and tokens[pos] == "|":
        rhs, pos = _parse_xor(tokens, pos + 1)
        node = Bin("|", node, rhs)
    return node, pos


def _parse_xor(tokens: list[str], pos: int) -> tuple[Expr, int]:
    node, pos = _parse_and(tokens, pos)
    while pos < len(tokens) and tokens[pos] == "^":
        rhs, pos = _parse_and(tokens, pos + 1)
        node = Bin("^", node, rhs)
    return node, pos


def _parse_and(tokens: list[str], pos: int) -> tuple[Expr, int]:
    node, pos = _parse_not(tokens, pos)
    while pos < len(tokens) and tokens[pos] == "&":
        rhs, pos = _parse_not(tokens, pos + 1)
        node = Bin("&", node, rhs)
    return node, pos


def _parse_not(tokens: list[str], pos: int) -> tuple[Expr, int]:
    if pos < len(tokens) and tokens[pos] == "!":
        node, pos = _parse_not(tokens, pos + 1)
        return Not(node), pos
    return _parse_atom(tokens, pos)


def _parse_atom(tokens: list[str], pos: int) -> tuple[Expr, int]:
    if pos >= len(tokens):
        raise ExprError("unexpected end of expression")
    token = tokens[pos]
    if token == "(":
        node, pos = _parse_or(tokens, pos + 1)
        if pos >= len(tokens) or tokens[pos] != ")":
            raise ExprError("missing ')' in expression")
        return node, pos + 1
    if token in _OPERATORS:
        raise ExprError(f"unexpected {token!r} in expression")
    if token.isdigit():
        if token not in ("0", "1"):
            raise ExprError(f"constant {token!r} must be 0 or 1")
        return Const(token == "1"), pos + 1
    if token == "state":
        if pos + 2 < len(tokens) and tokens[pos + 1] == "==" and tokens[pos + 2].isidentifier():
            return StateEq(tokens[pos + 2]), pos + 3
        raise ExprError("'state' may only appear as 'state == NAME'")
    return Var(token), pos + 1


def parse(text: str) -> Expr:
    """Parse an expression string into an AST."""
    tokens = _tokenize(text)
    if not tokens:
        raise ExprError("empty expression")
    node, pos = _parse_or(tokens, 0)
    if pos != len(tokens):
        raise ExprError(f"unexpected trailing tokens {tokens[pos:]!r} in {text!r}")
    return node


def free_vars(expr: Expr) -> set[str]:
    """Names of variables (inputs or named expressions) referenced by ``expr``."""
    if isinstance(expr, Var):
        return {expr.name}
    if isinstance(expr, Const):
        return set()
    if isinstance(expr, Not):
        return free_vars(expr.x)
    if isinstance(expr, Bin):
        return free_vars(expr.left) | free_vars(expr.right)
    if isinstance(expr, StateEq):
        return set()
    raise TypeError(expr)


def states_referenced(expr: Expr) -> set[str]:
    """State names compared against with ``state == NAME``."""
    if isinstance(expr, StateEq):
        return {expr.state}
    if isinstance(expr, (Var, Const)):
        return set()
    if isinstance(expr, Not):
        return states_referenced(expr.x)
    if isinstance(expr, Bin):
        return states_referenced(expr.left) | states_referenced(expr.right)
    raise TypeError(expr)


def expand(expr: Expr, definitions: Mapping[str, Expr]) -> Expr:
    """Substitute named-expression references with their definitions.

    Detects cycles (an expression defined in terms of itself, directly or
    transitively).
    """

    def go(e: Expr, seen: tuple[str, ...]) -> Expr:
        if isinstance(e, Var):
            if e.name in definitions:
                if e.name in seen:
                    chain = " -> ".join((*seen, e.name))
                    raise ExprError(f"cyclic expression definition: {chain}")
                return go(definitions[e.name], (*seen, e.name))
            return e
        if isinstance(e, Const):
            return e
        if isinstance(e, Not):
            return Not(go(e.x, seen))
        if isinstance(e, Bin):
            return Bin(e.op, go(e.left, seen), go(e.right, seen))
        if isinstance(e, StateEq):
            return e
        raise TypeError(e)

    return go(expr, ())


def evaluate(expr: Expr, env: Mapping[str, bool]) -> bool:
    """Evaluate a combinational expression under an input assignment.

    Raises ``ExprError`` if ``expr`` contains a ``state ==`` test (state is not
    an input).
    """
    if isinstance(expr, Var):
        if expr.name not in env:
            raise ExprError(f"unknown signal {expr.name!r} in evaluation")
        return env[expr.name]
    if isinstance(expr, Const):
        return expr.value
    if isinstance(expr, Not):
        return not evaluate(expr.x, env)
    if isinstance(expr, Bin):
        left = evaluate(expr.left, env)
        right = evaluate(expr.right, env)
        if expr.op == "&":
            return left and right
        if expr.op == "|":
            return left or right
        if expr.op == "^":
            return left != right
        raise ExprError(f"unknown operator {expr.op!r}")
    if isinstance(expr, StateEq):
        raise ExprError("state comparison has no combinational value")
    raise TypeError(expr)


def to_verilog(
    expr: Expr,
    var_map: Mapping[str, str],
    state_map: Mapping[str, str],
) -> str:
    """Emit a Verilog expression.

    ``var_map`` names inputs and named expressions; ``state_map`` maps a state
    name to the Verilog signal that is asserted when the FSM is in that state
    (the state bit for one-hot, ``(state == CODE)`` otherwise).
    """
    if isinstance(expr, Var):
        if expr.name not in var_map:
            raise ExprError(f"unknown signal {expr.name!r} in Verilog emission")
        return var_map[expr.name]
    if isinstance(expr, Const):
        return "1'b1" if expr.value else "1'b0"
    if isinstance(expr, Not):
        return f"(~{to_verilog(expr.x, var_map, state_map)})"
    if isinstance(expr, Bin):
        op = {"&": "&", "|": "|", "^": "^"}[expr.op]
        return (
            f"({to_verilog(expr.left, var_map, state_map)} {op} "
            f"{to_verilog(expr.right, var_map, state_map)})"
        )
    if isinstance(expr, StateEq):
        if expr.state not in state_map:
            raise ExprError(f"unknown state {expr.state!r} in Verilog emission")
        return state_map[expr.state]
    raise TypeError(expr)
