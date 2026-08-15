"""CPLD-hostile construct lint (§24.1).

§6's "Red" verdict recommends a flash CPLD as the fallback when a design is too
large for discrete packages.  §24.1 (and M0-FINDINGS' reading of it) observes
that the constraints that make RTL fit such a device — no memories, no latches,
no asynchronous logic, no surviving ``$_`` cells — are the ones the C3 script
*already* enforces ([R4-13], §9.2).  This module makes that enforcement explicit
rather than incidental: it inspects the generated behavioural Verilog and the
mapped netlist for constructs that would block a CPLD fallback and returns a
list of :class:`~gatepack.diagnostic.Diagnostic`.

The lint is a *blocker report*, never a build failure: a design that trips it is
still a valid discrete build, it just cannot take the §24.1 CPLD escape hatch.
Every diagnostic carries ``code=GP1009`` and ``severity=warning``.

Two detectors, kept separate so each is unit-testable in isolation:

* :func:`lint_verilog` — scans the generated behavioural Verilog text for memory
  declarations (register arrays) and latch-inferring combinational ``always``
  blocks.
* :func:`lint_netlist` — scans the mapped netlist for surviving ``$_`` internal
  cells (which would have to be a hard synthesis failure in a clean run) and for
  latch / memory cell types.
"""

from __future__ import annotations

import re
from typing import Sequence

from gatepack.diagnostic import GP_CPLD_BLOCKER, Diagnostic, warning
from gatepack.netlist import MappedNetlist

# Cell types that are memories in a Yosys netlist.  ``$mem`` is the abstract
# memory cell; ``$memrd``/``$memwr`` its read/write ports.  None survive a
# correct synchronous mapping (the C3 common front end asserts them away,
# [R4-13]).
_MEMORY_CELLS = frozenset({"$mem", "$mem_v2", "$memrd", "$memwr"})

# Latch cell types.  The C3 common front end asserts these away (§9.2 latch ban).
_LATCH_PREFIXES = ("$_DLATCH_", "$_SR_")

# A register *array* (memory) declaration: `reg [width] name [array];` — two
# bracket groups: the vector width after ``reg`` and the array bounds after the
# name.  A single bracket group is an ordinary vector (e.g. the binary/gray
# `state` register), which is fine for a CPLD.
_MEMORY_DECL = re.compile(r"\breg\s*\[[^\]]*\]\s*\w+\s*\[[^\]]*\]")

# `always` blocks whose sensitivity list has no clock edge (combinational) — the
# only place a latch can be inferred.
_COMB_ALWAYS = re.compile(r"\balways\s*@\s*(?:\(\s*\*?\s*\)|(?:\*\s*))")
_CLOCKED_ALWAYS = re.compile(r"\balways\s*@\s*\([^)]*\b(posedge|negedge)\b")


def lint_verilog(text: str, path: str = "generated.v") -> list[Diagnostic]:
    """Scan behavioural Verilog for CPLD-hostile constructs.

    Detects (a) memory declarations and (b) latch-inferring combinational
    ``always`` blocks — a combinational ``always`` containing an ``if`` with no
    matching ``else`` and no default assignment.  Both are coarse text heuristics:
    C1 never emits either, so the correct result on generated output is always an
    empty list; the detector exists so a *hostile* input cannot slip through.
    """
    blockers: list[Diagnostic] = []
    lines = text.splitlines()

    for lineno, line in enumerate(lines, 1):
        if _MEMORY_DECL.search(line):
            blockers.append(
                warning(
                    GP_CPLD_BLOCKER,
                    "memory declaration would block a CPLD fallback (§24.1): "
                    "no memories are permitted in a CPLD-targeted design",
                    path=path,
                    line=lineno,
                )
            )

    # Latch inference: a combinational `always` block with an `if` lacking an
    # `else` (and no default assignment).  Detected over the block body.
    blockers.extend(_latch_blockers(text, path))
    return blockers


