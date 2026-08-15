"""Exhaustive SAT-style checking of transition guards (§12 C1).

Guard overlap and transition-set exhaustiveness are checked by exhaustive
evaluation over the input space, *not* by syntactic inspection.  This is the
"small pure-Python SAT approach" §12 C1 permits: for each state we enumerate all
``2**n`` input assignments exactly once and, per assignment, record which guards
are true.  An assignment with no true guard is a coverage gap (non-exhaustive
transition set); an assignment with two or more true guards is non-determinism
(overlapping guards).

Limit: the number of free inputs is capped at ``MAX_EXHAUSTIVE_INPUTS`` (22),
i.e. at most ~4.2 million assignments per state.  Above that the front-end
refuses with a clear message rather than silently sampling — the design forbids
passing off partial coverage as a proof (§21.4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

from gatepack.frontend.expr import Expr, evaluate

MAX_EXHAUSTIVE_INPUTS = 22


class SatLimitError(ValueError):
    """The input space is too large for exhaustive checking."""


@dataclass
class GuardResult:
    """Outcome of checking one state's outgoing guards."""

    overlaps: list[tuple[int, int, dict[str, bool]]] = field(default_factory=list)
    gaps: list[dict[str, bool]] = field(default_factory=list)


def _assignments(inputs: Sequence[str]) -> Iterable[dict[str, bool]]:
    n = len(inputs)
    for code in range(1 << n):
        yield {name: bool(code & (1 << (n - 1 - i))) for i, name in enumerate(inputs)}


def check_state_guards(
    state: str,
    guards: Sequence[Expr],
    inputs: Sequence[str],
) -> GuardResult:
    """Check ``guards`` (already expanded to inputs only) for a single state.

    Returns a :class:`GuardResult` describing overlaps and coverage gaps.  An
    empty result means the transition set is total and deterministic.
    """
    n = len(inputs)
    if n > MAX_EXHAUSTIVE_INPUTS:
        raise SatLimitError(
            f"state {state!r} has {n} inputs; exhaustive guard checking is capped "
            f"at {MAX_EXHAUSTIVE_INPUTS} inputs (2**{MAX_EXHAUSTIVE_INPUTS} "
            f"assignments). Split the guard into named expressions or reduce the "
            f"input count."
        )

    result = GuardResult()
    for assignment in _assignments(inputs):
        true_indices = [
            i for i, guard in enumerate(guards) if evaluate(guard, assignment)
        ]
        if not true_indices:
            result.gaps.append(dict(assignment))
        elif len(true_indices) >= 2:
            result.overlaps.append(
                (true_indices[0], true_indices[1], dict(assignment))
            )
    return result


def format_assignment(assignment: dict[str, bool]) -> str:
    parts = [f"{name}={1 if value else 0}" for name, value in sorted(assignment.items())]
    return "{" + ", ".join(parts) + "}"
