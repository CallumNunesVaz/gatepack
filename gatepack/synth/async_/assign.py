"""Stage 3 — race-free (single-variable-change) state assignment (§7.3).

Finds a map from states to bit-vectors such that every flow-table transition
changes exactly one bit.  This is a hypercube-embedding problem and is solved
with z3 (via :mod:`gatepack.synth.async_.smt`), not a heuristic:

* variables: one bit-vector per state, width ``w``;
* constraints: all assignments distinct; for every transition ``s -> t`` the
  Hamming distance between ``code(s)`` and ``code(t)`` is exactly 1;
* start at ``w = ceil(log2(n))``, widen on UNSAT up to a stated cap.

Widening ``w`` is the textbook way to buy race-freedom (spare rows), so a design
that needs 4 bits for 5 states is a normal outcome, not a failure — the width
used is reported.  If UNSAT at the cap, the backend refuses and names a minimal
set of conflicting transitions (a deletion-based minimal-unsat-subset), so the
refusal reads "S2->S4 and S2->S5 both need to be one bit from S2 ..." rather
than "no assignment exists".
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence

from gatepack.frontend.errors import AsyncRefused
from gatepack.synth.async_ import smt
from gatepack.synth.async_.flowtable import FlowTable

#: Upper bound on the assignment width.  A hypercube of width ``w`` gives each
#: state ``w`` neighbours, so any embedding needs ``w >= max out-degree``; with
#: the stage-1 cap of 16 states that is at most 15.  The cap is stated (not
#: magic): widening past it buys nothing a sane design can use, and keeps the
#: UNSAT path from widening forever.
ASYNC_WIDTH_CAP = 16


@dataclass(frozen=True)
class Assignment:
    """A single-variable-change state assignment."""

    codes: Mapping[str, int]
    width: int

    def bit(self, state: str, index: int) -> int:
        return (self.codes[state] >> index) & 1


def minimum_width(state_count: int) -> int:
    """The smallest encoding width worth trying: ``ceil(log2(n))`` (at least 1)."""
    if state_count <= 1:
        return 1
    return max(1, math.ceil(math.log2(state_count)))


def assign_state_codes(
    table: FlowTable,
    runner,
    workdir: str = ".",
    design_name: str = "",
    max_width: int = ASYNC_WIDTH_CAP,
) -> Assignment:
    """Find an SVC assignment, widening ``w`` from the minimum up to ``max_width``.

    Raises :class:`AsyncRefused` when no assignment exists within the cap (naming
    the conflicting transitions) or when z3 is unavailable
    (:class:`smt.SolverError` propagates as an ``AsyncRefused``).
    """
    states = table.states
    transitions = table.transitions
    width = minimum_width(len(states))
    while width <= max_width:
        script = build_script(states, transitions, width)
        try:
            result = smt.solve(script, runner, workdir, f"assign_w{width}")
        except smt.SolverError as exc:
            raise AsyncRefused(
                f"asynchronous design {design_name!r} refused: {exc}"
            ) from exc
        if result.sat:
            codes = {s: result.values[_var(s)] for s in states}
            return Assignment(codes=codes, width=width)
        width += 1

    conflicts = _minimal_conflicts(
        states, transitions, max_width, runner, workdir
    )
    named = ", ".join(
        f"{src}->{dst}" for src, dst in sorted(conflicts)
    )
    raise AsyncRefused(
        f"asynchronous design {design_name!r} refused: no single-variable-change "
        f"state assignment exists within width {max_width}. Conflicting "
        f"transitions (a minimal unsatisfiable subset): {named}."
    )


def _var(state: str) -> str:
    return f"s_{state}"


def build_script(
    states: Sequence[str],
    transitions: Sequence[tuple[str, str]],
    width: int,
) -> str:
    """The canonical SMT-LIB2 script for the SVC problem (byte-deterministic)."""
    lines = [smt.script_header()]
    for state in states:
        lines.append(f"(declare-const {_var(state)} (_ BitVec {width}))")
    if len(states) > 1:
        lines.append(f"(assert (distinct {' '.join(_var(s) for s in states)}))")
    for index, (source, target) in enumerate(transitions):
        lines.extend(_hamming_one(_var(source), _var(target), width, f"d{index}"))
    lines.append("(check-sat)")
    lines.append(f"(get-value ({' '.join(_var(s) for s in states)}))")
    return "\n".join(lines) + "\n"


def _hamming_one(a: str, b: str, width: int, tmp: str) -> list[str]:
    """Assert the Hamming distance between bit-vectors ``a`` and ``b`` is 1."""
    return [
        f"(declare-const {tmp} (_ BitVec {width}))",
        f"(assert (= {tmp} (bvxor {a} {b})))",
        f"(assert (distinct {tmp} (_ bv0 {width})))",
        f"(assert (= (bvand {tmp} (bvsub {tmp} (_ bv1 {width}))) (_ bv0 {width})))",
    ]


def _minimal_conflicts(
    states: Sequence[str],
    transitions: Sequence[tuple[str, str]],
    width: int,
    runner,
    workdir: str,
) -> tuple[tuple[str, str], ...]:
    """A deletion-based minimal unsatisfiable subset of the transition constraints."""
    essential = list(transitions)
    index = 0
    while index < len(essential):
        candidate = essential[:index] + essential[index + 1:]
        if _unsat(states, candidate, width, runner, workdir):
            essential = candidate  # removing it kept UNSAT -> not essential
        else:
            index += 1
    return tuple(essential)


def _unsat(
    states: Sequence[str],
    transitions: Sequence[tuple[str, str]],
    width: int,
    runner,
    workdir: str,
) -> bool:
    script = build_script(states, transitions, width)
    result = smt.solve(script, runner, workdir, f"assign_probe_w{width}")
    return not result.sat
