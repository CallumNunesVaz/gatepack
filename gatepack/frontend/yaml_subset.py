"""A minimal YAML subset parser for ``design.yaml``, with line provenance.

The environment has no network access, so PyYAML cannot be installed.  The
``design.yaml`` schema of §10.2 uses a small, well-defined YAML subset:

* block mappings (``key: value`` and ``key:`` followed by indented blocks),
* block sequences (``- item``),
* flow mappings (``{a: b, c: d}``) and flow sequences (``[a, b, c]``),
  including nesting (``[[arm, fault_a], [arm, fault_b]]``),
* single/double-quoted and plain scalars, integers, floats, ``true``/``false``,
  ``null``.

Deliberate differences from full YAML:

* only ``true``/``false`` (and ``null``) are recognised as special scalars.
  ``on``/``off``/``yes``/``no``/``y``/``n`` are **plain strings**, which is what
  a hardware-naming domain wants (a state or input called ``ON`` must not
  silently become a boolean — the YAML 1.1 footgun).
* block scalars (``|`` / ``>``), anchors/aliases and tags are unsupported and
  raise ``ParseError``.
* tab indentation is rejected (as in real YAML).

The parser records the 1-based line number of every node so the C1 emitter can
attach ``(* gp_src = "design.yaml:<line>:<path>" *)`` provenance attributes
(§15.1).

This module is deliberately self-contained; switching to PyYAML later is a
drop-in replacement at the ``parse`` boundary, not a format change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Union


class ParseError(ValueError):
    """The ``design.yaml`` text is not valid for the supported subset."""

    def __init__(self, line: int, message: str) -> None:
        self.line = line
        super().__init__(f"line {line}: {message}")


@dataclass(frozen=True)
class Scalar:
    value: str
    line: int


@dataclass(frozen=True)
class Mapping:
    items: list[tuple[str, "Node"]]
    line: int


@dataclass(frozen=True)
class Sequence:
    items: list["Node"]
    line: int


Node = Union[Scalar, Mapping, Sequence]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse(text: str) -> Node:
    """Parse ``text`` into a :class:`Node` tree."""
    lines = _preprocess(text)
    if not lines:
        raise ParseError(1, "empty document")
    parser = _Parser(lines)
    node = parser.parse_block_node(0)
    return node


def to_python(node: Node) -> Any:
    """Convert a :class:`Node` tree to plain Python (dict/list/scalar)."""
    if isinstance(node, Scalar):
        return scalar_value(node)
    if isinstance(node, Mapping):
        return {key: to_python(value) for key, value in node.items}
    if isinstance(node, Sequence):
        return [to_python(item) for item in node.items]
    raise TypeError(f"unknown node type {type(node)!r}")


def provenance(node: Node, prefix: str = "") -> dict[str, int]:
    """Return ``{path: line}`` for every construct in the tree.

    Paths follow the ``src`` attribute convention of §15.1:
    ``inputs[0]``, ``transitions[2]``, ``output_logic.enable``, ``constraints.vcc``.
    """
    out: dict[str, int] = {}

    def walk(n: Node, path: str) -> None:
        if isinstance(n, Scalar):
            out[path] = n.line
        elif isinstance(n, Mapping):
            if path:
                out[path] = n.line
            for key, value in n.items:
                child = f"{path}.{key}" if path else key
                walk(value, child)
        elif isinstance(n, Sequence):
            if path:
                out[path] = n.line
            for index, item in enumerate(n.items):
                walk(item, f"{path}[{index}]")

    walk(node, prefix)
    return out


def scalar_value(node: Scalar) -> Any:
    """Interpret a :class:`Scalar` as its Python value."""
    s = node.value
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return _unquote(s[1:-1], '"')
    if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
        return s[1:-1].replace("''", "'")
    if s == "true":
        return True
    if s == "false":
        return False
    if s in ("null", "~", ""):
        return None
    if _is_int(s):
        return int(s)
    if _is_float(s):
        return float(s)
    return s


# ---------------------------------------------------------------------------
# Preprocessing
# ---------------------------------------------------------------------------


def _preprocess(text: str) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        content = _strip_comment(raw).rstrip()
        lines.append((lineno, content))
    return lines


def _strip_comment(line: str) -> str:
    quote: str | None = None
    i = 0
    n = len(line)
    while i < n:
        c = line[i]
        if quote:
            if c == "\\" and i + 1 < n:
                i += 2
                continue
            if c == quote:
                quote = None
        else:
            if c in ('"', "'"):
                quote = c
            elif c == "#" and (i == 0 or line[i - 1] in " \t"):
                return line[:i]
        i += 1
    return line


def _unquote(s: str, quote: str) -> str:
    out: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == "\\" and i + 1 < n:
            nxt = s[i + 1]
            escapes = {
                "n": "\n", "t": "\t", "r": "\r", "0": "\0",
                "\\": "\\", '"': '"', "'": "'",
            }
            out.append(escapes.get(nxt, nxt))
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _is_int(s: str) -> bool:
    if not s:
        return False
    body = s[1:] if s[0] in "+-" else s
    return body.isdigit()


def _is_float(s: str) -> bool:
    if not s or s.startswith((".", "+.", "-.")):
        # require at least one digit before any '.'
        pass
    if not any(c.isdigit() for c in s):
        return False
    try:
        float(s)
    except ValueError:
        return False
    return any(c in s for c in ".eE")


# ---------------------------------------------------------------------------
# Block parser
# ---------------------------------------------------------------------------


class _Parser:
    def __init__(self, lines: list[tuple[int, str]]) -> None:
        self.lines = lines
        self.pos = 0

    def peek(self) -> tuple[int, str] | None:
        while self.pos < len(self.lines):
            lineno, content = self.lines[self.pos]
            if content.strip():
                return lineno, content
            self.pos += 1
        return None

    def parse_block_node(self, indent: int) -> Node:
        entry = self.peek()
        if entry is None:
            return Scalar("", 0)
        lineno, content = entry
        if _is_seq_item(content):
            return self.parse_sequence(indent, lineno)
        return self.parse_mapping(indent, lineno)

    def parse_mapping(self, indent: int, start_line: int) -> Mapping:
        items: list[tuple[str, Node]] = []
        while True:
            entry = self.peek()
            if entry is None:
                break
            lineno, content = entry
            cur = _indent(content)
            if cur < indent:
                break
            if cur > indent:
                raise ParseError(lineno, "unexpected indentation")
            if _is_seq_item(content):
                raise ParseError(lineno, "sequence item where mapping key expected")
            key, inline = _split_mapping_line(content, lineno)
            self.pos += 1
            if inline is None:
                nxt = self.peek()
                if nxt is None or _indent(nxt[1]) <= indent:
                    value: Node = Scalar("", lineno)
                else:
                    value = self.parse_block_node(_indent(nxt[1]))
            else:
                value = parse_inline_value(inline, lineno)
            items.append((key, value))
        return Mapping(items, start_line)

    def parse_sequence(self, indent: int, start_line: int) -> Sequence:
        items: list[Node] = []
        while True:
            entry = self.peek()
            if entry is None:
                break
            lineno, content = entry
            cur = _indent(content)
            if cur < indent:
                break
            if cur > indent:
                raise ParseError(lineno, "unexpected indentation")
            if not _is_seq_item(content):
                break
            rest = _seq_item_rest(content)
            self.pos += 1
            if rest == "":
                nxt = self.peek()
                if nxt is not None and _indent(nxt[1]) > indent:
                    items.append(self.parse_block_node(_indent(nxt[1])))
                else:
                    items.append(Scalar("", lineno))
            else:
                items.append(parse_inline_value(rest, lineno))
        return Sequence(items, start_line)


def _indent(content: str) -> int:
    count = 0
    for c in content:
        if c == " ":
            count += 1
        elif c == "\t":
            raise ParseError(0, "tab characters are not allowed in indentation")
        else:
            break
    return count


def _is_seq_item(content: str) -> bool:
    stripped = content.lstrip()
    return stripped == "-" or stripped.startswith("- ")


def _seq_item_rest(content: str) -> str:
    stripped = content.lstrip()
    return stripped[1:].strip()


def _split_mapping_line(content: str, lineno: int) -> tuple[str, str | None]:
    quote: str | None = None
    i = 0
    n = len(content)
    while i < n:
        c = content[i]
        if quote:
            if c == "\\" and i + 1 < n:
                i += 2
                continue
            if c == quote:
                quote = None
        else:
            if c in ('"', "'"):
                quote = c
            elif c == ":":
                key = _strip_quotes(content[:i].strip())
                if not key:
                    raise ParseError(lineno, "empty mapping key")
                rest = content[i + 1 :].strip()
                return key, (rest if rest else None)
        i += 1
    raise ParseError(lineno, f"expected 'key: value', got {content!r}")


def _strip_quotes(s: str) -> str:
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return _unquote(s[1:-1], '"')
    if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
        return s[1:-1].replace("''", "'")
    return s


# ---------------------------------------------------------------------------
# Flow parser
# ---------------------------------------------------------------------------


def parse_inline_value(text: str, lineno: int) -> Node:
    text = text.strip()
    if not text:
        return Scalar("", lineno)
    if text.startswith("{"):
        if not text.endswith("}"):
            raise ParseError(lineno, f"unterminated flow mapping: {text!r}")
        return _parse_flow_mapping(text, lineno)
    if text.startswith("["):
        if not text.endswith("]"):
            raise ParseError(lineno, f"unterminated flow sequence: {text!r}")
        return _parse_flow_sequence(text, lineno)
    if text in ("|", ">") or text.startswith(("|", ">")):
        raise ParseError(lineno, "block scalars (|/ >) are not supported")
    return Scalar(text, lineno)


def _parse_flow_mapping(text: str, lineno: int) -> Mapping:
    inner = text[1:-1].strip()
    items: list[tuple[str, Node]] = []
    if inner:
        for part in _split_top_level(inner, ","):
            part = part.strip()
            if not part:
                continue
            key, value = _split_flow_kv(part, lineno)
            items.append((key, parse_inline_value(value, lineno)))
    return Mapping(items, lineno)


def _parse_flow_sequence(text: str, lineno: int) -> Sequence:
    inner = text[1:-1].strip()
    items: list[Node] = []
    if inner:
        for part in _split_top_level(inner, ","):
            part = part.strip()
            if part == "":
                continue
            items.append(parse_inline_value(part, lineno))
    return Sequence(items, lineno)


def _split_top_level(text: str, sep: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    quote: str | None = None
    cur: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if quote:
            cur.append(c)
            if c == "\\" and i + 1 < n:
                cur.append(text[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in ('"', "'"):
            quote = c
            cur.append(c)
            i += 1
            continue
        if c in "{[":
            depth += 1
        elif c in "}]":
            depth -= 1
        if c == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
            i += 1
            continue
        cur.append(c)
        i += 1
    parts.append("".join(cur))
    return parts


def _split_flow_kv(part: str, lineno: int) -> tuple[str, str]:
    quote: str | None = None
    depth = 0
    i = 0
    n = len(part)
    while i < n:
        c = part[i]
        if quote:
            if c == "\\" and i + 1 < n:
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in ('"', "'"):
            quote = c
            i += 1
            continue
        if c in "{[":
            depth += 1
        elif c in "}]":
            depth -= 1
        elif c == ":" and depth == 0:
            key = _strip_quotes(part[:i].strip())
            if not key:
                raise ParseError(lineno, f"empty key in flow mapping: {part!r}")
            return key, part[i + 1 :].strip()
        i += 1
    raise ParseError(lineno, f"expected 'key: value' in flow mapping, got {part!r}")