def _latch_blockers(text: str, path: str) -> list[Diagnostic]:
    blockers: list[Diagnostic] = []
    lines = text.splitlines()
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if _COMB_ALWAYS.search(line) and not _CLOCKED_ALWAYS.search(line):
            start = i + 1  # 1-based
            has_if = False
            has_else = False
            has_default = False
            depth = 0
            in_block = False
            j = i
            while j < n:
                body = lines[j]
                if "begin" in body:
                    in_block = True
                    depth += body.count("begin") - body.count("end")
                if in_block and re.search(r"\bif\s*\(", body):
                    has_if = True
                if in_block and re.search(r"\belse\b", body):
                    has_else = True
                if in_block and re.search(r"^\s*\w+\s*=", body) and "if" not in body:
                    has_default = True
                if "end" in body:
                    depth -= body.count("end")
                j += 1
                if in_block and depth <= 0:
                    break
            if has_if and not has_else and not has_default:
                blockers.append(
                    warning(
                        GP_CPLD_BLOCKER,
                        "combinational always block infers a latch (if without "
                        "else/default assignment) — a latch blocks a CPLD "
                        "fallback (§24.1)",
                        path=path,
                        line=start,
                    )
                )
            i = j
        else:
            i += 1
    return blockers


def lint_netlist(
    netlist: MappedNetlist | None, path: str = "mapped.json"
) -> list[Diagnostic]:
    """Scan a mapped netlist for surviving ``$_`` cells, latches and memories.

    A correct synchronous mapping leaves no ``$_``-prefixed cell at all (the C3
    backend maps everything to the 74AUP library).  Any such cell is both a
    synthesis failure and a CPLD blocker, so it is reported here with the cell
    name inline.
    """
    if netlist is None:
        return []
    blockers: list[Diagnostic] = []
    for cell in netlist.cells:
        ctype = cell.cell
        if ctype in _MEMORY_CELLS:
            blockers.append(
                warning(
                    GP_CPLD_BLOCKER,
                    f"mapped cell {cell.name!r} is a memory ({ctype}) — a memory "
                    f"blocks a CPLD fallback (§24.1)",
                    path=path,
                )
            )
        elif ctype.startswith(_LATCH_PREFIXES):
            blockers.append(
                warning(
                    GP_CPLD_BLOCKER,
                    f"mapped cell {cell.name!r} is a latch ({ctype}) — a latch "
                    f"blocks a CPLD fallback (§24.1, §9.2 latch ban)",
                    path=path,
                )
            )
        elif ctype.startswith("$"):
            blockers.append(
                warning(
                    GP_CPLD_BLOCKER,
                    f"mapped cell {cell.name!r} is a surviving internal cell "
                    f"({ctype}) — un-mapped internal cells are not implementable "
                    f"and block a CPLD fallback (§24.1, §C3)",
                    path=path,
                )
            )
    return blockers


def lint_cpld(
    verilog_text: str,
    netlist: MappedNetlist | None,
    verilog_path: str = "generated.v",
    netlist_path: str = "mapped.json",
) -> list[Diagnostic]:
    """Combine the Verilog and netlist detectors (§24.1).

    The correct result on a clean golden design is an empty list.  An empty
    result is therefore meaningful (nothing blocks the CPLD fallback), and a
    lint that can never fire would be worthless — see the negative tests.
    """
    return lint_verilog(verilog_text, verilog_path) + lint_netlist(
        netlist, netlist_path
    )


def cpld_alternative_flow() -> str:
    """The alternative flow that consumes ``generated.v`` (§24.1).

    Kept in one place so the report and the ``--json`` payload cannot drift.
    """
    return (
        "flash CPLD (e.g. MAX V) driven by the portable inferred Verilog in "
        "generated.v; the generated design uses no memories, latches, "
        "asynchronous logic or surviving internal cells"
    )


def blockers_summary(blockers: Sequence[Diagnostic]) -> str:
    """A one-line summary of a blocker list for the report."""
    if not blockers:
        return "none — generated.v is CPLD-portable (no memories, latches, async logic, or surviving internal cells)"
    return f"{len(blockers)} construct(s) block a CPLD fallback"


__all__ = [
    "cpld_alternative_flow",
    "blockers_summary",
    "lint_cpld",
    "lint_netlist",
    "lint_verilog",
]
