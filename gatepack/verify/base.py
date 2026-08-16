"""Verification strategy interface (§7, §12 C4).

Mirrors :class:`~gatepack.synth.base.SynthesisBackend`: the timing model selects
a :class:`VerificationStrategy`.  Both strategies share the C1 front-end, C2
Liberty/sim generation, C5/C6/C7/C8; they diverge only in *how* they verify.

The result model carries §21.5's distinct **"bounded pass"** state: a BMC bound
is never folded into a green tick (that would recreate the vacuous pass R2 and
R18 exist to prevent).  A fourth **"not run"** state distinguishes "the check
could not be executed (tool missing)" from "passed", and **"not applicable"**
distinguishes "exhaustive sim is above its runtime cap" (§21.4) — both are honest
non-verdicts, never green.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Protocol, Sequence

from gatepack.toolchain import ToolResult, ToolchainRunner

# ``SubprocessRunner`` is the historical name; the implementation now lives in
# :mod:`gatepack.toolchain` so every tool invocation goes through one module.
SubprocessRunner = ToolchainRunner


class CheckStatus(str, Enum):
    PASSED = "passed"
    BOUNDED_PASS = "bounded pass"  # §21.5: carries a bound; never a green tick
    FAILED = "failed"
    NOT_RUN = "not run"
    NOT_APPLICABLE = "not applicable"  # §21.4: sim above its runtime cap


@dataclass(frozen=True)
class VerifyConfig:
    """Paths and names a verification strategy needs (§12 C4)."""

    top: str
    generated_v: str = "build/generated.v"
    properties_sv: str = "build/properties.sv"
    cells_lib: str = "build/cells.lib"
    cells_sim_v: str = "build/cells_sim.v"
    premap_json: str = "build/premap.json"
    mapped_json: str = "build/mapped.json"
    mapped_v: str = "build/mapped.v"
    gold_v: str = "build/gold.v"
    gate_v: str = "build/mapped.v"
    golden_json: str = "build/golden.json"
    testbench_v: str = "build/exhaustive_tb.v"
    exhaustive_cap: int = 1 << 24  # §21.4: ~2^24 vectors is the tractable bound
    induction_steps: int = 64  # §21.5 default k, overridable (max(2*states, 64))
    cwd: str = "."


@dataclass(frozen=True)
class Counterexample:
    """A failing trace, selectable into the FSM graph and schematic (§15.2).

    ``steps`` holds one dict per cycle mapping signal name to ``'0'``/``'1'``/
    ``'x'``.  ``pointers`` holds the §15.1 provenance tokens for the spec
    constructs implicated in the trace.
    """

    steps: tuple[Mapping[str, str], ...]
    pointers: tuple[str, ...]


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: CheckStatus
    detail: str = ""
    bound: int | None = None  # set only when status is BOUNDED_PASS
    kind: str = ""  # equivalence|simulation|mutation|property|hazard (api.ts)
    duration_ms: int = 0
    counterexample: Counterexample | None = None


@dataclass
class MutationOutcome:
    mutation: str
    detected: bool
    detail: str = ""
    # False when the mutation targets a cell the design does not instantiate
    # (a category error, not a vacuity finding).  Such outcomes are reported
    # separately and do not count towards the vacuity verdict (R2, R18).
    applicable: bool = True


@dataclass
class VerificationReport:
    checks: list[CheckResult] = field(default_factory=list)
    mutations: list[MutationOutcome] = field(default_factory=list)

    @property
    def has_failure(self) -> bool:
        return any(c.status == CheckStatus.FAILED for c in self.checks) or any(
            m.applicable and not m.detected for m in self.mutations
        )

    @property
    def has_not_run(self) -> bool:
        return any(c.status == CheckStatus.NOT_RUN for c in self.checks)

    @property
    def ok(self) -> bool:
        """True only when nothing failed, nothing is unrun, and every mutation was
        detected — the honest "verified" verdict (§14, R2)."""
        return not self.has_failure and not self.has_not_run


@dataclass(frozen=True)
class ToolResult:
    returncode: int
    stdout: str
    stderr: str


class ToolRunner(Protocol):
    """Runs external tools; injected so the verify logic is testable without them."""

    def available(self, name: str) -> bool: ...

    def run(self, argv: Sequence[str], cwd: str, timeout: int = 600) -> ToolResult: ...


class VerificationStrategy(ABC):
    """Verification strategy interface (§7), mirroring ``SynthesisBackend``."""

    @abstractmethod
    def verify(
        self,
        config: VerifyConfig,
        compiled,
        runner: ToolRunner,
        lib_text: str,
        sim_text: str,
    ) -> VerificationReport:
        """Run every check for the timing model and return a report."""
