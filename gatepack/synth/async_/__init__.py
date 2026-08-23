"""Asynchronous synthesis stages (§7.3, re-scoped into v0.1.0).

Five separable stages, one module each so every one is testable in isolation —
stage 5 (the hazard verifier, in :mod:`gatepack.verify.hazard`) must be able to
run without importing any of the synthesis stages' data structures:

* :mod:`~gatepack.synth.async_.admit` — stage 1, admission (refusals only);
* :mod:`~gatepack.synth.async_.flowtable` — stage 2, primitive flow table;
* :mod:`~gatepack.synth.async_.assign` — stage 3, SVC state assignment (z3);
* :mod:`~gatepack.synth.async_.cover` — stage 4, hazard-free cover (z3);
* :mod:`~gatepack.synth.async_.emit` — stage 4 tail, mapped-netlist emission.
"""

from gatepack.synth.async_.admit import ASYNC_STATE_CAP, admit
from gatepack.synth.async_.assign import Assignment, assign_state_codes
from gatepack.synth.async_.cover import CoverResult, FunctionCover, build_covers
from gatepack.synth.async_.emit import EmittedNetlist, emit_netlist
from gatepack.synth.async_.flowtable import FlowTable, build_flow_table, check_admissibility

__all__ = [
    "ASYNC_STATE_CAP",
    "Assignment",
    "CoverResult",
    "EmittedNetlist",
    "FlowTable",
    "FunctionCover",
    "admit",
    "assign_state_codes",
    "build_covers",
    "build_flow_table",
    "check_admissibility",
    "emit_netlist",
]
