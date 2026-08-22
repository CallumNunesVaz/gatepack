"""`gatepack doctor` — external-toolchain and bundled-resource self-check.

A packaged core has no host Python, no venv and no gatepack checkout; the one
thing it still needs from the host is the native EDA toolchain.  This module is
the single place that says, for each such tool, what it is for and whether it is
present (with a version, when the tool can report one) — and, now that the
toolchain ships with the app (§17.1), **which copy** it found: the bundled one
or a system one.  It is deliberately a *report*: nothing here raises, and a
missing tool is a visible "missing" entry, never a substituted result.

The bundled resources check exercises the same ``importlib.resources`` loads the
pipeline uses (``gatepack/yosys/common_frontend.ys`` and
``gatepack/macros/models/*.v``), so a bundle that lost its package data fails
this check instead of failing later, deep inside a synthesis run.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass

from gatepack import __version__
from gatepack.toolchain import (
    ToolResolution,
    build_run_env,
    bundled_tool_versions,
    resolve_tool,
)


@dataclass(frozen=True)
class ToolSpec:
    """A required external tool: how to find it, what it is for, how to version it."""

    name: str
    purpose: str
    version_args: tuple[str, ...] = ("--version",)
    # True when gatepack invokes this tool directly (not just indirectly via a
    # wrapper such as sby -> smtbmc -> z3).
    direct: bool = True
    # Where a Windows user gets this tool, appended to ``purpose`` when
    # :func:`run_doctor` runs on Windows.  The native Windows build bundles no
    # toolchain, so "missing" alone would strand a user; this names the real
    # distribution instead.  Empty means "no Windows-specific guidance".
    windows_note: str = ""


# The tools gatepack shells out to today, plus the two that the design reserves
# for the async backend (espresso) and that sby reaches indirectly (z3).  Order
# matters: this is the report order and it is pinned by the contract test.
TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        "yosys",
        "logic synthesis (C3): behavioural Verilog -> mapped netlist",
        ("--version",),
        windows_note=(
            "install OSS CAD Suite (YosysHQ/oss-cad-suite-build) and put yosys "
            "on PATH, or run gatepack under WSL2"
        ),
    ),
    ToolSpec(
        "sby",
        "formal property checking + equivalence fallback (§11, §12 C4)",
        # sby has no ``--version`` flag; its version is the pinned source commit
        # and comes from the toolchain manifest when bundled (see
        # :func:`gatepack.toolchain.bundled_tool_versions`).
        (),
        windows_note=(
            "SymbiYosys ships with OSS CAD Suite (YosysHQ/oss-cad-suite-build); "
            "otherwise run gatepack under WSL2"
        ),
    ),
    ToolSpec(
        "iverilog",
        "compiles the exhaustive-simulation testbench (Icarus, §12 C4)",
        ("-V",),
        windows_note=(
            "Icarus Verilog for Windows (MSYS2 or an official build) on PATH, "
            "or run gatepack under WSL2"
        ),
    ),
    ToolSpec(
        "vvp",
        "Icarus runtime: runs the compiled simulation testbench",
        ("-V",),
        windows_note="ships with Icarus Verilog (the same distribution as iverilog)",
    ),
    ToolSpec(
        "z3",
        "SMT solver used by sby's smtbmc engine (reached indirectly)",
        ("--version",),
        direct=False,
        windows_note="ships with OSS CAD Suite; reached indirectly through sby",
    ),
    ToolSpec(
        "bash",
        "POSIX shell sby runs its engine steps through (/usr/bin/env bash) — a "
        "host requirement, never bundled",
        ("--version",),
        direct=False,
        windows_note=(
            "on native Windows there is no bash, so sby cannot run its engine "
            "steps; use WSL2 (bash is a POSIX host requirement, never bundled)"
        ),
    ),
    ToolSpec(
        "espresso",
        "two-level logic minimiser (async backend, v0.2; not in the sync path)",
        (),
        direct=False,
        windows_note="not in the sync path; build from source if the async backend needs it",
    ),
)


def is_windows(platform: str | None = None) -> bool:
    """True when running on (or asked to report for) Windows.

    ``platform`` is injectable so a test can exercise the Windows guidance on a
    POSIX host, the same pattern ``app/main/core.cts`` uses (``platform:
    'win32'``).  When ``None`` it reflects the host (``sys.platform``).
    """
    return (platform if platform is not None else sys.platform) == "win32"


def _purpose(spec: ToolSpec, platform: str | None) -> str:
    """``spec.purpose``, extended with Windows guidance only on Windows.

    The base purpose is unchanged on every platform; the extension is appended,
    never a replacement, so the contract's "name the binary *and* what it is for"
    is preserved and the Windows user additionally gets "… and here is where".
    """
    if is_windows(platform) and spec.windows_note:
        return f"{spec.purpose}. On Windows: {spec.windows_note}"
    return spec.purpose


def _first_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _probe_version(resolution: ToolResolution, version_args: tuple[str, ...]) -> str | None:
    """Run the resolved binary with ``version_args``; return its first line, or
    ``None``.  Runs under the tool's environment so a bundled binary's shared
    libraries resolve."""
    if not version_args:
        return None
    try:
        proc = subprocess.run(
            [resolution.path, *version_args],
            env=build_run_env(resolution),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return _first_line(proc.stdout) or _first_line(proc.stderr) or None


def _probe_tool(spec: ToolSpec, platform: str | None = None) -> dict:
    resolution = resolve_tool(spec.name)
    found = resolution is not None
    if not found:
        return {
            "name": spec.name,
            "found": False,
            "purpose": _purpose(spec, platform),
            "direct": spec.direct,
            "path": None,
            "version": None,
            "source": None,
        }
    version = _probe_version(resolution, spec.version_args)
    if version is None and resolution.source in ("bundled", "env"):
        version = bundled_tool_versions().get(spec.name) or None
    return {
        "name": spec.name,
        "found": True,
        "purpose": _purpose(spec, platform),
        "direct": spec.direct,
        "path": resolution.path,
        "version": version,
        # "env" is the explicit-override copy; it is not a host `PATH` copy, so
        # for the purpose of "which yosys ran" it is reported as distinct from
        # "system" and as close to "bundled" as matters to the reader.
        "source": resolution.source,
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


def run_doctor(platform: str | None = None) -> dict:
    """Return the ``data`` payload for ``gatepack doctor --json``.

    ``platform`` selects whose guidance the report carries (``"win32"`` for the
    Windows wording); ``None`` means the host platform.  The envelope shape is
    identical either way — only the ``purpose`` text differs, so the JSON
    contract is stable and the human reading it gets the right "where to get
    this" for their OS.
    """
    tools = [_probe_tool(spec, platform) for spec in TOOLS]
    direct = [t for t in tools if t["direct"]]
    return {
        "version": __version__,
        "tools": tools,
        "resources": _probe_resources(),
        # "all tools present" means the ones gatepack invokes directly; the
        # indirect entries (z3, espresso) are reported but never gate this flag.
        "allToolsPresent": all(t["found"] for t in direct),
    }


__all__ = ["TOOLS", "ToolSpec", "is_windows", "run_doctor"]
