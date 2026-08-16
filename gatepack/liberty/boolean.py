"""Translation of ``parts.csv`` boolean functions to Liberty syntax.

Input functions use ``!`` (not), ``&`` (and), ``|`` (or), ``^`` (xor) with
parentheses and input identifiers ``A``, ``B``, ``C``, ...  Liberty accepts the
same operators, so translation is: parse (to validate well-formedness and the
input set), then re-emit fully parenthesised so precedence is unambiguous.
"""

from __future__ import annotations

from typing import Mapping


class BooleanError(ValueError):
    """A boolean function in ``parts.csv`` is malformed."""


_VAR = tuple[str]
# node = ("var", name) | ("not", node) | ("bin", op, left, right)


def _tokenize(func: str) -> list[str]:
    tokens: list[str] = []
    i = 0
    n = len(func)
    while i < n:
        c = func[i]
        if c.isspace():
            i += 1
            continue
        if c in "!&|^()":
            tokens.append(c)
            i += 1
            continue
        if c.isalpha() or c == "_":
            j = i
            while j < n and (func[j].isalnum() or func[j] == "_"):
                j += 1
            tokens.append(func[i:j])
            i = j
            continue
        raise BooleanError(f"unexpected character {c!r} in boolean function {func!r}")
    return tokens


def _parse_expr(tokens: list[str], pos: int) -> tuple[tuple, int]:
    node, pos = _parse_xor(tokens, pos)
    while pos < len(tokens) and tokens[pos] == "|":
        rhs, pos = _parse_xor(tokens, pos + 1)
        node = ("bin", "|", node, rhs)
    return node, pos


def _parse_xor(tokens: list[str], pos: int) -> tuple[tuple, int]:
    node, pos = _parse_and(tokens, pos)
    while pos < len(tokens) and tokens[pos] == "^":
        rhs, pos = _parse_and(tokens, pos + 1)
        node = ("bin", "^", node, rhs)
    return node, pos


def _parse_and(tokens: list[str], pos: int) -> tuple[tuple, int]:
    node, pos = _parse_not(tokens, pos)
    while pos < len(tokens) and tokens[pos] == "&":
        rhs, pos = _parse_not(tokens, pos + 1)
        node = ("bin", "&", node, rhs)
    return node, pos


def _parse_not(tokens: list[str], pos: int) -> tuple[tuple, int]:
    if pos < len(tokens) and tokens[pos] == "!":
        node, pos = _parse_not(tokens, pos + 1)
        return ("not", node), pos
    return _parse_atom(tokens, pos)


def _parse_atom(tokens: list[str], pos: int) -> tuple[tuple, int]:
    if pos >= len(tokens):
        raise BooleanError("unexpected end of boolean function")
    token = tokens[pos]
    if token == "(":
        node, pos = _parse_expr(tokens, pos + 1)
        if pos >= len(tokens) or tokens[pos] != ")":
            raise BooleanError("missing ')' in boolean function")
        return node, pos + 1
    if token in "!&|^)":
        raise BooleanError(f"unexpected {token!r} in boolean function")
    return ("var", token), pos + 1


def _variables(node: tuple) -> set[str]:
    if node[0] == "var":
        return {node[1]}
    if node[0] == "not":
        return _variables(node[1])
    return _variables(node[2]) | _variables(node[3])


def _emit(node: tuple) -> str:
    if node[0] == "var":
        return node[1]
    if node[0] == "not":
        return f"(!{_emit(node[1])})"
    return f"({_emit(node[2])} {node[1]} {_emit(node[3])})"


def _emit_verilog(node: tuple) -> str:
    if node[0] == "var":
        return node[1]
    if node[0] == "not":
        return f"(~{_emit_verilog(node[1])})"
    return f"({_emit_verilog(node[2])} {node[1]} {_emit_verilog(node[3])})"


def pin_names(inputs: int) -> list[str]:
    """Input pin names for a combinational cell: ``A``, ``B``, ``C``, ..."""
    return [chr(ord("A") + i) for i in range(inputs)]


def translate(func: str, inputs: int) -> str:
    """Validate ``func`` against ``inputs`` pins and emit Liberty syntax."""
    node, expected = _parse_and_validate(func, inputs)
    return _emit(node)


def translate_verilog(func: str, inputs: int) -> str:
    """Validate ``func`` against ``inputs`` pins and emit Verilog syntax.

    Used by the ``cells_sim.v`` behavioural models ([R4-17]) so the simulation
    model of a G-cell is generated from the same ``parts.csv`` function string
    the Liberty file uses, and cannot drift from it.
    """
    node, expected = _parse_and_validate(func, inputs)
    return _emit_verilog(node)


def _parse_and_validate(func: str, inputs: int) -> tuple[tuple, set[str]]:
    tokens = _tokenize(func)
    if not tokens:
        raise BooleanError("empty boolean function")
    node, pos = _parse_expr(tokens, 0)
    if pos != len(tokens):
        raise BooleanError(f"unexpected trailing tokens {tokens[pos:]!r} in {func!r}")
    expected = set(pin_names(inputs))
    used = _variables(node)
    unknown = used - expected
    if unknown:
        raise BooleanError(
            f"function {func!r} references {sorted(unknown)!r}; "
            f"expected inputs {sorted(expected)!r}"
        )
    return node, expected


def _eval_node(node: tuple, env: dict[str, bool]) -> bool:
    if node[0] == "var":
        return env[node[1]]
    if node[0] == "not":
        return not _eval_node(node[1], env)
    left = _eval_node(node[2], env)
    right = _eval_node(node[3], env)
    if node[1] == "&":
        return left and right
    if node[1] == "|":
        return left or right
    if node[1] == "^":
        return left != right
    raise BooleanError(f"unknown operator {node[1]!r}")


def evaluate(func: str, inputs: int, assignment: dict[str, bool]) -> bool:
    """Evaluate ``func`` (over pins A..) under a complete ``assignment``."""
    node, expected = _parse_and_validate(func, inputs)
    missing = expected - set(assignment)
    if missing:
        raise BooleanError(f"assignment missing inputs {sorted(missing)!r}")
    return _eval_node(node, assignment)


def parse_function(func: str, inputs: int) -> tuple:
    """Parse and validate ``func`` once, returning the (opaque) AST node.

    Hot loops (SCOAP, fault simulation) call :func:`evaluate` many times per
    gate; re-tokenising and re-parsing the same string on every call dominates
    the cost.  Callers that evaluate a gate repeatedly should parse once and
    reuse the node with :func:`eval_function`.
    """
    node, _expected = _parse_and_validate(func, inputs)
    return node


def eval_function(node: tuple, assignment: Mapping[str, bool]) -> bool:
    """Evaluate a node from :func:`parse_function` under ``assignment``."""
    return _eval_node(node, dict(assignment))
