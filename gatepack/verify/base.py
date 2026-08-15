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
from typing import Protocol, Sequence


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
    golden_json: str = "build/golden.json"
    testbench_v: str = "build/exhaustive_tb.v"
    exhaustive_cap: int = 1 << 24  # §21.4: ~2^24 vectors is the tractable bound
    induction_steps: int = 64  # §21.5 default k, overridable (max(2*states, 64))
    cwd: str = "."


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: CheckStatus
    detail: str = ""
    bound: int | None = None  # set only when status is BOUNDED_PASS


@dataclass
class MutationOutcome:
    mutation: str
    detected: bool
    detail: str = ""


@dataclass
class VerificationReport:
    checks: list[CheckResult] = field(default_factory=list)
    mutations: list[MutationOutcome] = field(default_factory=list)

    @property
    def has_failure(self) -> bool:
        return any(c.status == CheckStatus.FAILED for c in self.checks) or any(
            not m.detected for m in self.mutations
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


class SubprocessRunner:
    """Default runner backed by :mod:`subprocess` (Yosys, Icarus, sby)."""

    def __init__(self, which=None) -> None:
        import shutil

        self._which = which or shutil.which

    def available(self, name: str) -> bool:
        return self._which(name) is not None

    def run(self, argv: Sequence[str], cwd: str, timeout: int = 600) -> ToolResult:
        import subprocess

        try:
            proc = subprocess.run(
                list(argv),
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return ToolResult(returncode=-1, stdout="", stderr=str(exc))
        return ToolResult(returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


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
