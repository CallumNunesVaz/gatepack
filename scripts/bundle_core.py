#!/usr/bin/env python3
"""Build the self-contained gatepack core into ``app/resources/bin/gatepack``.

The packaged app locates its core at ``app/resources/bin/gatepack`` (see
``app/main/core.cts`` and §17 of the design).  This script produces that binary
with PyInstaller so the result runs with **no host Python, no venv and no
gatepack on the machine** — the whole stdlib, ``gatepack`` and ``pydantic`` are
frozen into a single executable.

PyInstaller is a build-only dependency: it is deliberately absent from
``pyproject.toml``'s runtime ``dependencies``.  If it is not importable here,
the build fails loudly rather than emitting a stub.

The trap this script exists to catch: ``pyproject.toml`` declares package data
(``gatepack/yosys/*.ys`` and ``gatepack/macros/models/*.v``) that is loaded at
runtime via ``importlib.resources``.  ``--collect-all gatepack`` folds those
files into the bundle, and the post-build smoke test re-loads them under a
scrubbed environment — if either resource went missing, the smoke test fails and
this script exits non-zero instead of leaving a broken binary in place.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def host_platform() -> str:
    """The platform this interpreter is running on (``"win32"`` vs ``sys.platform``).

    PyInstaller builds *only* for the platform it runs on; it does not
    cross-compile.  So the only way to produce ``gatepack.exe`` is to run this
    script on Windows (or a ``windows-latest`` CI runner — see
    ``.github/workflows/release.yml``, which already does).  A request for a
    foreign platform is refused by :func:`build_core`, never silently built for
    the host with a misleading name.
    """
    return "win32" if os.name == "nt" else sys.platform


def binary_name(platform: str | None = None) -> str:
    """The frozen binary's file name on ``platform`` (default: this host).

    PyInstaller appends ``.exe`` on Windows.  The packaged app's core locator
    (``app/main/core.cts``) and the release workflow must resolve the *same*
    name, or a Windows bundle is produced but never found.  ``platform`` is
    injectable so a test can pin the Windows name without a Windows host.
    """
    return "gatepack.exe" if (platform or host_platform()) == "win32" else "gatepack"


OUTPUT = REPO / "app" / "resources" / "bin" / binary_name()

_ENTRY_SOURCE = (
    "import sys\n"
    "from gatepack.cli import main\n"
    "if __name__ == '__main__':\n"
    "    sys.exit(main())\n"
)


def _has_executable(directory: Path, name: str) -> bool:
    """True when ``directory`` contains an executable named ``name``.

    Checks the bare name *and* its ``.exe`` variant: a Windows host has
    ``python.exe``/``gatepack.exe``, not ``python3``/``gatepack``, and a scrub
    that only checks the bare name would leak a host interpreter through.
    """
    for candidate in (name, name + ".exe"):
        if (directory / candidate).exists():
            return True
    return False


def pyinstaller_available() -> bool:
    """True when this interpreter can import PyInstaller (build-only dep)."""
    try:
        import PyInstaller  # noqa: F401

        return True
    except ImportError:
        return False


def _scrubbed_env() -> dict[str, str]:
    """An environment with no gatepack/python escape hatches.

    Used for the post-build smoke test: the frozen binary must work when there
    is no ``PYTHONPATH``/``PYTHONHOME``, no ``GATEPACK_CORE`` override, and no
    host ``python3``/``gatepack`` on ``PATH``.  ``TMPDIR``/``HOME`` are left
    alone — a PyInstaller onefile binary needs a writable temp dir, and that is
    not a gatepack dependency.
    """
    env = dict(os.environ)
    env.pop("GATEPACK_CORE", None)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    kept: list[str] = []
    for directory in env.get("PATH", "").split(os.pathsep):
        if not directory:
            continue
        d = Path(directory)
        if not d.is_dir():
            kept.append(directory)
            continue
        has_gatepack_or_python = any(
            _has_executable(d, name) for name in ("gatepack", "python3", "python")
        )
        if not has_gatepack_or_python:
            kept.append(directory)
    env["PATH"] = os.pathsep.join(kept)
    return env


def build_core(
    output: Path | None = None,
    workdir: Path | None = None,
    platform: str | None = None,
) -> Path:
    """Run PyInstaller and install the frozen binary at ``output``.

    ``platform`` defaults to the host; any *other* value is refused up front
    because PyInstaller does not cross-compile (a Windows binary must be built
    on Windows — ``.github/workflows/release.yml`` runs this script on
    ``windows-latest`` for exactly that reason).  The refusal is a clear error,
    never a host binary silently named ``gatepack.exe``.

    Raises :class:`RuntimeError` on any failure (PyInstaller missing, build
    failed, or the smoke test refused the result).  Never returns a stub.
    """
    platform = host_platform() if platform is None else platform
    if platform != host_platform():
        raise RuntimeError(
            f"PyInstaller does not cross-compile: this host is "
            f"{host_platform()!r}, but a {platform!r} binary was requested. "
            f"Build the {platform} core on a {platform} machine instead — "
            f".github/workflows/release.yml already runs scripts/bundle_core.py "
            f"on windows-latest/macos-13/macos-14 so each platform's core is "
            f"built natively."
        )

    if not pyinstaller_available():
        raise RuntimeError(
            "PyInstaller is not importable from this interpreter "
            f"({sys.executable}). Install it (a build-only dependency, not in "
            "pyproject.toml) with: pip install pyinstaller"
        )

    output = Path(output) if output is not None else OUTPUT
    workdir = Path(workdir) if workdir is not None else REPO / ".gpout" / "core-bundle"

    workdir.mkdir(parents=True, exist_ok=True)
    entry = workdir / "_gatepack_entry.py"
    entry.write_text(_ENTRY_SOURCE)

    dist = workdir / "dist"
    build = workdir / "build"
    if dist.exists():
        shutil.rmtree(dist)
    if build.exists():
        shutil.rmtree(build)

    argv = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--name",
        "gatepack",
        "--paths",
        str(REPO),
        "--collect-all",
        "gatepack",
        "--collect-all",
        "pydantic",
        # `examples/` is NOT package data — it sits beside the `gatepack`
        # package — so `--collect-all gatepack` does not see it.  `--add-data`
        # places it under the extraction root where `gatepack/examples.py`
        # resolves it via `sys._MEIPASS` when frozen.  `libraries/74aup.csv` is
        # deliberately NOT bundled: the CLI takes it as an explicit
        # `--library` path argument and the packaged app opens projects that
        # carry their own `parts.csv`; it is repo fixture data, not runtime data.
        "--add-data",
        f"{REPO / 'examples'}{os.pathsep}examples",
        "--distpath",
        str(dist),
        "--workpath",
        str(build),
        "--specpath",
        str(workdir),
        "--clean",
        "--noconfirm",
        str(entry),
    ]
    proc = subprocess.run(argv, cwd=str(REPO), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            "PyInstaller failed "
            f"({proc.returncode}):\n{proc.stdout}\n{proc.stderr}"
        )

    built = dist / binary_name(platform)
    if not built.exists():
        raise RuntimeError(
            f"PyInstaller reported success but no binary exists at {built}"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(built, output)
    if os.name != "nt":
        output.chmod(0o755)
    _smoke_test(output, workdir)
    return output


def _smoke_test(binary: Path, workdir: Path) -> None:
    """Refuse the binary if it cannot answer on a clean host.

    Three checks, each under a scrubbed environment (no ``GATEPACK_CORE``, no
    ``PYTHONPATH``/``PYTHONHOME``, no host ``python3``/``gatepack`` on ``PATH``):

    1. ``doctor --json`` — proves the ``.ys``/``.v`` package data survived;
    2. ``examples list`` — must name *every* example the source tree has
       (``examples list`` exits 0 even when it finds nothing, so exit 0 alone
       proves nothing, and naming the showcase alone would pass a bundle that
       had lost every other example);
    3. ``examples extract pelican`` — must materialise a ``design.yaml``.
    """
    env = _scrubbed_env()
    cwd = str(workdir)

    proc = subprocess.run(
        [str(binary), "doctor", "--json"],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"bundled core exited {proc.returncode} under a scrubbed "
            f"environment; refusing to install it.\nstdout={proc.stdout}\n"
            f"stderr={proc.stderr}"
        )
    import json

    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"bundled core emitted non-JSON stdout ({exc}): {proc.stdout!r}"
        ) from exc
    if not envelope.get("ok") or envelope.get("command") != "doctor":
        raise RuntimeError(
            f"bundled core emitted an unexpected envelope: {proc.stdout!r}"
        )
    resources = envelope.get("data", {}).get("resources", {})
    if not resources.get("commonFrontendYs") or not resources.get("mcellModels"):
        raise RuntimeError(
            "bundled core lost its package data (common_frontend.ys / M-cell "
            f"models not loadable): {resources!r}"
        )

    # `examples/` is not package data; a bundle that lost it reports "none" on
    # `examples list` with exit 0 — so assert the *names*, not just the exit
    # code. Checking for the showcase alone is not enough: `--add-data` copies
    # the tree wholesale, so the way this fails is *every* example going
    # missing, and one hardcoded name would have reported that as fine. Compare
    # against what the source tree actually holds, so an example added tomorrow
    # is covered without anyone remembering to add it here.
    expected = {
        entry.name
        for entry in (REPO / "examples").iterdir()
        if entry.is_dir() and (entry / "design.yaml").is_file()
    }
    proc = subprocess.run(
        [str(binary), "examples", "list", "--json"],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"bundled core could not list its examples (exit {proc.returncode}): "
            f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
        )
    try:
        listed = {
            e["name"]
            for e in json.loads(proc.stdout).get("data", {}).get("examples", [])
        }
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError(
            f"bundled core's `examples list --json` was unreadable: {exc}; "
            f"stdout={proc.stdout!r}"
        ) from exc
    if listed != expected:
        raise RuntimeError(
            "bundled core does not ship the examples the source tree has: "
            f"missing={sorted(expected - listed)} unexpected={sorted(listed - expected)}"
        )

    target = workdir / "smoke-extract"
    if target.exists():
        shutil.rmtree(target)
    proc = subprocess.run(
        [str(binary), "examples", "extract", "pelican", "-o", str(target)],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0 or not (target / "design.yaml").is_file():
        raise RuntimeError(
            "bundled core could not extract the showcase "
            f"'pelican': stdout={proc.stdout!r} stderr={proc.stderr!r}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the self-contained gatepack core (PyInstaller)."
    )
    parser.add_argument(
        "-o",
        "--output",
        default=str(OUTPUT),
        help=f"output path (default: {OUTPUT})",
    )
    parser.add_argument(
        "--workdir",
        default=None,
        help="scratch dir for PyInstaller (default: .gpout/core-bundle)",
    )
    parser.add_argument(
        "--platform",
        default=None,
        help="target platform (default: this host). PyInstaller cannot "
        "cross-compile, so any non-host value is refused with a clear error.",
    )
    args = parser.parse_args(argv)
    try:
        path = build_core(
            output=Path(args.output),
            workdir=Path(args.workdir) if args.workdir else None,
            platform=args.platform,
        )
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
