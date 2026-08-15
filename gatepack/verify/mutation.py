"""Mutation testing (§C4.4, R2, §19 R2).

Inject a deliberate fault — swap NAND for AND, invert a flop's D input, flip a
reset polarity — and assert that the equivalence and exhaustive-simulation checks
**fail**.  This is the only thing distinguishing a real proof from a
misconfiguration: an equivalence check that passes vacuously is worse than no
check, because it survives review.

Mutations are pure text transforms on the generated ``cells.lib`` and
``cells_sim.v``.  A mutation is *detected* only when **both** checks fail; if
either still passes, the mutation is **undetected** and the build must fail
(R2, R18).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from gatepack.verify.base import CheckStatus, MutationOutcome

MutationFn = Callable[[str, str], tuple[str, str]]


@dataclass(frozen=True)
class Mutation:
    name: str
    description: str
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
        mutate=_nand_to_and,
    ),
    Mutation(
        name="flop_d_invert",
        description="invert every flop's D input",
        mutate=_flop_d_invert,
    ),
    Mutation(
        name="reset_polarity_flip",
        description="flip the async reset polarity (active-low -> active-high)",
        mutate=_reset_polarity_flip,
    ),
)


def is_detected(equivalence: CheckStatus, simulation: CheckStatus) -> bool:
    """A mutation is caught only when *both* checks fail (§C4.4)."""
    return equivalence is CheckStatus.FAILED and simulation is CheckStatus.FAILED


def run_mutation_suite(
    mutations: Sequence[Mutation],
    lib_text: str,
    sim_text: str,
    run_equivalence,
    run_simulation,
) -> list[MutationOutcome]:
    """Inject each mutation and assert both checks fail.

    ``run_equivalence(lib_text)`` and ``run_simulation(sim_text)`` return a
    :class:`~gatepack.verify.base.CheckStatus`; they are injected so the suite is
    unit-testable without Yosys/Icarus.
    """
    outcomes: list[MutationOutcome] = []
    for mutation in mutations:
        mutated_lib, mutated_sim = mutation.mutate(lib_text, sim_text)
        if mutated_lib == lib_text and mutated_sim == sim_text:
            outcomes.append(
                MutationOutcome(
                    mutation.name,
                    detected=False,
                    detail="mutation did not change either artefact (not applicable)",
                )
            )
            continue
        equiv = run_equivalence(mutated_lib)
        sim = run_simulation(mutated_sim)
        detected = is_detected(equiv, sim)
        outcomes.append(
            MutationOutcome(
                mutation.name,
                detected=detected,
                detail=f"equivalence={equiv.value}, simulation={sim.value}",
            )
        )
    return outcomes
