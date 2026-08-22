#!/usr/bin/env python3
"""Bundle the native EDA toolchain into ``app/resources/bin/``.

The packaged app already ships a self-contained Python core
(``scripts/bundle_core.py``), but the core shells out to **yosys, sby, iverilog,
vvp and z3**, and none of them ship — on a machine without them ``gatepack
doctor`` reports "missing" and ``gatepack build`` refuses.  This script closes
that gap: it copies the pinned toolchain and everything it dynamically links
against into ``app/resources/bin/`` (already ``asarUnpack``ed and gitignored;
``app/electron-builder.yml`` carries the ``extraResources`` entry).

Provenance, verification and dynamic linking are recorded per binary in
``app/resources/bin/toolchain-manifest.json`` — where the build came from, how
it is verified (checksum + version), and what it links against (the ``ldd``
output).  A binary that only works because of a host library is *not* bundled
bare: its non-glibc shared libraries are copied into ``app/resources/bin/lib``
and surfaced at run time through ``LD_LIBRARY_PATH`` (see
``gatepack/toolchain.py``).

Two kinds of tool, two strategies:

* **ELF binaries** (yosys, iverilog, vvp, z3) are copied verbatim, then their
  ``ldd`` closure is walked and every library outside the glibc core set is
  copied alongside.
* **Python drivers** (sby, yosys-smtbmc, yosys-witness) are Python scripts that
  need a Python runtime the packaged app does not have.  They are frozen with
  PyInstaller (the same technique as the core) so each becomes a self-contained
  executable; sby still shells out to ``yosys``/``yosys-smtbmc``/``z3`` by bare
  name, which the runtime environment (``PATH`` prepended with this directory)
  resolves to the bundled siblings.

The toolchain comes from the pinned measurement image ``gatepack-toolchain:m6``
(``Dockerfile.probe``: Debian bookworm, Yosys 0.23 from the archive, sby pinned
to commit ``beb8b3c6e38ee716cd9771eb906c37684e83eab4``).  Every measured finding
in ``docs/M0-FINDINGS.md`` and ``docs/M6-FINDINGS.md`` was taken against that
image, so bundling *this* toolchain is what keeps the packaged app's results
consistent with those findings.

espresso is **not** bundled here, on purpose: the probe image does not build it
(Dockerfile builds it from ``chipsalliance/espresso@0288253c…`` but that image
has never been built end-to-end — see ``Dockerfile``), and it is only used by
the not-yet-shipped async backend.  See ``docs/BUILD-NOTES-toolchain.md``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUTPUT = REPO / "app" / "resources" / "bin"
LIB_DIR = OUTPUT / "lib"
MANIFEST_PATH = OUTPUT / "toolchain-manifest.json"
SCRATCH = REPO / ".gpout" / "toolchain-bundle"

# The image every M0/M6 measurement was taken in (Dockerfile.probe).
IMAGE = "gatepack-toolchain:m6"

# sby is pinned by bare commit, not tag (M6-FINDINGS §5 / Dockerfile.probe).
SBY_COMMIT = "beb8b3c6e38ee716cd9771eb906c37684e83eab4"

# glibc-provided shared objects that must NOT be bundled (the host loader
# resolves them at process start; they are the interface to the running libc).
# Everything else a binary links against is copied into ``lib/``.
GCLIBC_CORE = frozenset(
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


def host_is_linux() -> bool:
    """True when this script is running on Linux.

    This script bundles **Linux x86-64 ELF** binaries (yosys, iverilog, vvp,
    z3, berkeley-abc) extracted from the Linux ``gatepack-toolchain:m6`` image,
    plus their non-glibc shared libraries.  None of that is runnable on Windows:
    a Windows app must instead use OSS CAD Suite or WSL2, which ``gatepack
    doctor`` describes.  The bundle is refused on a non-Linux host so nobody
    ships inert ELF binaries in a Windows installer.
    """
    return sys.platform.startswith("linux")


@dataclass(frozen=True)
class ElfTool:
    name: str
    container_path: str
    licence: str
    component: str
    source: str
    version_args: tuple[str, ...]


@dataclass(frozen=True)
class PythonTool:
    name: str
    container_path: str
    module_dirs: tuple[str, ...]
    licence: str
    component: str
    source: str
    version: str


ELF_TOOLS: tuple[ElfTool, ...] = (
    ElfTool(
        "yosys",
        "/usr/bin/yosys",
        "ISC",
        "Yosys",
        "Debian bookworm archive (Yosys 0.23), via gatepack-toolchain:m6",
        ("--version",),
    ),
    ElfTool(
        "iverilog",
        "/usr/bin/iverilog",
        "GPL-2.0-or-later",
        "Icarus Verilog",
        "Debian bookworm archive (Icarus Verilog 11.0), via gatepack-toolchain:m6",
        ("-V",),
    ),
    ElfTool(
        "vvp",
        "/usr/bin/vvp",
        "GPL-2.0-or-later",
        "Icarus Verilog",
        "Debian bookworm archive (Icarus Verilog 11.0), via gatepack-toolchain:m6",
        ("-V",),
    ),
    ElfTool(
        "z3",
        "/usr/bin/z3",
        "MIT",
        "Z3",
        "Debian bookworm archive (z3 4.8.12), via gatepack-toolchain:m6",
        ("--version",),
    ),
    ElfTool(
        "berkeley-abc",
        "/usr/bin/berkeley-abc",
        "BSD-style",
        "ABC (Berkeley-abc)",
        "Debian bookworm archive (berkeley-abc), via gatepack-toolchain:m6; "
        "invoked indirectly by yosys's abc pass (not a direct gatepack tool)",
        (),
    ),
)

PYTHON_TOOLS: tuple[PythonTool, ...] = (
    PythonTool(
        "sby",
        "/usr/local/bin/sby",
        ("/usr/local/share/yosys/python3",),
        "ISC",
        "SymbiYosys (sby)",
        f"git clone YosysHQ/sby + checkout {SBY_COMMIT} + make install",
        f"git {SBY_COMMIT}",
    ),
    PythonTool(
        "yosys-smtbmc",
        "/usr/bin/yosys-smtbmc",
        ("/usr/share/yosys",),
        "ISC",
        "Yosys (yosys-smtbmc)",
        "Debian bookworm yosys package (ships yosys-smtbmc)",
        "Yosys 0.23 (git sha1 7ce5011c24b)",
    ),
    PythonTool(
        "yosys-witness",
        "/usr/bin/yosys-witness",
        ("/usr/share/yosys",),
        "ISC",
        "Yosys (yosys-witness)",
        "Debian bookworm yosys package (ships yosys-witness)",
        "Yosys 0.23 (git sha1 7ce5011c24b)",
    ),
)

# sby depends on click, which is not in the host venv; it is extracted from the
# container's site-packages and made importable during the freeze.
CLICK_DIR = "/usr/lib/python3/dist-packages/click"

# Yosys cannot run without its ``share`` directory (techlibs, simcells.v,
# smtio.py, ...).  It locates it relative to its own executable
# (``<bin>/../share/yosys``), so the whole tree must ship beside the binary.
YOSYS_SHARE = "/usr/share/yosys"

# Icarus Verilog's driver shells out to ``ivlpp`` and ``ivl`` (plus the ``.tgt``
# and ``.vpi`` support files), which it locates at ``<bin>/../x86_64-linux-gnu/ivl``
# relative to the iverilog/vvp executables.  The whole tree ships beside them.
IVERILOG_IVL = "/usr/lib/x86_64-linux-gnu/ivl"

# Data directories shipped beside the binaries, each with a single uniform
# licence.  ``rel`` is the path relative to ``app/resources/``; ``src`` is the
# container path; ``dst`` is where it lands in the tree.
DATA_DIRS: tuple[dict, ...] = (
    {
        "rel": "share/yosys",
        "src": YOSYS_SHARE,
        "dst": REPO / "app" / "resources" / "share",
        "licence": "ISC",
        "component": "Yosys",
        "source": "Debian bookworm archive (Yosys 0.23 share/ data)",
    },
    {
        "rel": "x86_64-linux-gnu/ivl",
        "src": IVERILOG_IVL,
        "dst": REPO / "app" / "resources" / "x86_64-linux-gnu",
        "licence": "GPL-2.0-or-later",
        "component": "Icarus Verilog",
        "source": "Debian bookworm archive (Icarus Verilog 11.0 support files)",
    },
)


# ---------------------------------------------------------------------------
# Docker plumbing
# ---------------------------------------------------------------------------


def docker_available() -> bool:
    return shutil.which("docker") is not None


def image_available(image: str = IMAGE) -> bool:
    if not docker_available():
        return False
    return (
        subprocess.run(
            ["docker", "image", "inspect", image], capture_output=True, text=True
        ).returncode
        == 0
    )


def _run_in_image(image: str, script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "run", "--rm", image, "bash", "-c", script],
        capture_output=True,
        text=True,
    )


class _Container:
    """A created-but-not-started container, used for ``docker cp`` extraction."""

    def __init__(self, image: str) -> None:
        proc = subprocess.run(
            ["docker", "create", image], capture_output=True, text=True, check=True
        )
        self.id = proc.stdout.strip()

    def copy_out(self, src: str, dst_dir: Path) -> None:
        """Copy ``src`` (a file or directory) into ``dst_dir`` (a directory)."""
        dst_dir.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            ["docker", "cp", f"{self.id}:{src}", f"{dst_dir}/"],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"docker cp {src} failed: {proc.stderr}")

    def copy_out_as(self, src: str, dst_file: Path) -> None:
        """Copy ``src`` (a single file) to the exact ``dst_file`` path."""
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            ["docker", "cp", f"{self.id}:{src}", str(dst_file)],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"docker cp {src} failed: {proc.stderr}")

    def close(self) -> None:
        subprocess.run(["docker", "rm", self.id], capture_output=True, text=True)


def _resolve_paths(image: str, paths: list[str]) -> dict[str, str]:
    """Map each container path to its ``readlink -f``-resolved real path.

    Debian ships its shared libraries as symlinks (``libstdc++.so.6`` ->
    ``libstdc++.so.6.0.30``); ``docker cp`` copies the symlink, not its target,
    so the target must be resolved first and copied under the SONAME the binary
    links against.
    """
    if not paths:
        return {}
    script = "\n".join(f"readlink -f {shlex.quote(p)}" for p in paths)
    proc = _run_in_image(image, script)
    resolved = proc.stdout.splitlines()
    return dict(zip(paths, resolved))


# ---------------------------------------------------------------------------
# ldd parsing
# ---------------------------------------------------------------------------


def parse_ldd(output: str) -> list[tuple[str, str]]:
    """Parse ``ldd`` output into ``(soname, path)`` pairs.

    Handles both forms: ``soname => /path (addr)`` and a bare absolute path
    (the dynamic linker itself, e.g. ``/lib64/ld-linux-x86-64.so.2``).
    """
    pairs: list[tuple[str, str]] = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        if " => " in line:
            left, _, right = line.partition(" => ")
            soname = left.strip()
            path = right.split(" (")[0].strip()
            pairs.append((soname, path))
        elif line.startswith("/"):
            path = line.split(" (")[0].strip()
            pairs.append((Path(path).name, path))
    return pairs


def is_glibc_core(soname: str) -> bool:
    return any(soname.startswith(prefix) for prefix in GCLIBC_CORE)


def non_glibc_libs(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """The ``(soname, path)`` pairs that must be bundled (everything but glibc)."""
    return [(soname, path) for soname, path in pairs if not is_glibc_core(soname)]


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _manifest_entry(
    name: str, kind: str, component: str, licence: str, source: str, version: str
) -> dict:
    return {
        "name": name,
        "kind": kind,
        "component": component,
        "licence": licence,
        "source": source,
        "version": version,
    }


# ---------------------------------------------------------------------------
# ELF bundling
# ---------------------------------------------------------------------------


def _elf_ldd_in_container(image: str, path: str) -> str:
    proc = _run_in_image(image, f"ldd {path} 2>&1")
    return proc.stdout


def bundle_elf_tools(image: str, container: _Container, out: Path) -> list[dict]:
    """Copy each ELF binary and its non-glibc shared libraries into ``out``."""
    entries: list[dict] = []
    lib_seen: dict[str, str] = {}  # soname -> container path (dedupe across tools)

    for tool in ELF_TOOLS:
        ldd_out = _elf_ldd_in_container(image, tool.container_path)
        pairs = parse_ldd(ldd_out)
        libs = non_glibc_libs(pairs)

        version = _probe_version_in_container(image, tool.container_path, tool.version_args)

        # copy the binary
        container.copy_out(tool.container_path, out)
        (out / tool.name).chmod(0o755)

        for soname, path in libs:
            lib_seen.setdefault(soname, path)

        entries.append(
            {
                **_manifest_entry(
                    tool.name,
                    "elf",
                    tool.component,
                    tool.licence,
                    tool.source,
                    version or tool.name,
                ),
                "files": [tool.name],
                "ldd": [soname for soname, _ in libs],
                "sha256": sha256(out / tool.name),
            }
        )

    return entries, lib_seen


def _probe_version_in_container(
    image: str, path: str, version_args: tuple[str, ...]
) -> str | None:
    if not version_args:
        return None
    proc = _run_in_image(image, f"{path} {' '.join(version_args)} 2>&1")
    text = (proc.stdout or proc.stderr or "").strip()
    return text.splitlines()[0].strip() if text.splitlines() else None


# ---------------------------------------------------------------------------
# Python-driver freezing (PyInstaller)
# ---------------------------------------------------------------------------


def pyinstaller_available() -> bool:
    try:
        import PyInstaller  # noqa: F401

        return True
    except ImportError:
        return False


def _extract_python_sources(
    container: _Container, scratch: Path
) -> tuple[list[Path], list[Path]]:
    """Copy the Python drivers + their modules out of the container.

    Returns ``(module_dirs, click_dirs)`` — directories to add to PyInstaller's
    ``--paths``.
    """
    module_dirs: list[Path] = []
    for tool in PYTHON_TOOLS:
        container.copy_out(tool.container_path, scratch / "drivers")
        (scratch / "drivers" / tool.name).rename(scratch / "drivers" / f"{tool.name}.py")
        for d in tool.module_dirs:
            # flatten: copy every .py in the module dir into one shared dir
            proc = _run_in_image(IMAGE, f"find {d} -maxdepth 1 -name '*.py' -printf '%p\\n'")
            for src in proc.stdout.splitlines():
                src = src.strip()
                if not src:
                    continue
                container.copy_out(src, scratch / "python3")
    module_dirs.append(scratch / "python3")

    # click (the one non-stdlib dependency) comes from the container.
    container.copy_out(CLICK_DIR, scratch / "python3")
    click_dist = "/usr/lib/python3/dist-packages/click-8.1.3.dist-info"
    proc = _run_in_image(IMAGE, f"ls -d {click_dist} 2>/dev/null || true")
    if proc.stdout.strip():
        container.copy_out(click_dist, scratch / "python3")
    return module_dirs, module_dirs


def _freeze_driver(tool: PythonTool, driver: Path, module_dirs: list[Path], out: Path) -> None:
    paths = [str(d) for d in module_dirs]
    argv = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--name",
        tool.name,
        "--distpath",
        str(out / "dist"),
        "--workpath",
        str(out / "build"),
        "--specpath",
        str(out),
        "--clean",
        "--noconfirm",
        *[arg for d in paths for arg in ("--paths", d)],
        str(driver),
    ]
    proc = subprocess.run(argv, cwd=str(REPO), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"PyInstaller failed for {tool.name} ({proc.returncode}):\n"
            f"{proc.stdout}\n{proc.stderr}"
        )
    built = out / "dist" / tool.name
    if not built.exists():
        raise RuntimeError(f"PyInstaller reported success but no binary for {tool.name}")


def bundle_python_tools(
    container: _Container, scratch: Path, out: Path
) -> list[dict]:
    if not pyinstaller_available():
        raise RuntimeError(
            "PyInstaller is not importable from this interpreter; it is required "
            "to freeze the Python toolchain drivers (sby, yosys-smtbmc, "
            "yosys-witness). Install it (a build-only dependency) with "
            "pip install pyinstaller"
        )
    module_dirs, _ = _extract_python_sources(container, scratch)
    entries: list[dict] = []
    for tool in PYTHON_TOOLS:
        driver = scratch / "drivers" / f"{tool.name}.py"
        freeze_dir = scratch / f"freeze-{tool.name}"
        _freeze_driver(tool, driver, module_dirs, freeze_dir)
        src = freeze_dir / "dist" / tool.name
        shutil.copy2(src, out / tool.name)
        (out / tool.name).chmod(0o755)
        entries.append(
            {
                **_manifest_entry(
                    tool.name,
                    "python",
                    tool.component,
                    tool.licence,
                    tool.source,
                    tool.version,
                ),
                "files": [tool.name],
                "sha256": sha256(out / tool.name),
            }
        )
    return entries


# ---------------------------------------------------------------------------
# Manifest + shared-library copying
# ---------------------------------------------------------------------------


def _shared_lib_entry(soname: str, container_path: str) -> dict:
    licence, component = _lib_licence(soname)
    return {
        "file": f"lib/{soname}",
        "licence": licence,
        "component": component,
        "source": f"Debian bookworm archive ({Path(container_path).name})",
    }


def _lib_licence(soname: str) -> tuple[str, str]:
    if soname.startswith("libstdc++") or soname.startswith("libgcc_s"):
        return "GPL-3.0-or-later with GCC Runtime Library Exception", "GCC runtime"
    if soname.startswith("libreadline"):
        return "GPL-3.0-or-later", "GNU Readline"
    if soname.startswith("libtcl"):
        return "BSD-style", "Tcl (Tcl/Tk licence)"
    if soname.startswith("libffi"):
        return "MIT", "libffi"
    if soname.startswith("libz.") or soname == "libz.so.1":
        return "zlib", "zlib"
    if soname.startswith("libbz2"):
        return "bzip2", "bzip2"
    if soname.startswith("libtinfo") or soname.startswith("libncurses"):
        return "MIT", "ncurses (MIT/X11)"
    # A library the table does not name: refuse to guess. The audit treats a
    # missing licence the same way.
    return "UNRECOGNISED", soname


def write_manifest(
    out: Path,
    elf_entries: list[dict],
    python_entries: list[dict],
    lib_seen: dict[str, str],
    data_dirs: list[dict],
) -> Path:
    shared_libs = [
        _shared_lib_entry(soname, path) for soname, path in sorted(lib_seen.items())
    ]
    manifest = {
        "schema_version": 1,
        "comment": (
            "Bundled native toolchain produced by scripts/bundle_toolchain.py. "
            "Every file below is audited by scripts/licence_audit.py "
            "(--require-toolchain)."
        ),
        "image": IMAGE,
        "sby_commit": SBY_COMMIT,
        "tools": elf_entries + python_entries,
        "shared_libs": shared_libs,
        "data_dirs": data_dirs,
    }
    path = out / "toolchain-manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return path


def _prune_share(share_dir: Path) -> None:
    """Remove Python bytecode caches from the copied Yosys share tree."""
    for pycache in share_dir.rglob("__pycache__"):
        shutil.rmtree(pycache, ignore_errors=True)


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------


def _scrubbed_env(bin_dir: Path) -> dict[str, str]:
    """PATH with only the bundled directory; LD_LIBRARY_PATH with only its lib."""
    return {
        "PATH": str(bin_dir),
        "LD_LIBRARY_PATH": str(bin_dir / "lib"),
        # keep HOME/TMPDIR: the frozen drivers (sby) and onefile PyInstaller
        # bootstraps need a writable temp dir, which is not a gatepack dependency.
        "HOME": os.environ.get("HOME", ""),
        "TMPDIR": os.environ.get("TMPDIR", ""),
    }


def smoke_test(bin_dir: Path) -> None:
    """Refuse the bundle if any binary cannot run under a scrubbed environment."""
    env = _scrubbed_env(bin_dir)
    checks = [
        (bin_dir / "yosys", ["--version"]),
        (bin_dir / "iverilog", ["-V"]),
        (bin_dir / "vvp", ["-V"]),
        (bin_dir / "z3", ["--version"]),
        (bin_dir / "sby", ["--help"]),
        (bin_dir / "yosys-smtbmc", ["--help"]),
        (bin_dir / "yosys-witness", ["--help"]),
    ]
    for binary, args in checks:
        proc = subprocess.run(
            [str(binary), *args], env=env, capture_output=True, text=True, timeout=120
        )
        if proc.returncode != 0 and not (proc.stdout or proc.stderr):
            raise RuntimeError(
                f"bundled {binary.name} produced no output and exited "
                f"{proc.returncode} under a scrubbed environment"
            )


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def bundle(verbose: bool = False) -> Path:
    if not host_is_linux():
        raise RuntimeError(
            "bundle_toolchain.py bundles Linux x86-64 ELF binaries (yosys, "
            "iverilog, vvp, z3, berkeley-abc) from the Linux gatepack-toolchain:m6 "
            "image; it cannot run on a non-Linux host. On Windows, install OSS "
            "CAD Suite (YosysHQ/oss-cad-suite-build) or run gatepack under WSL2 "
            "instead — `gatepack doctor` reports a missing tool honestly and "
            "names where a Windows user gets each one. A Windows package ships "
            "no bundled toolchain."
        )
    if not image_available():
        raise RuntimeError(
            f"toolchain image {IMAGE} is not available; build it with "
            f"Dockerfile.probe (or provide a local toolchain with --tools-dir, "
            "not implemented here — the image is the pinned provenance)"
        )

    OUTPUT.mkdir(parents=True, exist_ok=True)
    LIB_DIR.mkdir(parents=True, exist_ok=True)
    if SCRATCH.exists():
        subprocess.run(
            ["docker", "run", "--rm", "-v", f"{SCRATCH}:/scratch", IMAGE, "rm", "-rf", "/scratch"],
            capture_output=True,
            text=True,
        )
        shutil.rmtree(SCRATCH, ignore_errors=True)
    SCRATCH.mkdir(parents=True, exist_ok=True)

    container = _Container(IMAGE)
    try:
        elf_entries, lib_seen = bundle_elf_tools(IMAGE, container, OUTPUT)
        resolved = _resolve_paths(IMAGE, list(lib_seen.values()))
        for soname, path in lib_seen.items():
            container.copy_out_as(resolved.get(path, path), LIB_DIR / soname)

        # Yosys's share/ and Icarus's ivl/ support trees.
        data_dirs: list[dict] = []
        for spec in DATA_DIRS:
            dst = spec["dst"]
            if dst.exists():
                subprocess.run(
                    ["docker", "run", "--rm", "-v", f"{dst}:/d", IMAGE, "rm", "-rf", "/d"],
                    capture_output=True, text=True,
                )
                shutil.rmtree(dst, ignore_errors=True)
            container.copy_out(spec["src"], dst)
            _prune_share(dst)
            data_dirs.append(
                {
                    "path": spec["rel"],
                    "licence": spec["licence"],
                    "component": spec["component"],
                    "source": spec["source"],
                }
            )

        python_entries = bundle_python_tools(container, SCRATCH, OUTPUT)
    finally:
        container.close()

    write_manifest(OUTPUT, elf_entries, python_entries, lib_seen, data_dirs)
    smoke_test(OUTPUT)
    if verbose:
        for e in elf_entries + python_entries:
            print(f"  {e['name']}: {e['licence']} ({e['component']})")
    return MANIFEST_PATH


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="bundle the native EDA toolchain into app/resources/bin/"
    )
    parser.add_argument(
        "--output", default=str(OUTPUT), help="output directory (default: %(default)s)"
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    try:
        manifest = bundle(verbose=args.verbose)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"wrote toolchain to {args.output} (manifest: {manifest})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
