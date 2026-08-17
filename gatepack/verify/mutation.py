"""Mutation testing (§C4.4, R2, §19 R2).

Inject a deliberate fault — swap NAND for AND, invert a flop's D input, flip a
reset polarity — and assert that the equivalence and exhaustive-simulation checks
**fail**.  This is the only thing distinguishing a real proof from a
misconfiguration: an equivalence check that passes vacuously is worse than no
check, because it survives review.

A mutation is *applicable* only when the mapped netlist actually instantiates
the cell type it corrupts.  ``nand_to_and`` on a design with no ``NAND2``, or
``flop_d_invert`` on a purely combinational design, is not a vacuity finding —
it is a category error.  Such mutations are reported ``not_applicable``, kept
out of the vacuity verdict, and never reported as "not detected".  A mutation
that **was** applied (the design uses the cell) and not detected remains a hard
failure (R2, R18).

Mutations are pure text transforms on the generated ``cells.lib`` and
``cells_sim.v``.  Both equivalence and simulation read ``cells_sim.v`` as the
behavioural model, so a corrupted model is seen by both.

Verdicts for an applied mutation:

* **detected** — equivalence *and* exhaustive simulation both fail: the fault
  is real and reaches a primary output, and both checks catch it.
* **equivalence only** — equivalence fails but exhaustive simulation passes.
  The fault is real and was caught, by the stronger of the two checks; the
  output-only simulation did not see it.  Not a vacuity finding, and reported
  under a name that says only what was observed.

  Two very different situations produce this verdict, and **the checker cannot
  tell them apart** — it sees two status values, nothing more:

  - the fault genuinely cannot reach a primary output in any reachable state
    (classical fault masking); or
  - the fault *can* reach an output, but in a phase the exhaustive simulation
    does not exercise.  §9.6 makes reset a setup step and checks outputs only
    at transition edges, so a reset-polarity fault is observable and unlooked
    for.  That is a coverage gap in the simulation, not a benign fault.

  Calling both of those "masked" would assert the first when the evidence only
  supports "equivalence caught it".  Establishing masking takes an argument
  about reachability that no status code carries, so the verdict names the
  observation and the distinction is left to whoever reads it.
* **undetected** — equivalence passes.  The full-state check did not catch the
  injected fault, so the checks are insensitive (or vacuous); this remains a
  hard failure (R2, R18).

If *every* applicable mutation is "equivalence only" and none is detected, the
suite has shown nothing about the exhaustive simulation at all — a simulation
that passed unconditionally would look exactly like that — so the check does
**not** pass (see ``simulation_was_exercised``).

Requiring *both* checks to fail before calling a mutation "detected" was the
original rule, and it is wrong: it reports a fault that equivalence alone
catches as if no check had caught it.  The honest distinction is between
*caught by equivalence only* and *not caught at all*.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Sequence

from gatepack.verify.base import CheckStatus, MutationOutcome

MutationFn = Callable[[str, str], tuple[str, str]]

_CELL_INSTANCE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s+_\d+_\s*\(", re.MULTILINE)


@dataclass(frozen=True)
class Mutation:
    name: str
    description: str
    targets: tuple[str, ...]
    mutate: MutationFn


def _nand_to_and(lib: str, sim: str) -> tuple[str, str]:
    return (
        lib.replace('function : "(!(A & B))";', 'function : "(A & B)";'),
        sim.replace("assign Y = (~(A & B));", "assign Y = (A & B);"),
    )


def _flop_d_invert(lib: str, sim: str) -> tuple[str, str]:
    return (
        lib.replace('next_state : "D";', 'next_state : "(!D)";'),
        sim.replace("Q <= D;", "Q <= (~D);"),
    )


def _reset_polarity_flip(lib: str, sim: str) -> tuple[str, str]:
    return (
        lib.replace('clear : "!RST_N";', 'clear : "RST_N";'),
        sim.replace("if (!RST_N) Q <= 1'b0;", "if (RST_N) Q <= 1'b0;"),
    )


MUTATIONS: tuple[Mutation, ...] = (
    Mutation(
        name="nand_to_and",
        description="swap NAND2 for AND2 (a wrong gate function)",
        targets=("NAND2",),
        mutate=_nand_to_and,
    ),
    Mutation(
        name="flop_d_invert",
        description="invert every flop's D input",
        targets=("DFF", "DFF_R", "DFF_SR", "DFF_S"),
        mutate=_flop_d_invert,
    ),
    Mutation(
        name="reset_polarity_flip",
        description="flip the async reset polarity (active-low -> active-high)",
        targets=("DFF_R", "DFF_SR"),
        mutate=_reset_polarity_flip,
    ),
)


def used_cells(mapped_v: str) -> set[str]:
    """Cell types instantiated in a ``write_verilog`` netlist."""
    return {m.group(1) for m in _CELL_INSTANCE.finditer(mapped_v)}


def is_applicable(mutation: Mutation, mapped_v: str) -> bool:
    """True when the mapped netlist instantiates a cell this mutation corrupts."""
    cells = used_cells(mapped_v)
    return any(t in cells for t in mutation.targets)


def is_detected(equivalence: CheckStatus, simulation: CheckStatus) -> bool:
    """A mutation is caught when *both* checks fail — the fault reaches an output."""
    return equivalence is CheckStatus.FAILED and simulation is CheckStatus.FAILED


def is_equivalence_only(equivalence: CheckStatus, simulation: CheckStatus) -> bool:
    """True when equivalence caught the fault and the simulation did not.

    Deliberately named for the observation rather than a cause: from two status
    values one cannot tell a fault that *cannot* reach an output from one the
    simulation never looks for.  See the module docstring.
    """
    return equivalence is CheckStatus.FAILED and simulation is CheckStatus.PASSED


def simulation_was_exercised(outcomes) -> bool:
    """True when some applicable mutation made the *simulation* fail.

    The mutation suite exists to prove the checks are not vacuous.  An
    "equivalence only" verdict proves that about equivalence and says nothing
    about the simulation — so if every applicable mutation lands there and none
    is detected, nothing has demonstrated the simulation can fail at all, which
    is indistinguishable from a simulation that passes unconditionally.
    """
    applicable = [o for o in outcomes if o.applicable]
    return not applicable or any(o.detected for o in applicable)


def run_mutation_suite(
    mutations: Sequence[Mutation],
    lib_text: str,
    sim_text: str,
    run_equivalence,
    run_simulation,
    mapped_v: str | None = None,
) -> list[MutationOutcome]:
    """Inject each mutation and assert both checks fail.

    ``run_equivalence(sim_text)`` and ``run_simulation(sim_text)`` return a
    :class:`~gatepack.verify.base.CheckStatus`; they are injected so the suite is
    unit-testable without Yosys/Icarus.  ``mapped_v`` (the ``write_verilog``
    netlist) is used to decide applicability; when ``None`` every mutation is
    treated as applicable (the unit-test default).
    """
    outcomes: list[MutationOutcome] = []
    for mutation in mutations:
        mutated_lib, mutated_sim = mutation.mutate(lib_text, sim_text)
        if mutated_lib == lib_text and mutated_sim == sim_text:
            outcomes.append(
                MutationOutcome(
                    mutation.name,
                    detected=False,
                    detail="mutation did not change either artefact",
                    applicable=False,
                )
            )
            continue
        if mapped_v is not None and not is_applicable(mutation, mapped_v):
            outcomes.append(
                MutationOutcome(
                    mutation.name,
                    detected=False,
                    detail=f"not applicable: design instantiates none of "
                    f"{', '.join(mutation.targets)}",
                    applicable=False,
                )
            )
            continue
        equiv = run_equivalence(mutated_sim)
        sim = run_simulation(mutated_sim)
        detected = is_detected(equiv, sim)
        equivalence_only = is_equivalence_only(equiv, sim)
        outcomes.append(
            MutationOutcome(
                mutation.name,
                detected=detected,
                equivalence_only=equivalence_only,
                detail=f"equivalence={equiv.value}, simulation={sim.value}",
                applicable=True,
            )
        )
    return outcomes
