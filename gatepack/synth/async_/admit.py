"""Stage 1 — admission (§7.3): refuse an asynchronous design before doing work.

The asynchronous backend is re-scoped into v0.1.0 by *constraining* the problem
(≤3-literal product terms, single-variable-change encodings), and every limit is
a refusal, not a best effort.  This module is the first gate: it declines a
design that cannot even be attempted, naming the specific construct that forced
the refusal.  A tool that declines with a reason is more useful than one that
hangs or silently mis-synthesises (§7.3).

Every refusal raises :class:`~gatepack.frontend.errors.AsyncRefused` so the CLI
keeps its ``async-refused`` exit code and the existing "asynchronous" wording in
the tests is preserved.
"""

from __future__ import annotations

from gatepack.frontend.errors import AsyncRefused
from gatepack.frontend.schema import Design

#: State-count cap for the asynchronous backend.  Stages 2 (flow table) and 3
#: (single-variable-change assignment) are both exponential in the number of
#: states — the flow table's columns grow with 2**n_inputs and stage 3's z3
#: problem grows with the transition set and the assignment width — so a design
#: above this cap is refused up front.  §7.3: "a tool that hangs is worse than
#: one that declines."
ASYNC_STATE_CAP = 16


def admit(design: Design) -> None:
    """Refuse an asynchronous design that cannot be synthesised, before any work.

    Checks, in order:

    * ``fundamental_mode`` present and ``mutually_exclusive`` non-empty — §7.2
      requires the designer to declare which inputs cannot change together;
      without it the whole method is unsound.
    * every declared input is covered by some mutual-exclusion group, and every
      group names a declared input.
    * no ``clock`` block — asynchronous synthesis is clockless.
    * state count at or below :data:`ASYNC_STATE_CAP`.
    """
    fm = design.fundamental_mode
    if fm is None:
        raise AsyncRefused(_refuse(design.name)(
            "fundamental_mode is required: §7.2 requires the designer to "
            "declare which inputs cannot change together, and without it the "
            "whole method is unsound"
        ))
    groups = fm.mutually_exclusive
    if not groups:
        raise AsyncRefused(_refuse(design.name)(
            "fundamental_mode.mutually_exclusive is empty: declare which inputs "
            "cannot change together (§7.2)"
        ))
    if design.clock is not None:
        raise AsyncRefused(_refuse(design.name)(
            f"a clock block (signal {design.clock.signal!r}) on an asynchronous "
            "design is refused: asynchronous synthesis is clockless (§7.3)"
        ))
    if len(design.states) > ASYNC_STATE_CAP:
        raise AsyncRefused(_refuse(design.name)(
            f"{len(design.states)} states exceed the asynchronous cap of "
            f"{ASYNC_STATE_CAP}: stages 2 and 3 are exponential in the state "
            "count, and a tool that hangs is worse than one that declines (§7.3)"
        ))
    declared = {p.name for p in design.inputs}
    covered: set[str] = set()
    for group in groups:
        for name in group:
            if name not in declared:
                raise AsyncRefused(_refuse(design.name)(
                    f"fundamental_mode.mutually_exclusive names input {name!r}, "
                    "which is not a declared input"
                ))
            covered.add(name)
    uncovered = declared - covered
    if uncovered:
        raise AsyncRefused(_refuse(design.name)(
            "input(s) not covered by a mutual-exclusion group: "
            f"{sorted(uncovered)!r} — every input must be declared in "
            "fundamental_mode (§7.2)"
        ))


def _refuse(name: str):
    """Return a refusal-message builder prefixed with the async design identity."""
    return lambda reason: f"asynchronous design {name!r} refused: {reason}"
