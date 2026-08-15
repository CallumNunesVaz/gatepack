"""Formal equivalence (§12 C4, [R4-12], M0-FINDINGS §6).

The golden side runs through the *same* ``common_frontend.ys`` text C3 uses —
shared from that one file, never copied — and then stops before
``dfflegalize``/``dfflibmap``/``abc``.  That shared front end is what makes
k-induction close, because both sides keep identical state encodings ([R4-5]).

The script follows the **measured** M0 recipe, which added three steps the
design omitted and each of which is a hard failure:

1. ``cells_sim.v`` is read alongside the mapped netlist — without the
   behavioural models the mapped cells are undefined modules and ``equiv_make``
   dies with ``Module '\\INV' ... is not part of the design``.
2. ``async2sync`` runs on **both** sides — async-reset flops are ``$adff`` with
   no SAT model, so without it induction cannot close (§9.3 makes async-assert
   reset mandatory, so every design hits this).
3. ``proc`` is re-run after every Verilog round-trip, or the module "contains
   memories or processes".

The fallback ladder (``equiv_simple`` -> ``equiv_induct -seq N`` raised -> sby
miter) remains for escalation; the primary run uses the measured ``equiv_simple
; equiv_induct`` sequence.  The exact wording of ``equiv_status -assert`` output
is best-effort and MUST be confirmed against the pinned Yosys at M0 (Yosys is
not installed here); the script *generation* and result *parsing* are
unit-testable regardless.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from gatepack import yosys
from gatepack.verify.base import CheckStatus, VerifyConfig


class EquivStep(str, Enum):
    EQUIV_SIMPLE = "equiv_simple"
    EQUIV_INDUCT = "equiv_induct"
    SBY_MITER = "sby_miter"


@dataclass(frozen=True)
class EquivalenceOutcome:
    status: CheckStatus
    detail: str = ""
    bound: int | None = None


def default_induction_steps(state_count: int) -> int:
    """§21.5 default k: ``max(2 * state count, 64)``."""
    return max(2 * state_count, 64)


def induction_ladder(state_count: int) -> list[tuple[EquivStep, int | None]]:
    """The §C4 fallback ladder, with induction step raised between rungs."""
    base = default_induction_steps(state_count)
    return [
        (EquivStep.EQUIV_SIMPLE, None),
        (EquivStep.EQUIV_INDUCT, base),
        (EquivStep.EQUIV_INDUCT, base * 2),
        (EquivStep.SBY_MITER, None),
    ]


def golden_prep(config: VerifyConfig) -> str:
    """The golden side: the shared common front end, stopped before the split.

    This is literally ``yosys.common_frontend`` — the same text C3 uses — so the
    two cannot drift (§C4, R20).  It ends with ``write_json`` of the golden's
    pre-ABC state; there is no ``dfflegalize``/``dfflibmap``/``abc`` here.
    """
    return yosys.common_frontend(config.top, config.generated_v, config.golden_json)


def _equiv_commands(step: EquivStep, induction_steps: int | None) -> list[str]:
    if step is EquivStep.EQUIV_SIMPLE:
        return ["equiv_simple equiv", "equiv_status -assert equiv"]
    if step is EquivStep.EQUIV_INDUCT:
        induct = (
            f"equiv_induct -seq {induction_steps} equiv"
            if induction_steps is not None
            else "equiv_induct equiv"
        )
        return ["equiv_simple equiv", induct, "equiv_status -assert equiv"]
    raise ValueError("SBY_MITER is a separate construction, not a Yosys script")


def build_equivalence_script(
    config: VerifyConfig,
    step: EquivStep = EquivStep.EQUIV_INDUCT,
    induction_steps: int | None = None,
) -> str:
    """Emit the Yosys equivalence script following the measured M0 recipe."""
    lines = [
        golden_prep(config),
        "# --- golden side ready (shared front end, stopped before dfflegalize/dfflibmap/abc) ---",
        f"write_verilog -noattr {config.gold_v}",
        "design -reset",
        "# --- golden side, round-tripped: re-proc is mandatory after write_verilog ---",
        f"read_verilog {config.gold_v}",
        "proc; opt; async2sync; opt",
        "design -stash golden",
        "# --- gate side: mapped netlist + behavioural models (cells_sim.v is mandatory) ---",
        f"read_verilog {config.gate_v} {config.cells_sim_v}",
        "proc; flatten; opt; async2sync; opt",
        "design -stash mapped",
        "equiv_make golden mapped equiv",
        "prep -top equiv",
    ]
    lines.extend(_equiv_commands(step, induction_steps))
    return "\n".join(lines)


def build_sby_miter(config: VerifyConfig, bound: int) -> str:
    """Emit a hand-built miter + ``.sby`` config for BMC (last-resort fallback).

    BMC proves correctness only up to ``bound``; the result must therefore be a
    *bounded pass*, never a green pass (§21.5).  The miter renames the golden
    top to avoid the name clash with the mapped top; the exact form is
    best-effort and unverified against a real sby run (M0).  It reads the cell
    models and runs ``async2sync`` for the same reasons the equivalence recipe
    does (M0-FINDINGS §6).
    """
    return "\n".join(
        [
            "[options]",
            f"mode bmc",
            f"depth {bound}",
            "",
            "[engines]",
            "smtbmc z3",
            "",
            "[script]",
            f"read_verilog -sv {config.generated_v}",
            "proc; opt; async2sync; opt",
            "rename {top} golden",
            f"read_verilog {config.mapped_v} {config.cells_sim_v}",
            "proc; flatten; opt; async2sync; opt",
            "prep -top {top}",
            "miter -equiv golden {top} miter",
            "select -assert-none t:miter -non-equiv",
            "",
            "[files]",
            f"{config.generated_v}",
            f"{config.mapped_v}",
            f"{config.cells_sim_v}",
        ]
    ).replace("{top}", config.top)


def parse_equiv_status(stdout: str) -> EquivalenceOutcome:
    """Parse ``equiv_status``/``equiv_induct`` output into a verdict."""
    text = stdout.lower()
    if "equivalence successfully proven" in text or "equivalence proved" in text:
        return EquivalenceOutcome(CheckStatus.PASSED)
    if "equivalence check failed" in text or "counterexample" in text:
        return EquivalenceOutcome(CheckStatus.FAILED, "equivalence check failed")
    return EquivalenceOutcome(CheckStatus.NOT_RUN, "unrecognized equiv output")


def parse_sby_bmc(stdout: str, bound: int) -> EquivalenceOutcome:
    """Parse sby BMC output.  A BMC "PASS" is bounded — it proves nothing beyond
    ``bound`` — so it is reported as a distinct ``BOUNDED_PASS`` carrying the
    bound, never folded into a green pass (§21.5)."""
    text = stdout
    if "counterexample" in text.lower() or "FAIL" in text:
        return EquivalenceOutcome(CheckStatus.FAILED, "sby BMC found a counterexample")
    if "PASS" in text:
        return EquivalenceOutcome(
            CheckStatus.BOUNDED_PASS, f"BMC passed to depth {bound}", bound=bound
        )
    return EquivalenceOutcome(CheckStatus.NOT_RUN, "unrecognized sby output")
