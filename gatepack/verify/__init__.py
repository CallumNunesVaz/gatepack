"""C4 verification (§12) — equivalence, exhaustive simulation, mutation.

The strategy boundary mirrors :mod:`gatepack.synth` (§7): the timing model
selects a :class:`~gatepack.verify.base.VerificationStrategy`.  v0.1.0 ships only
:class:`~gatepack.verify.synchronous.SynchronousVerify`; the asynchronous
strategy refuses cleanly (§7.3).
"""

from gatepack.verify import equivalence, mutation, simulation
from gatepack.verify.asynchronous import AsynchronousVerify
from gatepack.verify.base import (
    CheckResult,
    CheckStatus,
    Counterexample,
    MutationOutcome,
    SubprocessRunner,
    ToolResult,
    VerificationReport,
    VerificationStrategy,
    VerifyConfig,
)
from gatepack.verify.synchronous import SynchronousVerify

__all__ = [
    "AsynchronousVerify",
    "CheckResult",
    "CheckStatus",
    "Counterexample",
    "MutationOutcome",
    "SubprocessRunner",
    "SynchronousVerify",
    "ToolResult",
    "VerificationReport",
    "VerificationStrategy",
    "VerifyConfig",
    "equivalence",
    "mutation",
    "simulation",
]
