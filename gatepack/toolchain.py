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

Tool resolution (§17, and the packaged-app requirement of §17.1): a packaged
app ships the native toolchain beside its frozen core at
``app/resources/bin/``.  When a bundled copy exists it must be preferred over a
host ``PATH`` copy, and an explicit override must beat both — the same order
``app/main/core.cts`` already establishes for the core itself:

  1. ``GATEPACK_TOOLS`` — an explicit directory of bundled tools
     (integration/test override, works in both dev and packaged runs);
  2. the bundled directory (next to the frozen executable, only when running
     under PyInstaller — a dev checkout keeps using its system tools);
  3. ``PATH``.

A bundled binary is not run bare: its non-glibc shared libraries are shipped in
``<dir>/lib`` and surfaced through ``LD_LIBRARY_PATH``, and ``<dir>`` is
prepended to ``PATH`` so tools that reach each other (sby -> yosys-smtbmc ->
yosys) resolve their siblings rather than a host copy.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

#: The environment variable naming an explicit directory of bundled tools.  Its
#: presence beats both the bundled location and ``PATH`` (the core's analogue is
#: ``GATEPACK_CORE``).
GATEPACK_TOOLS_ENV = "GATEPACK_TOOLS"

#: Directories always appended to ``PATH`` when a bundled tool runs.  The
#: bundled tools legitimately need the base system — a POSIX shell and
#: ``/usr/bin/env`` — which sby reaches through ``/usr/bin/env bash``.  A
#: packaged app inherits a normal ``PATH``, but a scrubbed environment does not;
#: making these explicit (rather than relying on inheritance) is what lets a
#: bundled sby find ``bash`` even when the parent ``PATH`` is empty.  The
#: bundled directory is always placed *first*, so a bundled tool wins over any
#: system copy.
SYSTEM_PATH_DIRS: tuple[str, ...] = ("/bin", "/usr/bin", "/usr/local/bin")

#: Tools that are a *host requirement* rather than a bundled binary.  Their
#: presence is checked by absolute path (they are never bundled, and the base
#: system dirs are what ``build_run_env`` adds), so ``gatepack doctor`` reports
#: them accurately even under a scrubbed ``PATH``.
HOST_REQUIREMENT_PATHS: dict[str, tuple[str, ...]] = {
    "bash": ("/bin/bash", "/usr/bin/bash"),
}

#: glibc-provided shared objects that must *not* be bundled: they are the
#: interface to the running kernel/libc and cannot be shipped portably (the host
#: loader resolves them at process start).  Everything else a binary links
#: against — libstdc++, libgcc_s, libreadline, libtcl, libffi, libz, libtinfo —
#: is bundled alongside the binary by ``scripts/bundle_toolchain.py``.
GCLIBC_CORE_LIBS = frozenset(
    {
        "ld-linux",
        "libc.so",
        "libm.so",
        "libpthread.so",
        "libdl.so",
        "libresolv.so",
        "librt.so",
        "libnsl.so",
        "libutil.so",
        "libmvec.so",
        "linux-vdso",
    }
)


@dataclass(frozen=True)
class ToolResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class ToolResolution:
    """Where a tool was found and how to run it.

    ``path`` is the executable to spawn (absolute for a bundled/env copy, a bare
    ``PATH`` name for a system copy).  ``source`` is one of ``"env"``,
    ``"bundled"`` or ``"system"`` — the provenance :mod:`gatepack.doctor`
    reports so a user debugging a wrong result can tell *which* binary ran.
    ``libdir``/``tooldir`` are only set for a bundled/env copy and drive the
    ``LD_LIBRARY_PATH``/``PATH`` prefixes in :func:`build_run_env`.
    """

    name: str
    path: str
    source: str
    libdir: str | None = None
    tooldir: str | None = None


def yosys_command(script: str) -> list[str]:
    """The exact Yosys command line for a script (assertable without the binary)."""
    return ["yosys", "-p", script]


def iverilog_command(output: str, sources: Sequence[str]) -> list[str]:
    """The exact Icarus compile command line for a set of sources."""
    return ["iverilog", "-o", output, *list(sources)]


def vvp_command(vvp_path: str) -> list[str]:
    """The exact vvp (Icarus runtime) command line."""
    return ["vvp", vvp_path]


