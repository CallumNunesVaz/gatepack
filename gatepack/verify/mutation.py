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


# The ``DFF_R`` cell as C2 emits it in both artefacts.  These anchors are shared
# by the reset-family mutations below so each one corrupts exactly the reset
# path and nothing else (``DFF_SR`` has a ``preset`` and an ``else if`` line,
# so neither anchor collides with it).
_DFF_R_FF = (
    '    ff (IQ, IQN) {\n'
    '      next_state : "D";\n'
    '      clocked_on : "CK";\n'
    '      clear : "!RST_N";\n'
    '    }'
)

_DFF_R_ALWAYS = (
    '  always @(posedge CK or negedge RST_N) begin\n'
    "    if (!RST_N) Q <= 1'b0;\n"
    '    else Q <= D;\n'
    '  end'
)

# The ``DFF_SR`` cell as C2 emits it in both artefacts.  These anchors are the
# mirror image of ``_DFF_R_FF``/``_DFF_R_ALWAYS``: they capture the set path —
# the ``preset`` line in the ff group and the ``else if (!SET_N)`` line in the
# always block — so each set-path mutation corrupts exactly the set and nothing
# else.  Neither anchor collides with ``DFF_R``: ``DFF_R`` has no ``preset`` and
# no ``else if``, so the reset family and the set family each keep their own.
_DFF_SR_FF = (
    '    ff (IQ, IQN) {\n'
    '      next_state : "D";\n'
    '      clocked_on : "CK";\n'
    '      clear : "!RST_N";\n'
    '      preset : "!SET_N";\n'
    '      clear_preset_var1 : "L";\n'
    '      clear_preset_var2 : "H";\n'
    '    }'
)

_DFF_SR_ALWAYS = (
    '  always @(posedge CK or negedge RST_N or negedge SET_N) begin\n'
    "    if (!RST_N) Q <= 1'b0;\n"
    "    else if (!SET_N) Q <= 1'b1;\n"
    '    else Q <= D;\n'
    '  end'
)


def _reset_never_asserts(lib: str, sim: str) -> tuple[str, str]:
    """Drop the async clear entirely, so the flop is a plain ``DFF``.

    Stands for the "somebody forgot to wire the reset" fault: the reset pin is
    present in the netlist but does nothing, so the flop never asserts it.
    Distinct from ``reset_polarity_flip``, which keeps a reset but inverts it.
    """
    return (
        lib.replace(
            _DFF_R_FF,
            '    ff (IQ, IQN) {\n'
            '      next_state : "D";\n'
            '      clocked_on : "CK";\n'
            '    }',
        ),
        sim.replace(
            _DFF_R_ALWAYS,
            '  always @(posedge CK) begin\n'
            '    Q <= D;\n'
            '  end',
        ),
    )


def _reset_becomes_synchronous(lib: str, sim: str) -> tuple[str, str]:
    """Move the clear inside the clock edge: async-assert becomes sync reset.

    Stands for the implementation error of gating the reset through the clock
    (a reset only sampled at ``posedge CK``) where §9.3 promises async-assert /
    sync-de-assert.  A check suite that cannot tell async from sync reset is not
    verifying that promise.
    """
    return (
        lib.replace(
            _DFF_R_FF,
            '    ff (IQ, IQN) {\n'
            '      next_state : "(RST_N & D)";\n'
            '      clocked_on : "CK";\n'
            '    }',
        ),
        sim.replace(
            _DFF_R_ALWAYS,
            '  always @(posedge CK) begin\n'
            "    if (!RST_N) Q <= 1'b0;\n"
            '    else Q <= D;\n'
            '  end',
        ),
    )


def _reset_value_flips(lib: str, sim: str) -> tuple[str, str]:
    """Reset clears to 1 instead of 0 (the reset value is inverted).

    Stands for a wrong reset-value constant / a clear-preset confusion.  On the
    one-hot path every state bit clears to 0 on reset; a flop that instead
    asserts 1 on reset leaves the state register in a physically impossible
    encoding, which is observable only through the reset phase.
    """
    return (
        lib.replace(
            _DFF_R_FF,
            '    ff (IQ, IQN) {\n'
            '      next_state : "D";\n'
            '      clocked_on : "CK";\n'
            '      preset : "!RST_N";\n'
            '    }',
        ),
        sim.replace(
            _DFF_R_ALWAYS,
            '  always @(posedge CK or negedge RST_N) begin\n'
            "    if (!RST_N) Q <= 1'b1;\n"
            '    else Q <= D;\n'
            '  end',
        ),
    )


