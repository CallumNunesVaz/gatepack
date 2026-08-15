"""Provenance spine (§15.1) — the net-based carrier, per M0-FINDINGS §3.

Measured survival through ``dfflegalize; dfflibmap; abc; clean``:

* cell attributes survive ``dfflibmap`` but **not** ``abc``;
* an attribute on a ``wire`` declaration attaches to the *net*, and net
  attributes survive ``abc`` **intact**.

The workable spine is therefore to attach ``gp_src`` to named nets in C1 (on
``wire``/``reg`` declarations, never on an ``assign`` — M0 §1) and, after
mapping, associate each mapped cell with source via the provenance of the nets
it connects to.  Pre-map capture plus structural matching remains a *secondary*
signal for cells whose nets were themselves optimised away.

This module holds the pure, testable part of that spine: extracting which named
nets carry ``gp_src`` from the emitted Verilog.  The mapped-cell association
(net -> cell -> source, with structural matching as fallback) is the M11b
deliverable and is deliberately **not** implemented here — it needs a real
``mapped.json`` from the pinned Yosys, and nothing in this environment
fabricates one.  Coverage is reported honestly: any consumer of this map must
distinguish "traced to a source line" from "no link", and never imply a
one-to-one that the netlist does not support (§15.1).
"""

from __future__ import annotations

import re

_ATTR = re.compile(r"\(\*\s*gp_src\s*=\s*\"([^\"]*)\"\s*\*\)")
_DECL = re.compile(r"^\s*(wire|reg)\s+(?:\[[^\]]*\]\s*)?([A-Za-z_][A-Za-z0-9_]*)\b")


def net_provenance(verilog: str) -> dict[str, str]:
    """Return ``{net_name: gp_src_value}`` for every named net carrying ``gp_src``.

    Only *declarations* are considered: a ``gp_src`` attribute attaches to the
    ``wire``/``reg`` declaration that follows it (M0 §1, §3).  An attribute that
    precedes anything else (a ``module`` header, for example) is ignored, and an
    attribute is never allowed to precede an ``assign``.
    """
    out: dict[str, str] = {}
    pending: str | None = None
    for raw in verilog.splitlines():
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        match = _ATTR.search(line)
        if match:
            pending = match.group(1)
            continue
        decl = _DECL.match(raw)
        if decl and pending is not None:
            out[decl.group(2)] = pending
        pending = None
    return out


__all__ = ["net_provenance"]