def sby_command(sby_file: str) -> list[str]:
    """The exact SymbiYosys command line for a ``.sby`` file (M6, §11)."""
    return ["sby", "-f", sby_file]


def _is_executable(path: Path) -> bool:
    try:
        return path.is_file() and os.access(path, os.X_OK)
    except OSError:
        return False


def bundled_toolchain_dir() -> Path | None:
    """The directory holding bundled tools, when running inside the packaged app.

    Only the packaged (frozen) core bundles the toolchain beside itself, so this
    returns ``sys.executable``'s directory when frozen and ``None`` otherwise.  A
    development checkout runs the CLI from source and uses its **system** tools
    (§17: the bundled tools exist only in the packaged ``app/resources/bin/``,
    which a source checkout does not see) — ``GATEPACK_TOOLS`` remains the
    explicit override for both cases.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return None


def _search_dir_from_env(environ: Mapping[str, str]) -> tuple[Path, str] | None:
    override = environ.get(GATEPACK_TOOLS_ENV)
    if not override:
        return None
    d = Path(override)
    if not d.is_dir():
        return None
    return d, "env"


def _in_dir(directory: Path, name: str, platform: str) -> Path | None:
    """``name`` inside ``directory``, honouring the platform's executable suffix.

    On Windows a bundled tool is ``yosys.exe``, not ``yosys``.  ``shutil.which``
    applies ``PATHEXT`` for us on the ``PATH`` branch below, but the bundled and
    ``GATEPACK_TOOLS`` branches look a file up directly, so without this they
    find nothing on Windows — which is precisely the self-contained case a
    Windows installer exists to serve.  ``app/main/core.cts::binaryName`` has
    always done this for the core; the toolchain did not.
    """
    for suffix in ("", ".exe") if platform == "win32" else ("",):
        candidate = directory / f"{name}{suffix}"
        if _is_executable(candidate):
            return candidate
    return None


def resolve_tool(
    name: str,
    environ: Mapping[str, str] | None = None,
    platform: str | None = None,
) -> ToolResolution | None:
    """Resolve ``name`` to a :class:`ToolResolution`, or ``None`` when absent.

    Precedence (matches ``app/main/core.cts`` for the core): explicit
    ``GATEPACK_TOOLS`` directory, the bundled directory, then ``PATH``.  A
    bundled/env copy advertises its ``lib`` subdirectory (shared libraries) and
    its own directory (sibling tools) so the runner can construct the right
    environment; a system copy does not.

    ``platform`` defaults to ``sys.platform``; a test passes ``"win32"`` to
    exercise the Windows suffix rule on a POSIX host.
    """
    environ = dict(environ) if environ is not None else os.environ
    platform = platform if platform is not None else sys.platform

    env_dir = _search_dir_from_env(environ)
    if env_dir is not None:
        d, source = env_dir
        candidate = _in_dir(d, name, platform)
        if candidate is not None:
            return ToolResolution(
                name=name,
                path=str(candidate),
                source=source,
                libdir=_libdir(d),
                tooldir=str(d),
            )

    bundled = bundled_toolchain_dir()
    if bundled is not None:
        candidate = _in_dir(bundled, name, platform)
        if candidate is not None:
            return ToolResolution(
                name=name,
                path=str(candidate),
                source="bundled",
                libdir=_libdir(bundled),
                tooldir=str(bundled),
            )

    for host_path in HOST_REQUIREMENT_PATHS.get(name, ()):
        if _is_executable(Path(host_path)):
            return ToolResolution(name=name, path=host_path, source="system")

    found = shutil.which(name)
    if found is not None:
        return ToolResolution(name=name, path=found, source="system")
    return None


def _libdir(tool_dir: Path) -> str:
    """The bundled shared-library directory (``<dir>/lib``), even if not yet
    present — the dynamic loader silently ignores a missing ``LD_LIBRARY_PATH``
    entry, so advertising it unconditionally keeps the code simple and the
    bundled tools still fall back to the host when no libraries were shipped."""
    return str(tool_dir / "lib")


def bundled_tool_versions() -> dict[str, str]:
    """``{name: version}`` recorded in the bundled toolchain manifest, or ``{}``.

    Some tools (sby) have no ``--version`` flag, so their version is the pinned
    source it was built from, recorded by ``scripts/bundle_toolchain.py`` in
    ``toolchain-manifest.json``.  :mod:`gatepack.doctor` falls back to this when
    a bundled tool's ``--version`` probe is empty.
    """
    d = bundled_toolchain_dir()
    if d is None:
        return {}
    try:
        data = json.loads((d / "toolchain-manifest.json").read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        tool["name"]: tool.get("version", "")
        for tool in data.get("tools", [])
        if isinstance(tool, dict)
    }


def build_run_env(
    resolution: ToolResolution, base_env: Mapping[str, str] | None = None
) -> dict[str, str] | None:
    """Return the environment a resolved tool must run under, or ``None``.

    ``None`` means "inherit the parent environment unchanged" — the case for a
    system copy and for a custom/injected runner.  A bundled/env copy prepends
    its library directory to ``LD_LIBRARY_PATH`` and sets ``PATH`` to its own
    directory followed by the inherited ``PATH`` and the base system dirs (so
    sby finds the bundled yosys-smtbmc/yosys/z3 *and* a POSIX shell/``env`` even
    when the parent ``PATH`` is empty).
    """
    if not resolution.libdir and not resolution.tooldir:
        return None
    env = dict(base_env) if base_env is not None else os.environ.copy()
    if resolution.libdir:
        existing = env.get("LD_LIBRARY_PATH")
        env["LD_LIBRARY_PATH"] = (
            resolution.libdir if not existing else resolution.libdir + os.pathsep + existing
        )
    if resolution.tooldir:
        env["PATH"] = _tool_path(resolution.tooldir, env.get("PATH"))
    return env


def _tool_path(tooldir: str, inherited: str | None) -> str:
    """``tooldir`` + inherited ``PATH`` + the base system dirs, deduplicated.

    The bundled directory is first (a bundled tool must win over a host copy),
    then whatever the parent supplied, then the base system dirs that are always
    appended rather than relied upon (see :data:`SYSTEM_PATH_DIRS`).
    """
    parts = [tooldir]
    if inherited:
        parts.extend(inherited.split(os.pathsep))
    parts.extend(SYSTEM_PATH_DIRS)
    seen: set[str] = set()
    ordered: list[str] = []
    for part in parts:
        if part and part not in seen:
            seen.add(part)
            ordered.append(part)
    return os.pathsep.join(ordered)


class ToolchainRunner:
    """Subprocess-backed runner; inject a fake in tests to avoid the binary.

    ``which`` is retained for the historical injection point (tests pass a fake
    ``which`` to assert a missing binary is reported, never faked).  When
    ``which`` is ``None`` the runner resolves tools through
    :func:`resolve_tool`, so a packaged core prefers its bundled tools and a dev
    checkout keeps using its system tools.
    """

    def __init__(self, which=None) -> None:
        self._which = which

    def _resolve(self, name: str) -> ToolResolution | None:
        if self._which is not None:
            path = self._which(name)
            if path is None:
                return None
            return ToolResolution(name=name, path=path, source="custom")
        return resolve_tool(name)

    def available(self, name: str) -> bool:
        return self._resolve(name) is not None

    def run(self, argv: Sequence[str], cwd: str, timeout: int = 600) -> ToolResult:
        if not argv:
            return ToolResult(returncode=-1, stdout="", stderr="empty command")
        resolution = self._resolve(argv[0])
        if resolution is None:
            return ToolResult(
                returncode=-1, stdout="", stderr=f"{argv[0]}: tool not found"
            )
        cmd = [resolution.path, *argv[1:]]
        env = build_run_env(resolution)
        try:
            proc = subprocess.run(
                cmd,
                cwd=cwd,
                env=env,
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
    "GATEPACK_TOOLS_ENV",
    "HOST_REQUIREMENT_PATHS",
    "SYSTEM_PATH_DIRS",
    "ToolResolution",
    "ToolResult",
    "ToolchainRunner",
    "build_run_env",
    "bundled_toolchain_dir",
    "bundled_tool_versions",
    "iverilog_command",
    "resolve_tool",
    "sby_command",
    "vvp_command",
    "yosys_command",
]