def _set_never_asserts(lib: str, sim: str) -> tuple[str, str]:
    """Drop the async preset entirely, so the set pin is a no-op.

    Stands for the "somebody forgot to wire the set" fault: the set pin is
    present in the netlist but does nothing, so the flop never asserts it.  The
    mirror of ``reset_never_asserts``: the cell degrades to a clear-only flop,
    leaving the reset path intact and only the set path missing.
    """
    return (
        lib.replace(
            _DFF_SR_FF,
            '    ff (IQ, IQN) {\n'
            '      next_state : "D";\n'
            '      clocked_on : "CK";\n'
            '      clear : "!RST_N";\n'
            '    }',
        ),
        sim.replace(
            _DFF_SR_ALWAYS,
            '  always @(posedge CK or negedge RST_N) begin\n'
            "    if (!RST_N) Q <= 1'b0;\n"
            '    else Q <= D;\n'
            '  end',
        ),
    )


def _set_becomes_synchronous(lib: str, sim: str) -> tuple[str, str]:
    """Move the preset inside the clock edge: async-assert set becomes sync set.

    Stands for gating the set through the clock (a set only sampled at
    ``posedge CK``) where §9.3 promises async-assert / sync-de-assert.  A suite
    that cannot tell an async set from a sync set is not verifying that
    promise.  The clear stays async; only the set path changes.
    """
    return (
        lib.replace(
            _DFF_SR_FF,
            '    ff (IQ, IQN) {\n'
            '      next_state : "(!SET_N | D)";\n'
            '      clocked_on : "CK";\n'
            '      clear : "!RST_N";\n'
            '    }',
        ),
        sim.replace(
            _DFF_SR_ALWAYS,
            '  always @(posedge CK or negedge RST_N) begin\n'
            "    if (!RST_N) Q <= 1'b0;\n"
            "    else if (!SET_N) Q <= 1'b1;\n"
            '    else Q <= D;\n'
            '  end',
        ),
    )


def _set_value_flips(lib: str, sim: str) -> tuple[str, str]:
    """Set presets to 0 instead of 1 (the set value is inverted).

    Stands for a wrong set-value constant / a set-clear confusion.  A flop that
    drives 0 when its set pin asserts leaves the state register in the wrong
    encoding, observable through the reset phase.  The mirror of
    ``reset_value_flips``, whose ``clear`` -> ``preset`` swap is reversed here
    as ``preset`` -> ``clear`` on the set pin; the reset path is untouched.

    The Liberty side folds both pins into the **one** ``clear`` expression
    rather than emitting a second ``clear`` line.  Two ``clear`` lines in one
    ``ff`` group is not valid Liberty; measured 2026-08-23, Yosys 0.23 imports
    it without complaint, which is worse than rejecting it — the mutation would
    then rest on whichever line the parser happened to keep, and if it kept the
    second one the mutation would be corrupting the *reset* path while claiming
    to corrupt the set path.  ``clear_preset_var*`` go with the ``preset`` they
    describe.
    """
    return (
        lib.replace(
            _DFF_SR_FF,
            '    ff (IQ, IQN) {\n'
            '      next_state : "D";\n'
            '      clocked_on : "CK";\n'
            '      clear : "(!RST_N) | (!SET_N)";\n'
            '    }',
        ),
        sim.replace(
            _DFF_SR_ALWAYS,
            '  always @(posedge CK or negedge RST_N or negedge SET_N) begin\n'
            "    if (!RST_N) Q <= 1'b0;\n"
            "    else if (!SET_N) Q <= 1'b0;\n"
            '    else Q <= D;\n'
            '  end',
        ),
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
    Mutation(
        name="reset_never_asserts",
        description="drop the async clear entirely (reset never asserts, flop is a plain DFF)",
        targets=("DFF_R",),
        mutate=_reset_never_asserts,
    ),
    Mutation(
        name="reset_becomes_synchronous",
        description="move the clear inside the clock edge (async-assert becomes sync reset)",
        targets=("DFF_R",),
        mutate=_reset_becomes_synchronous,
    ),
    Mutation(
        name="reset_value_flips",
        description="reset clears to 1 instead of 0 (inverted reset value)",
        targets=("DFF_R",),
        mutate=_reset_value_flips,
    ),
    Mutation(
        name="set_never_asserts",
        description="drop the async preset entirely (set never asserts, flop is clear-only)",
        targets=("DFF_SR",),
        mutate=_set_never_asserts,
    ),
    Mutation(
        name="set_becomes_synchronous",
        description="move the preset inside the clock edge (async-assert becomes sync set)",
        targets=("DFF_SR",),
        mutate=_set_becomes_synchronous,
    ),
    Mutation(
        name="set_value_flips",
        description="set presets to 0 instead of 1 (inverted set value)",
        targets=("DFF_SR",),
        mutate=_set_value_flips,
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
