"""Reset-connectivity check (§9.5).

Discrete logic has no internal power-on reset: every flop comes up undefined.
This check scans the C1-emitted behavioural Verilog for sequential ``always``
blocks that have no reset edge — i.e. flops that would come up undefined and
stay undefined.  It inspects the *emitted text*, not C1's internal model, so a
front-end regression that drops a reset is caught independently of the generator.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_ALWAYS = re.compile(r"always\s*@\s*\(")
_NONBLOCK = re.compile(r"\b(\w+)\s*<=")


@dataclass(frozen=True)
class AlwaysBlock:
    sensitivity: str
    body: str


def _blocks(verilog: str) -> list[AlwaysBlock]:
    blocks: list[AlwaysBlock] = []
    i = 0
    n = len(verilog)
    while True:
        m = _ALWAYS.search(verilog, i)
        if m is None:
            break
        sens_start = m.end()
        depth = 1
        j = sens_start
        while j < n:
            if verilog[j] == "(":
                depth += 1
            elif verilog[j] == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        sensitivity = verilog[sens_start:j]
        k = j + 1
        # find the body's `begin` … matching `end`
        begin = verilog.find("begin", k)
        if begin == -1:
            break
        p = begin + len("begin")
        bdepth = 1
        q = p
        while q < n and bdepth > 0:
            if verilog.startswith("begin", q):
                bdepth += 1
                q += len("begin")
            elif verilog.startswith("end", q):
                bdepth -= 1
                if bdepth == 0:
                    break
                q += len("end")
            else:
                q += 1
        body = verilog[p:q]
        blocks.append(AlwaysBlock(sensitivity=sensitivity, body=body))
        i = q
    return blocks


def find_unreset_flops(verilog: str) -> list[str]:
    """Return human-readable findings for sequential blocks lacking a reset edge.

    A sequential ``always`` block (nonblocking ``<=``) whose sensitivity list has
    exactly one clock edge — and no second ``posedge``/``negedge`` for a reset —
    describes a flop that is not reset-connected.
    """
    findings: list[str] = []
    for block in _blocks(verilog):
        edges = block.sensitivity.count("posedge") + block.sensitivity.count("negedge")
        if edges < 1:
            continue
        assigned = sorted({m.group(1) for m in _NONBLOCK.finditer(block.body)})
        if edges == 1:
            names = ", ".join(assigned) if assigned else "?"
            findings.append(
                f"flop(s) {names} are not reset-connected (no reset edge in "
                f"'always @({block.sensitivity.strip()})')"
            )
    return findings


def check_all_flops_reset_connected(verilog: str) -> list[str]:
    """§9.5 check 1: every flop must be reset-connected."""
    return find_unreset_flops(verilog)
