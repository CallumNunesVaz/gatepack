"""The single entry point for constrained asynchronous synthesis (§7.3).

The one hard rule of the package: *"A netlist that is formally equivalent and
hazardous on the bench is the worst possible output of this tool."*  Concretely,
**no asynchronous netlist may be written to disk, returned to a caller, or
reported as a result unless stage 5 (the independent hazard checks) has run on
it and passed.**  This module makes that binding structural rather than a
convention:

* :func:`run_async_pipeline` runs stages 1–4 (synthesis) and then stage 5 (the
  hazard checks) — stage 5 is *not* optional and is *not* a separate call a
  future caller can forget.  It returns an :class:`AsyncPipelineResult` whose
  ``report`` is always available (so ``gatepack verify`` can report a failed
  check as a failed verification) but whose netlist is only obtainable through
  guarded accessors that raise :class:`HazardFailed` unless stage 5 passed.
* :class:`~gatepack.synth.asynchronous.AsynchronousBackend.synthesize` is
  demoted to ``_synthesize``: the stages 1–4 result (which already contains the
  raw netlist) is no longer reachable through a public method, so a caller
  cannot obtain an async netlist that has not been through stage 5.

Why a third module: :mod:`gatepack.verify.asynchronous` imports from
:mod:`gatepack.synth.async_`, so a pipeline that runs *both* synthesis and
verification cannot live inside either one without creating an import cycle.
It lives here, and both callers (``build`` and ``verify``) go through it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from gatepack.frontend.errors import AsyncRefused
from gatepack.frontend.model import CompiledDesign
from gatepack.netlist import MappedNetlist
from gatepack.synth.asynchronous import AsynchronousBackend
from gatepack.synth.async_.assign import Assignment
from gatepack.synth.async_.cover import CoverResult
from gatepack.synth.async_.emit import EmittedNetlist
from gatepack.synth.async_.flowtable import FlowTable
from gatepack.verify.asynchronous import AsynchronousVerify
from gatepack.verify.base import (
    CheckResult,
    CheckStatus,
    ToolRunner,
    VerificationReport,
    VerifyConfig,
)

#: The 5b (Icarus glitch) input is written under a *scratch* name, never the
#: deliverable ``mapped.v``, so a stage-5 failure leaves no netlist artefact in
#: a location a caller would mistake for a result.  ``write_artefacts`` writes
#: the deliverable ``mapped.v``/``mapped.json`` and is gated on a stage-5 pass.
_SCRATCH_VERILOG = "async_glitch_mapped.v"


class HazardFailed(AsyncRefused):
    """Stage 5 did not pass — the netlist must not be emitted, returned or reported.

    Subclasses :class:`~gatepack.frontend.errors.AsyncRefused` so the CLI's
    existing refusal path (exit code and diagnostic mapping) carries it, but the
    message names the specific failing check, never a flattened
    "asynchronous synthesis failed".
    """


@dataclass(frozen=True)
class AsyncPipelineResult:
    """Stages 1–4 plus stage 5, with the netlist gated on a passing stage 5.

    The synthesis products (flow table, assignment, covers) are exposed so the
    async report can state the assignment width and maximum product-term literal
    count honestly; the netlist itself is only reachable through the guarded
    accessors below.
    """

    flow_table: FlowTable
    assignment: Assignment
    covers: CoverResult
    report: VerificationReport
    _emitted: EmittedNetlist = field(repr=False, compare=False)

    @property
    def hazard_checks(self) -> tuple[CheckResult, ...]:
        """The stage-5 checks (ternary 5a and glitch 5b), each with its own status."""
        return tuple(self.report.checks)

    @property
    def hazard_passed(self) -> bool:
        """True only when stage 5 ran and *every* check passed.

        Never true on ``not run``, and — unlike a bare ``report.ok`` — never true
        on ``not applicable`` either: a functional check that could not enumerate
        has not measured "the netlist implements the design", so a netlist gated
        on it must not be emitted (§7.3, §21.4).
        """
        return all(c.status is CheckStatus.PASSED for c in self.report.checks)

    def _require_pass(self) -> None:
        if self.hazard_passed:
            return
        failing = [
            f"{c.name}: {c.status.value}" + (f" — {c.detail}" if c.detail else "")
            for c in self.report.checks
            if c.status is not CheckStatus.PASSED
        ]
        if not failing:
            failing = ["no hazard check ran"]
        raise HazardFailed(
            "asynchronous netlist refused: stage 5 hazard verification did not "
            "pass. " + "; ".join(failing)
        )

    def netlist(self) -> MappedNetlist:
        """The mapped netlist — raises :class:`HazardFailed` unless stage 5 passed."""
        self._require_pass()
        return self._emitted.netlist

    def mapped_verilog(self) -> str:
        """The mapped structural Verilog — raises unless stage 5 passed."""
        self._require_pass()
        return self._emitted.verilog

    def mapped_json(self) -> str:
        """The mapped netlist as Yosys ``write_json`` text — raises unless stage 5 passed."""
        self._require_pass()
        return self._emitted.json

    def write_artefacts(self, directory: str | Path) -> dict[str, Path]:
        """Write ``mapped.json``/``mapped.v`` — raises unless stage 5 passed.

        This is the only way the emitted netlist reaches disk.  It never writes
        on a failed, unrun or never-run stage 5.
        """
        self._require_pass()
        out = Path(directory)
        out.mkdir(parents=True, exist_ok=True)
        mapped_json = out / "mapped.json"
        mapped_v = out / "mapped.v"
        mapped_json.write_text(self._emitted.json)
        mapped_v.write_text(self._emitted.verilog)
        return {"mapped_json": mapped_json, "mapped_v": mapped_v}


def run_async_pipeline(
    compiled: CompiledDesign,
    runner: ToolRunner,
    workdir: str | Path,
    cell_functions: Mapping[str, str],
) -> AsyncPipelineResult:
    """Run stages 1–4 then stage 5 and return the result with a gated netlist.

    ``cell_functions`` maps G-cell names to their boolean function strings, read
    from the generated Liberty file via
    :func:`gatepack.verify.asynchronous.cell_functions_from_liberty`, so the
    hazard checker evaluates the *actual* library the netlist maps to rather
    than a hard-coded table.

    A refusal in stages 1–4 (admission, admissibility, no SVC assignment, a
    >3-literal term, or a missing z3) propagates as :class:`AsyncRefused` naming
    the construct.  A stage-5 *failure* does **not** raise here — the report
    carries it and the guarded accessors raise :class:`HazardFailed` — because
    ``verify`` must be able to report a failed check as a failed verification.
    """
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    synth = AsynchronousBackend()._synthesize(
        compiled, runner, workdir=str(workdir)
    )

    # Stage 5 needs the mapped Verilog on disk for 5b (Icarus); write it under a
    # scratch name so a failed stage 5 leaves no deliverable netlist artefact.
    scratch_v = workdir / _SCRATCH_VERILOG
    scratch_v.write_text(synth.emitted.verilog)

    config = VerifyConfig(
        top=compiled.design.name,
        mapped_json=str(workdir / "async_mapped.json"),
        mapped_v=str(scratch_v),
        cwd=".",
    )
    report = AsynchronousVerify().verify_netlist(
        synth.emitted.netlist, cell_functions, compiled, runner, config
    )

    return AsyncPipelineResult(
        flow_table=synth.flow_table,
        assignment=synth.assignment,
        covers=synth.covers,
        report=report,
        _emitted=synth.emitted,
    )


__all__ = [
    "AsyncPipelineResult",
    "HazardFailed",
    "run_async_pipeline",
]
