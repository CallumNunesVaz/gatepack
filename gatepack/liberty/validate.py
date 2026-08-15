"""C2 self-check (§12 C2, R1): verify emitted Liberty is structurally sound
and the cell count matches expectation.

This is a pure-Python structural check.  Yosys-level parse validation is
deferred to the pinned container (see the Dockerfile and BUILD-NOTES); this
check exists so that a generator bug cannot silently produce a degenerate
library, which §19 R1 identifies as the most likely silent failure in the
system.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Sequence


class LibertyError(ValueError):
    """The Liberty text failed structural validation."""


_FF_ATTRS = (
    "next_state",
    "clocked_on",
    "clear",
    "preset",
    "clear_preset_var1",
    "clear_preset_var2",
)

_TOKEN = re.compile(
    r"""
      (?P<STRING>"(?:[^"\\]|\\.)*")
    | (?P<COMMENT>/\*.*?\*/)
    | (?P<NUMBER>-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)
    | (?P<LPAREN>\()
    | (?P<RPAREN>\))
    | (?P<LBRACE>\{)
    | (?P<RBRACE>\})
    | (?P<COLON>:)
    | (?P<SEMI>;)
    | (?P<COMMA>,)
    | (?P<WORD>[A-Za-z_][A-Za-z0-9_]*)
    | (?P<SKIP>\s+)
    | (?P<OTHER>.)
    """,
    re.VERBOSE | re.DOTALL,
)


@dataclass
class CellInfo:
    name: str
    has_ff: bool = False
    ff_attrs: set[str] = field(default_factory=set)
    area: bool = False
    output_function: bool = False
    pin_directions: list[str] = field(default_factory=list)


def _tokenize(text: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    for match in _TOKEN.finditer(text):
        kind = match.lastgroup
        if kind in ("SKIP", "COMMENT", "OTHER"):
            continue
        tokens.append((kind, match.group()))
    return tokens


def _brace_balanced(text: str) -> None:
    depth = 0
    in_string = False
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if in_string:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_string = False
        else:
            if c == '"':
                in_string = True
            elif c == "/" and i + 1 < n and text[i + 1] == "*":
                end = text.find("*/", i + 2)
                if end == -1:
                    raise LibertyError("unterminated /* comment */")
                i = end + 1
                continue
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth < 0:
                    raise LibertyError("unbalanced '}'")
        i += 1
    if depth != 0:
        raise LibertyError(f"unbalanced braces (depth {depth})")
    if in_string:
        raise LibertyError("unterminated string literal")


def _parse_cell_body(name: str, body: list[tuple[str, str]]) -> CellInfo:
    info = CellInfo(name=name)
    i = 0
    n = len(body)
    while i < n:
        kind, value = body[i]
        if kind == "WORD" and value == "area":
            info.area = True
            i += 1
            continue
        if kind == "WORD" and value == "pin":
            i = _parse_pin(info, body, i)
            continue
        if kind == "WORD" and value == "ff":
            info.has_ff = True
            i = _parse_ff(info, body, i)
            continue
        i += 1
    return info


def _parse_pin(info: CellInfo, body: list[tuple[str, str]], i: int) -> int:
    n = len(body)
    if i + 1 >= n or body[i + 1][0] != "LPAREN":
        raise LibertyError(f"cell {info.name}: malformed pin")
    i += 2
    if i >= n or body[i][0] != "WORD":
        raise LibertyError(f"cell {info.name}: pin missing name")
    i += 1
    if i >= n or body[i][0] != "RPAREN":
        raise LibertyError(f"cell {info.name}: pin missing ')'")
    i += 1
    if i >= n or body[i][0] != "LBRACE":
        raise LibertyError(f"cell {info.name}: pin missing '{{'")
    depth = 1
    i += 1
    direction = None
    function = False
    while i < n:
        kind, value = body[i]
        if kind == "LBRACE":
            depth += 1
        elif kind == "RBRACE":
            depth -= 1
            if depth == 0:
                break
        elif kind == "WORD" and value == "direction":
            if i + 2 < n and body[i + 1][0] == "COLON" and body[i + 2][0] == "WORD":
                direction = body[i + 2][1]
        elif kind == "WORD" and value == "function":
            function = True
        i += 1
    if direction is not None:
        info.pin_directions.append(direction)
    if direction == "output" and function:
        info.output_function = True
    return i + 1


def _parse_ff(info: CellInfo, body: list[tuple[str, str]], i: int) -> int:
    n = len(body)
    if i + 1 >= n or body[i + 1][0] != "LPAREN":
        raise LibertyError(f"cell {info.name}: malformed ff group")
    i += 2
    while i < n and body[i][0] != "RPAREN":
        i += 1
    if i >= n:
        raise LibertyError(f"cell {info.name}: ff group missing ')'")
    i += 1
    if i >= n or body[i][0] != "LBRACE":
        raise LibertyError(f"cell {info.name}: ff group missing '{{'")
    depth = 1
    i += 1
    while i < n:
        kind, value = body[i]
        if kind == "LBRACE":
            depth += 1
        elif kind == "RBRACE":
            depth -= 1
            if depth == 0:
                break
        elif kind == "WORD" and value in _FF_ATTRS:
            info.ff_attrs.add(value)
        i += 1
    return i + 1


def _parse_cell(tokens: list[tuple[str, str]], pos: int) -> tuple[CellInfo, int]:
    n = len(tokens)
    # tokens[pos] is ("WORD", "cell")
    pos += 1
    if pos >= n or tokens[pos][0] != "LPAREN":
        raise LibertyError("cell: expected '('")
    pos += 1
    if pos >= n or tokens[pos][0] != "WORD":
        raise LibertyError("cell: expected cell name")
    name = tokens[pos][1]
    pos += 1
    if pos >= n or tokens[pos][0] != "RPAREN":
        raise LibertyError(f"cell {name}: expected ')'")
    pos += 1
    if pos >= n or tokens[pos][0] != "LBRACE":
        raise LibertyError(f"cell {name}: expected '{{'")
    depth = 1
    pos += 1
    body: list[tuple[str, str]] = []
    while pos < n:
        kind, value = tokens[pos]
        if kind == "LBRACE":
            depth += 1
        elif kind == "RBRACE":
            depth -= 1
            if depth == 0:
                break
        body.append((kind, value))
        pos += 1
    if depth != 0:
        raise LibertyError(f"cell {name}: unbalanced braces")
    return _parse_cell_body(name, body), pos + 1


def parse_library(text: str) -> tuple[str, list[CellInfo]]:
    """Return ``(library_name, cells)``; raise ``LibertyError`` on bad structure."""
    tokens = _tokenize(text)
    pos = 0
    n = len(tokens)

    while pos < n and not (tokens[pos][0] == "WORD" and tokens[pos][1] == "library"):
        pos += 1
    if pos >= n:
        raise LibertyError("no 'library' block found")
    pos += 1
    if pos >= n or tokens[pos][0] != "LPAREN":
        raise LibertyError("expected '(' after 'library'")
    pos += 1
    if pos >= n or tokens[pos][0] not in ("WORD", "STRING"):
        raise LibertyError("expected library name")
    library_name = tokens[pos][1].strip('"')
    pos += 1
    if pos >= n or tokens[pos][0] != "RPAREN":
        raise LibertyError("expected ')' after library name")
    pos += 1
    if pos >= n or tokens[pos][0] != "LBRACE":
        raise LibertyError("expected '{' to open library block")
    pos += 1

    cells: list[CellInfo] = []
    while pos < n:
        kind, value = tokens[pos]
        if kind == "WORD" and value == "cell":
            info, pos = _parse_cell(tokens, pos)
            cells.append(info)
        elif kind == "RBRACE":
            pos += 1
            break
        else:
            pos += 1

    return library_name, cells


def _duplicates(names: list[str]) -> list[str]:
    seen: set[str] = set()
    dups: set[str] = set()
    for name in names:
        if name in seen:
            dups.add(name)
        seen.add(name)
    return sorted(dups)


def validate_library(text: str, expected_cells: Sequence[str]) -> list[str]:
    """Validate ``text`` structurally and check it contains exactly ``expected_cells``.

    Returns the list of cell names found (in order).  Raises ``LibertyError`` on
    any structural problem or cell-count/name mismatch.
    """
    _brace_balanced(text)
    library_name, cells = parse_library(text)
    if not library_name:
        raise LibertyError("library has no name")

    names = [c.name for c in cells]
    dups = _duplicates(names)
    if dups:
        raise LibertyError(f"duplicate cell names in library: {dups}")

    expected = list(expected_cells)
    missing = [c for c in expected if c not in names]
    extra = [c for c in names if c not in expected]
    if missing or extra:
        raise LibertyError(
            f"cell count/name mismatch: expected {len(expected)} cells, "
            f"found {len(names)}; missing={missing}, extra={extra}"
        )

    for cell in cells:
        if not cell.area:
            raise LibertyError(f"cell {cell.name}: missing 'area'")
        if cell.has_ff:
            for attr in ("next_state", "clocked_on"):
                if attr not in cell.ff_attrs:
                    raise LibertyError(f"cell {cell.name}: ff group missing '{attr}'")
        else:
            if not cell.output_function:
                raise LibertyError(
                    f"cell {cell.name}: combinational cell missing output function"
                )

    return names
