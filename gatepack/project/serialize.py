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


def dumps_documents_with_design_source(
    design_source: str, documents: Sequence[Mapping[str, Any]]
) -> str:
    """Emit a ``.gpk`` stream whose first document carries ``design_source`` verbatim.

    ``design_source`` is the exact ``design.yaml`` text; it is emitted after the
    ``gatepack``/``kind`` header so comments and key order survive (§10.4
    "contained in a single file **as source**").  ``documents`` are the
    remaining (truth table / library) tagged mappings, in order.
    """
    chunks: list[str] = ["%YAML 1.2", "---", design_document(design_source)]
    for doc in documents:
        chunks.append("---")
        chunks.append("\n".join(_block_mapping(doc, 0, top=True)))
    return "\n".join(chunks) + "\n"


def design_document(design_source: str) -> str:
    """Render a design document: ``gatepack``/``kind`` header + verbatim source.

    A single trailing newline is normalised away here and restored by the stream
    joiner in :func:`dumps_documents_with_design_source`, so the emitted source
    matches the original text byte-for-byte when it ended in a newline.
    """
    body = design_source
    if body.endswith("\n"):
        body = body[:-1]
    return f"gatepack: 1\nkind: design\n{body}"


def split_documents(text: str) -> list[str]:
    """Split raw ``.gpk`` text into document bodies (separators/directives removed).

    Line endings and comments are preserved, so the design document's verbatim
    source can be recovered by :func:`design_source`.  A document whose only
    content is blank/comment lines is dropped, mirroring
    :func:`gatepack.frontend.yaml_subset.parse_documents` so the two lists stay
    aligned one-to-one.
    """
    documents: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if any(_has_content(line) for line in current):
            documents.append("".join(current))
        current.clear()

    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped in ("---", "..."):
            flush()
            continue
        if stripped.startswith("%"):
            continue
        current.append(line)
    flush()
    return documents


def design_source(body: str) -> str:
    """Recover the verbatim ``design.yaml`` text from a raw design document body.

    The body is ``gatepack: 1`` / ``kind: design`` followed by the original
    text; everything after the ``kind`` header line is returned unchanged.
    """
    out: list[str] = []
    seen_kind = False
    for line in body.splitlines(keepends=True):
        stripped = line.strip()
        if not seen_kind:
            if stripped.startswith("kind:"):
                seen_kind = True
            continue
        out.append(line)
    return "".join(out)


def document_dict(data: Mapping[str, Any], kind: str) -> dict:
    """Return a tagged document mapping (``gatepack`` first, then ``kind``)."""
    doc = {"gatepack": 1, "kind": kind}
    doc.update(data)
    return doc


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (bool, int, float, str))


def _has_content(line: str) -> bool:
    """True when a raw document line is not blank and not purely a comment."""
    stripped = line.strip()
    return stripped != "" and not stripped.startswith("#")


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
