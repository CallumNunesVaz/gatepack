"""`gatepack doctor` — external-toolchain and bundled-resource self-check.

A packaged core has no host Python, no venv and no gatepack checkout; the one
thing it still needs from the host is the native EDA toolchain.  This module is
the single place that says, for each such tool, what it is for and whether it is
present (with a version, when the tool can report one).  It is deliberately a
*report*: nothing here raises, and a missing tool is a visible "missing" entry,
never a substituted result.

The bundled resources check exercises the same ``importlib.resources`` loads the
pipeline uses (``gatepack/yosys/common_frontend.ys`` and
``gatepack/macros/models/*.v``), so a bundle that lost its package data fails
this check instead of failing later, deep inside a synthesis run.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass

from gatepack import __version__


@dataclass(frozen=True)
class ToolSpec:
    """A required external tool: how to find it, what it is for, how to version it."""

    name: str
    purpose: str
    version_args: tuple[str, ...] = ("--version",)
    # True when gatepack invokes this tool directly (not just indirectly via a
    # wrapper such as sby -> smtbmc -> z3).
    direct: bool = True


# The tools gatepack shells out to today, plus the two that the design reserves
# for the async backend (espresso) and that sby reaches indirectly (z3).  Order
# matters: this is the report order and it is pinned by the contract test.
TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        "yosys",
        "logic synthesis (C3): behavioural Verilog -> mapped netlist",
        ("--version",),
    ),
    ToolSpec(
        "sby",
        "formal property checking + equivalence fallback (§11, §12 C4)",
        ("--version",),
    ),
    ToolSpec(
        "iverilog",
        "compiles the exhaustive-simulation testbench (Icarus, §12 C4)",
        ("-V",),
    ),
    ToolSpec(
        "vvp",
        "Icarus runtime: runs the compiled simulation testbench",
        ("-V",),
    ),
    ToolSpec(
        "z3",
        "SMT solver used by sby's smtbmc engine (reached indirectly)",
        ("--version",),
        direct=False,
    ),
    ToolSpec(
        "espresso",
        "two-level logic minimiser (async backend, v0.2; not in the sync path)",
        (),
        direct=False,
    ),
)


def _first_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _probe_version(name: str, version_args: tuple[str, ...]) -> str | None:
    """Run ``name version_args`` and return the first output line, or ``None``."""
    if not version_args:
        return None
    try:
        proc = subprocess.run(
            [name, *version_args],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return _first_line(proc.stdout) or _first_line(proc.stderr) or None


def _probe_tool(spec: ToolSpec) -> dict:
    path = shutil.which(spec.name)
    found = path is not None
    return {
        "name": spec.name,
        "found": found,
        "purpose": spec.purpose,
        "direct": spec.direct,
        "path": path,
        "version": _probe_version(spec.name, spec.version_args) if found else None,
    }


def _probe_resources() -> dict:
    """Confirm the bundled ``.ys`` and ``.v`` package data actually loads."""
    status: dict = {"commonFrontendYs": False, "mcellModels": False, "mcellCount": 0}
    try:
        from gatepack.yosys import load_common_frontend

        status["commonFrontendYs"] = bool(load_common_frontend().strip())
    except Exception:  # pragma: no cover - a bundle that lost its data
        pass
    try:
        from gatepack.macros import load_models, model_files

        status["mcellModels"] = bool(load_models().strip())
        status["mcellCount"] = len(model_files())
    except Exception:  # pragma: no cover - a bundle that lost its data
        pass
    return status


def run_doctor() -> dict:
    """Return the ``data`` payload for ``gatepack doctor --json``."""
    tools = [_probe_tool(spec) for spec in TOOLS]
    direct = [t for t in tools if t["direct"]]
    return {
        "version": __version__,
        "tools": tools,
        "resources": _probe_resources(),
        # "all tools present" means the ones gatepack invokes directly; the
        # indirect entries (z3, espresso) are reported but never gate this flag.
        "allToolsPresent": all(t["found"] for t in direct),
    }


__all__ = ["TOOLS", "ToolSpec", "run_doctor"]
