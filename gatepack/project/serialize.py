"""Deterministic YAML emitter for the ``.gpk`` single-file format (§10.4).

Hand-written, no dependency (the environment has no PyYAML).  It is the exact
inverse of :mod:`gatepack.frontend.yaml_subset` on the emitted subset, so that
``parse(dumps(x)) == x`` and ``dumps(parse(y)) == y`` hold on canonical text:

* mapping keys are emitted ``gatepack`` first, ``kind`` second, then the rest
  sorted (byte-determinism, §C6);
* sequences preserve order — order is semantic for ``states``, ``rows`` and
  friends;
* scalars are quoted only when a plain form would not round-trip, so expressions
  like ``!(a & b) | c``, ``arm & !fault`` and ``state == RUNNING`` survive exactly;
* no timestamps, no comments, no anchors, no block scalars.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

_SAFE_PLAIN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./-]*$")
_RESERVED = frozenset({"true", "false", "null", "~"})
_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\n": "\\n",
    "\t": "\\t",
    "\r": "\\r",
    "\0": "\\0",
}


def dumps_documents(documents: Sequence[Mapping[str, Any]]) -> str:
    """Emit a multi-document ``.gpk`` stream (``%YAML 1.2`` + ``---`` separators).

    Each ``documents`` entry must already carry its own ``gatepack``/``kind``
    keys (see :func:`document_dict`).
    """
    lines = ["%YAML 1.2"]
    for doc in documents:
        lines.append("---")
        lines.extend(_block_mapping(doc, 0, top=True))
    return "\n".join(lines) + "\n"


def dumps_mapping(mapping: Mapping[str, Any]) -> str:
    """Emit a single sorted-key mapping (used for the exploded ``design.yaml``)."""
    return "\n".join(_block_mapping(mapping, 0, top=False)) + "\n"


def document_dict(data: Mapping[str, Any], kind: str) -> dict:
    """Return a tagged document mapping (``gatepack`` first, then ``kind``)."""
    doc = {"gatepack": 1, "kind": kind}
    doc.update(data)
    return doc


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (bool, int, float, str))


def _all_scalars(value: Any) -> bool:
    if isinstance(value, dict):
        return all(_is_scalar(item) for item in value.values())
    if isinstance(value, list):
        return all(_is_scalar(item) for item in value)
    return True


def _ordered_keys(mapping: Mapping[str, Any], top: bool) -> list[str]:
    if top:
        ordered = [k for k in ("gatepack", "kind") if k in mapping]
        rest = [k for k in sorted(mapping) if k not in ("gatepack", "kind")]
        return ordered + rest
    return sorted(mapping)


def _block_mapping(mapping: Mapping[str, Any], level: int, top: bool) -> list[str]:
    lines: list[str] = []
    pad = "  " * level
    for key in _ordered_keys(mapping, top):
        value = mapping[key]
        if isinstance(value, dict) and not _all_scalars(value):
            lines.append(f"{pad}{_dump_string(key)}:")
            lines.extend(_block_mapping(value, level + 1, top=False))
        elif isinstance(value, list) and not _all_scalars(value):
            lines.append(f"{pad}{_dump_string(key)}:")
            lines.extend(_block_sequence(value, level + 1))
        else:
            lines.append(f"{pad}{_dump_string(key)}: {_inline(value)}")
    return lines


def _block_sequence(items: Sequence[Any], level: int) -> list[str]:
    lines: list[str] = []
    pad = "  " * level
    for item in items:
        if isinstance(item, dict) and not _all_scalars(item):
            lines.append(f"{pad}-")
            lines.extend(_block_mapping(item, level + 1, top=False))
        elif isinstance(item, list) and not _all_scalars(item):
            lines.append(f"{pad}-")
            lines.extend(_block_sequence(item, level + 1))
        else:
            lines.append(f"{pad}- {_inline(item)}")
    return lines


def _inline(value: Any) -> str:
    if _is_scalar(value):
        return _scalar(value)
    if isinstance(value, dict):
        return _flow_mapping(value)
    if isinstance(value, list):
        return _flow_sequence(value)
    raise TypeError(f"cannot emit YAML for {type(value).__name__}: {value!r}")


def _flow_mapping(mapping: Mapping[str, Any]) -> str:
    inner = ", ".join(
        f"{_dump_string(key)}: {_scalar(value)}"
        for key, value in ((k, mapping[k]) for k in sorted(mapping))
    )
    return "{" + inner + "}"


def _flow_sequence(items: Sequence[Any]) -> str:
    return "[" + ", ".join(_scalar(item) for item in items) + "]"


def _scalar(value: Any) -> str:
    if value is None:
        return "~"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return _dump_string(value)
    raise TypeError(f"cannot emit YAML for {type(value).__name__}: {value!r}")


def _dump_string(s: str) -> str:
    if s == "":
        return '""'
    if _plain_safe(s):
        return s
    return '"' + "".join(_ESCAPES.get(c, c) for c in s) + '"'


def _plain_safe(s: str) -> bool:
    if not _SAFE_PLAIN.match(s):
        return False
    if s in _RESERVED:
        return False
    return not _looks_numeric(s)


def _looks_numeric(s: str) -> bool:
    try:
        int(s)
        return True
    except ValueError:
        pass
    try:
        float(s)
        return True
    except ValueError:
        return False
