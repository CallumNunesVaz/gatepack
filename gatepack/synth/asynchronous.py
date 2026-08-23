"""AsynchronousBackend — the re-scoped §7.3 constrained asynchronous synthesis.

v0.1.0 now ships a *constrained* asynchronous backend, not a blanket refusal.
The three problems §7.3 left unsolved in general are not solved in general:
they are side-stepped by taking the sub-problem §7.3 itself sanctions — ≤3-literal
product terms and single-variable-change encodings — and by making
hazard-freedom an **independently verified property of the emitted netlist**
(stage 5), never an assumed consequence of how the netlist was built.

This backend does not go through Yosys: the cover is constructed in Python and
mapped directly to G-cells, and ABC never sees the netlist.  ``generate_script``
still refuses — it is the Yosys-script seam that belongs to the synchronous
backend — and the real work lives in :meth:`_synthesize`.

``_synthesize`` is **internal** by design.  It runs stages 1–4 and therefore
already holds a netlist, but it must never be a public entry point: the one rule
of the package (§7.3) is that an async netlist may not be obtained without
stage 5 (the independent hazard checks) having run and passed.  The public entry
point is :func:`gatepack.async_pipeline.run_async_pipeline`, which binds stages
1–4 to stage 5 structurally.
"""

from __future__ import annotations

from dataclasses import dataclass

from gatepack.frontend.errors import AsyncRefused
from gatepack.frontend.model import CompiledDesign
from gatepack.synth.async_ import (
    admit,
    assign_state_codes,
    build_covers,
    build_flow_table,
    check_admissibility,
    emit_netlist,
)
from gatepack.synth.async_.assign import Assignment
from gatepack.synth.async_.cover import CoverResult
from gatepack.synth.async_.emit import EmittedNetlist
from gatepack.synth.async_.flowtable import FlowTable
from gatepack.synth.base import SynthConfig, SynthesisBackend


@dataclass(frozen=True)
class AsyncSynthResult:
    """Everything the asynchronous backend produced, from flow table to netlist."""

    flow_table: FlowTable
    assignment: Assignment
    covers: CoverResult
    emitted: EmittedNetlist


class AsynchronousBackend(SynthesisBackend):
    """Constrained asynchronous synthesis: admit -> flow table -> SVC -> cover -> netlist."""

    def generate_script(self, config: SynthConfig) -> str:
        raise AsyncRefused(
            "asynchronous synthesis is not driven through Yosys: the "
            "AsynchronousBackend synthesises in pure Python (stages 1-4, §7.3 "
            "re-scoped into v0.1.0) via synthesize(); generate_script() is the "
            "Yosys-script seam of the SynchronousBackend only."
        )

    def _synthesize(
        self,
        compiled: CompiledDesign,
        runner,
        workdir: str = ".",
    ) -> AsyncSynthResult:
        """Run the four synthesis stages and emit a mapped netlist (internal).

        Every stage that can refuse does so with a reason naming the specific
        construct; the result is never emitted past a refusal.

        This is the stages 1–4 half only.  It returns a result that already
        contains a netlist, so it is deliberately **not** public: call
        :func:`gatepack.async_pipeline.run_async_pipeline` instead, which runs
        stage 5 on that netlist and only then hands it back.
        """
        admit(compiled.design)  # stage 1
        table = build_flow_table(compiled)  # stage 2
        check_admissibility(compiled, table)  # stage 2
        assignment = assign_state_codes(
            table, runner, workdir=workdir, design_name=compiled.design.name
        )  # stage 3
        covers = build_covers(compiled, table, assignment, runner, workdir)  # stage 4
        emitted = emit_netlist(compiled, assignment, covers)  # stage 4 tail
        return AsyncSynthResult(
            flow_table=table,
            assignment=assignment,
            covers=covers,
            emitted=emitted,
        )
