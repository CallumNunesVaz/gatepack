"""Single injectable entry point for external tool invocation (Yosys, Icarus, sby).

Every tool call in gatepack goes through this module so that the *command line*
is a pure function of its inputs and can be asserted in tests without the
binary present.  Nothing here fakes a result: :class:`ToolchainRunner` is the
only thing that shells out, and it is injected everywhere a tool would run
(``run_verify``/``run_estimate`` and the verification strategy).

Command construction is separated from execution on purpose — the measured
recipe of M0 (§6) is pinned by asserting the exact command *text*, while the
actual run stays behind :class:`ToolchainRunner` so a missing binary reports
``not run`` rather than a fabricated pass.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class ToolResult:
    returncode: int
    stdout: str
    stderr: str


def yosys_command(script: str) -> list[str]:
    """The exact Yosys command line for a script (assertable without the binary)."""
    return ["yosys", "-p", script]


def iverilog_command(output: str, sources: Sequence[str]) -> list[str]:
    """The exact Icarus compile command line for a set of sources."""
    return ["iverilog", "-o", output, *list(sources)]


def vvp_command(vvp_path: str) -> list[str]:
    """The exact vvp (Icarus runtime) command line."""
    return ["vvp", vvp_path]


class ToolchainRunner:
    """Subprocess-backed runner; inject a fake in tests to avoid the binary."""

    def __init__(self, which=None) -> None:
        self._which = which or shutil.which

    def available(self, name: str) -> bool:
        return self._which(name) is not None

    def run(self, argv: Sequence[str], cwd: str, timeout: int = 600) -> ToolResult:
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
        return ToolResult(
            returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr
        )


__all__ = [
    "ToolResult",
    "ToolchainRunner",
    "iverilog_command",
    "vvp_command",
    "yosys_command",
]
