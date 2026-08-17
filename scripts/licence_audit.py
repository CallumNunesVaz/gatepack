#!/usr/bin/env python3
"""Licence audit (§4): every dependency's licence must be GPL-3.0-compatible.

Three inputs, all audited against the same POLICY table:

1. ``scripts/dependencies.json`` — the declared-dependency manifest (the core
   toolchain binaries + the Python runtime dependency).  Every entry's licence
   is classified; weak-copyleft-at-file-scope licences (EPL-2.0, MPL-2.0, LGPL)
   are *conditionally* compatible: accepted only when the entry is declared
   ``"unmodified": true``, which is exactly the elkjs case §4 calls out.

2. The installed npm tree (``app/node_modules``) — the ~500 packages the desktop
   application actually bundles.  This is opt-in via ``--node-tree`` /
   ``--require-node-tree``, because the manifest-only invocation is what the
   ``test`` CI job (which has no node_modules) runs.  The manifest could not see
   this tree, so the audit previously let an incompatible or unrecognised
   licence ship invisibly.  Each installed ``package.json`` ``license`` field is
   read (never assumed from the package name) and classified.  The tree is split
   into:

   * **shipped** — the packages npm records as production in
     ``app/package-lock.json`` (an entry with no ``dev``/``devOptional`` flag).
     These end up inside the packaged app (the renderer bundle embeds them and
     electron-builder packs production ``node_modules``).  Any *incompatible* or
     *unrecognised* licence here is a hard failure.  The lock file is used
     because re-deriving the graph from ``dependencies`` alone silently drops
     *nested* production dependencies (a hoisted ``yargs@17`` hides
     ``netlistsvg``'s real ``yargs@6`` subtree); when no lock file is present a
     flat-tree fallback is used instead.
    * **not shipped** (devDependencies, build tooling, extraneous hoisted
      packages, and packages packed out by ``app/electron-builder.yml`` ``files``
      excludes) — these do not ship, so an *incompatible* licence is reported as
      a warning, not a failure (conflating the two drowns the signal in build
      tooling).  The ``files`` excludes are read from the same
      ``electron-builder.yml`` that electron-builder itself reads, so the audit's
      "shipped" set tracks the actual asar instead of drifting from it.  An
      *unrecognised* licence is still a hard failure everywhere: a licence the
      table cannot name is a hole in the audit, not a pass.

3. The bundled Python core (``app/resources/bin/gatepack``, a PyInstaller
   onefile produced by ``scripts/bundle_core.py``) — opt-in via ``--bundle`` /
   ``--require-bundle``, because the manifest-only invocation is what the
   ``test`` CI job runs.  The binary is opened and its actual contents are
   enumerated (the PYZ module list, the bootloader/loader/runtime-hooks, the
   CPython runtime, and every bundled shared library) — never the declared
   dependency list, which is how the npm tree drifted once before.  Each
   enumerated component is classified against the POLICY table; an
   *unrecognised* component is a hard failure.

SPDX ``OR`` / ``AND`` expressions are evaluated properly (an ``OR`` is
acceptable when any alternative is; an ``AND`` when every part is).  Licences
are added to POLICY only after being identified by name, never defaulted.

Exit code 0 = every shipped dependency compatible and every licence recognised;
1 = at least one shipped dependency is incompatible or unrecognised, or any
licence anywhere is unrecognised.
"""

from __future__ import annotations

import argparse
import json
import marshal
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = Path(__file__).resolve().parent / "dependencies.json"
DEFAULT_NODE_TREE = REPO / "app" / "node_modules"
DEFAULT_APP_MANIFEST = REPO / "app" / "package.json"
DEFAULT_BUNDLE = REPO / "app" / "resources" / "bin" / "gatepack"
DEFAULT_TOOLCHAIN = REPO / "app" / "resources"
TOOLCHAIN_MANIFEST = "toolchain-manifest.json"

# Normalised licence key -> (verdict, rationale).
# verdicts: "compatible", "conditional", "incompatible", "unrecognised"
# Entries added for the installed tree are named licences, each identified
# before being added (see docs/BUILD-NOTES-m18.md), never defaulted.
POLICY: dict[str, tuple[str, str]] = {
    "isc": ("compatible", "permissive; GPL-compatible"),
    "mit": ("compatible", "permissive; GPL-compatible"),
    "mit-0": ("compatible", "MIT No Attribution; permissive; GPL-compatible"),
    "apache-2.0": ("compatible", "permissive; GPL-3.0-compatible (Apache-2.0)"),
    "bsd-2-clause": ("compatible", "permissive; GPL-compatible"),
    "bsd-3-clause": ("compatible", "permissive; GPL-compatible"),
    "bsd-style": ("compatible", "permissive BSD-style; GPL-compatible"),
    "blueoak-1.0.0": ("compatible", "Blue Oak Model License 1.0.0; permissive, OSI-approved, GPL-3.0-compatible"),
    "python-2.0": ("compatible", "PSF licence; permissive BSD-style; GPL-compatible"),
    "cc0-1.0": ("compatible", "CC0-1.0 public-domain dedication; GPL-compatible"),
    "wtfpl": ("compatible", "permissive; GPL-compatible"),
    "gpl-2.0+": ("compatible", "'or later' clause permits GPL-3.0 combination"),
    "gpl-2.0-or-later": ("compatible", "'or later' clause permits GPL-3.0 combination"),
    "gpl-3.0": ("compatible", "same family as GPL-3.0-or-later"),
    "gpl-3.0+": ("compatible", "same family as GPL-3.0-or-later"),
    "gpl-3.0-or-later": ("compatible", "the project licence itself"),
    "epl-2.0": ("conditional", "weak copyleft at file scope; requires unmodified library use"),
    "epl-1.0": ("incompatible", "EPL-1.0 has no secondary-licence provision (unlike EPL-2.0) and is not GPL-compatible (FSF); §4's elkjs argument does not transfer"),
    "mpl-2.0": ("conditional", "weak copyleft at file scope; requires unmodified library use"),
    "lgpl-2.1": ("conditional", "weak copyleft; requires unmodified library use (dynamic or independent)"),
    "lgpl-2.1+": ("conditional", "weak copyleft; requires unmodified library use"),
    "lgpl-3.0": ("conditional", "weak copyleft; requires unmodified library use"),
    "lgpl-3.0+": ("conditional", "weak copyleft; requires unmodified library use"),
    "gpl-2.0": ("incompatible", "GPL-2.0-only is not compatible with GPL-3.0"),
    "gpl-2.0-only": ("incompatible", "GPL-2.0-only is not compatible with GPL-3.0"),
    "cc-by-3.0": ("incompatible", "CC-BY-3.0 is not GPL-compatible (FSF)"),
    "cc-by-4.0": ("incompatible", "CC-BY-4.0 is not GPL-compatible (FSF)"),
    "proprietary": ("incompatible", "proprietary licence is not distributable under GPL-3.0"),
    # The bundled-core audit (below) resolves these.  Each was identified by name
    # before being added — the bootloader exception and GCC runtime exception are
    # quoted verbatim in docs/BUILD-NOTES-m18-release.md; the rest were read from
    # the installed package metadata or the build host's distro copyright files.
    "psf-2.0": ("compatible", "Python Software Foundation License 2.0 (the CPython/typing_extensions licence); permissive BSD-style; GPL-compatible"),
    "gpl-2.0-or-later with bootloader-exception": ("compatible", "PyInstaller bootloader/loader licence: GPL-2.0-or-later with the bootloader exception — unlimited permission to embed the bootloader in a combined executable (GPL restrictions still cover modification and non-embedded distribution)"),
    "gpl-3.0-or-later with gcc-runtime-library-exception": ("compatible", "GCC runtime (libgcc_s): GPL-3.0-or-later with the GCC Runtime Library Exception, which permits linking the runtime into a combined work under other terms"),
    # The toolchain manifest records this licence with spaces (it is written by
    # a human and normalised by ``_normalise``); the hyphenated key above is the
    # form the bundled-core audit passes directly.  Both name the same licence.
    "gpl-3.0-or-later with gcc runtime library exception": ("compatible", "GCC runtime (libgcc_s/libstdc++): GPL-3.0-or-later with the GCC Runtime Library Exception, which permits linking the runtime into a combined work under other terms"),
    "zlib": ("compatible", "Zlib licence; permissive; GPL-compatible"),
    "bzip2": ("compatible", "bzip2 licence; permissive; GPL-compatible"),
    "0bsd": ("compatible", "Zero-Clause BSD / public domain (liblzma); GPL-compatible"),
}


def _normalise(licence: str) -> str:
    text = licence.strip().lower()
    if "(" in text:
        text = text[: text.index("(")].strip()
    return text


def _verdict_for_key(name: str, key: str, unmodified: bool, shown: str) -> tuple[str, str]:
    if key not in POLICY:
        return "unrecognised", f"licence {shown!r} has no policy entry; add one after review"
    verdict, rationale = POLICY[key]
    if verdict == "conditional" and not unmodified:
        return (
            "incompatible",
            f"{rationale}; but {name!r} is not declared 'unmodified', so the "
            f"condition is not met",
        )
    return verdict, rationale


def _classify(name: str, licence: str, unmodified: bool) -> tuple[str, str]:
    """Classify a single human-written licence label from the manifest."""
    key = _normalise(licence)
    return _verdict_for_key(name, key, unmodified, licence)


# --- SPDX expression handling (installed npm `license` fields) ---------------


def _tokenize_spdx(expr: str) -> list[str]:
    tokens: list[str] = []
    i = 0
    n = len(expr)
    while i < n:
        c = expr[i]
        if c.isspace():
            i += 1
            continue
        if c in "()":
            tokens.append(c)
            i += 1
            continue
        j = i
        while j < n and not expr[j].isspace() and expr[j] not in "()":
            j += 1
        tokens.append(expr[i:j])
        i = j
    return tokens


class _SpdxSyntaxError(ValueError):
    pass


def _parse_spdx(expr: str):
    """Parse an SPDX expression into a nested ('atom'|'or'|'and', ...) tree."""
    tokens = _tokenize_spdx(expr)
    pos = 0

    def peek() -> str | None:
        return tokens[pos] if pos < len(tokens) else None

    def advance() -> str:
        nonlocal pos
        if pos >= len(tokens):
            raise _SpdxSyntaxError("unexpected end of expression")
        tok = tokens[pos]
        pos += 1
        return tok

    def parse_or():
        left = parse_and()
        while peek() == "OR":
            advance()
            right = parse_and()
            left = ("or", left, right)
        return left

    def parse_and():
        left = parse_atom()
        while peek() == "AND":
            advance()
            right = parse_atom()
            left = ("and", left, right)
        return left

    def parse_atom():
        tok = peek()
        if tok is None:
            raise _SpdxSyntaxError("empty licence expression")
        if tok == "(":
            advance()
            node = parse_or()
            if advance() != ")":
                raise _SpdxSyntaxError("missing closing parenthesis")
            return node
        return ("atom", advance())

    node = parse_or()
    if pos != len(tokens):
        raise _SpdxSyntaxError(f"unexpected token {tokens[pos]!r}")
    return node


_RANK = {"compatible": 0, "conditional": 1, "incompatible": 2, "unrecognised": 3}


def _eval_spdx(node, name: str, unmodified: bool) -> tuple[str, str]:
    if node[0] == "atom":
        atom = node[1]
        return _verdict_for_key(name, atom.lower(), unmodified, atom)
    op, left, right = node[0], node[1], node[2]
    lv = _eval_spdx(left, name, unmodified)
    rv = _eval_spdx(right, name, unmodified)
    if op == "or":
        best = min([lv, rv], key=lambda p: _RANK[p[0]])
        return best[0], f"SPDX OR; a compatible alternative is available ({best[1]})" if best[0] in ("compatible", "conditional") else f"SPDX OR; no acceptable alternative ({best[1]})"
    worst = max([lv, rv], key=lambda p: _RANK[p[0]])
    return worst[0], f"SPDX AND; all parts required ({worst[1]})"


def classify_node_licence(name: str, expr: str, unmodified: bool = True) -> tuple[str, str]:
    """Classify an installed package's ``license`` field (may be an SPDX expression)."""
    try:
        node = _parse_spdx(expr)
    except _SpdxSyntaxError as exc:
        return "unrecognised", f"licence expression {expr!r} could not be parsed ({exc})"
    return _eval_spdx(node, name, unmodified)


# --- bundled-core (PyInstaller onefile) audit ---------------------------------
#
# The app ships a self-contained Python core at app/resources/bin/gatepack
# (produced by scripts/bundle_core.py): a PyInstaller onefile binary embedding
# CPython, the PyInstaller bootloader/loader/runtime-hooks, and the collected
# Python packages.  The declared manifest cannot see any of that (it is a list
# of *declared* toolchain/runtime deps), so this section opens the binary and
# enumerates what is actually inside it — the same lesson the npm tree taught:
# the declared set is not the shipped set.
#
# The archive format is parsed here directly (stdlib only: struct + marshal)
# rather than by importing PyInstaller, so the audit does not depend on a
# build-only tool being installed.  The layout follows PyInstaller 6.x
# (PyInstaller/archive/readers.py, PyInstaller/loader/pyimod01_archive.py):
#
#   [ELF bootloader][CArchive ("PKG")][data]
#   CArchive: cookie b"MEI\014\013\012\013\016" + a TOC of (name, offset, ...)
#   PYZ:      b"PYZ\0" + python-bytecode magic + TOC offset + a marshal'd list
#             of (name, entry) pairs (PyInstaller rebuilds it as a dict)
#
# Every licence below was identified by name before being added; an
# unrecognised component is a hard failure, never a defaulted pass.

_CARCHIVE_MAGIC = b"MEI\014\013\012\013\016"
_CARCHIVE_COOKIE = "!8sIIII64s"
_CARCHIVE_TOC_ENTRY = "!IIIIBc"
_PYZ_MAGIC = b"PYZ\0"


class BundleFormatError(Exception):
    """The file is not a parseable PyInstaller onefile archive."""


def _enumerate_bundle(path: Path) -> tuple[list[str], list[tuple[str, str]]]:
    """Parse a PyInstaller onefile binary.

    Returns ``(pyz_modules, carchive_entries)``: the dotted module names frozen
    in the PYZ, and the ``(typecode, name)`` pairs in the CArchive TOC.
    """
    data = path.read_bytes()
    cookie_at = data.rfind(_CARCHIVE_MAGIC)
    if cookie_at == -1:
        raise BundleFormatError(
            "no PyInstaller archive cookie found; not a PyInstaller onefile binary"
        )
    cookie_len = struct.calcsize(_CARCHIVE_COOKIE)
    (_, pkg_length, toc_offset, toc_length, _pyver, _pylib) = struct.unpack(
        _CARCHIVE_COOKIE, data[cookie_at : cookie_at + cookie_len]
    )
    start = cookie_at + cookie_len - pkg_length
    toc_data = data[start + toc_offset : start + toc_offset + toc_length]

    entry_len = struct.calcsize(_CARCHIVE_TOC_ENTRY)
    toc: dict[str, tuple[int, int, int, int, str]] = {}
    pos = 0
    while pos < len(toc_data):
        (entry_length, offset, length, uncompressed, comp_flag, typecode) = struct.unpack(
            _CARCHIVE_TOC_ENTRY, toc_data[pos : pos + entry_len]
        )
        pos += entry_len
        name_len = entry_length - entry_len
        name = toc_data[pos : pos + name_len].rstrip(b"\0").decode("utf-8", "replace")
        pos += name_len
        code = typecode.decode("ascii", "replace")
        if code != "o":
            toc[name] = (offset, length, uncompressed, comp_flag, code)

    modules = _pyz_module_names(data, start, toc)
    return modules, [(code, name) for name, (_, _, _, _, code) in sorted(toc.items())]


def _pyz_module_names(data: bytes, start: int, toc: dict) -> list[str]:
    """List the dotted module names frozen in the archive's PYZ."""
    pyz = next((t for n, t in toc.items() if t[4] == "z"), None)
    if pyz is None:
        raise BundleFormatError("no PYZ archive found in the CArchive")
    offset = pyz[0]
    pos = start + offset
    if data[pos : pos + 4] != _PYZ_MAGIC:
        raise BundleFormatError("PYZ magic mismatch")
    pos += 4
    pos += 4  # python bytecode magic number (4 bytes on CPython >= 3.3)
    toc_offset = struct.unpack("!i", data[pos : pos + 4])[0]
    pyz_obj = marshal.loads(data[start + offset + toc_offset :])
    # PyInstaller marshals a list of (name, entry) pairs and reconstructs the
    # dict on load (`dict(marshal.load(fp))`), so accept either shape.
    if isinstance(pyz_obj, dict):
        return sorted(pyz_obj.keys())
    return sorted(name for name, _entry in pyz_obj)


# Component name -> (licence key, rationale).  The licence keys must exist in
# POLICY.  Each was identified by name before being added; see
# docs/BUILD-NOTES-m18-release.md for exactly where each licence was read from.
BUNDLE_COMPONENTS: dict[str, tuple[str, str]] = {
    "gatepack": ("gpl-3.0-or-later", "the project itself"),
    "cpython": ("python-2.0", "CPython runtime + stdlib (PSF licence)"),
    "pyinstaller-bootloader": ("gpl-2.0-or-later with bootloader-exception", "PyInstaller bootloader + loader; the bootloader exception permits embedding it in a combined executable"),
    "pyinstaller-runtime-hooks": ("apache-2.0", "PyInstaller run-time hooks are Apache-2.0 (see PyInstaller COPYING.txt)"),
    "pydantic": ("mit", "read from pydantic dist-info (License-Expression: MIT)"),
    "pydantic-core": ("mit", "read from pydantic_core dist-info (License-Expression: MIT)"),
    "annotated-types": ("mit", "read from annotated_types dist-info (License-Expression: MIT)"),
    "typing-extensions": ("psf-2.0", "read from typing_extensions dist-info (License-Expression: PSF-2.0)"),
    "typing-inspection": ("mit", "read from typing_inspection dist-info (License-Expression: MIT)"),
    "packaging": ("apache-2.0", "packaging is Apache-2.0 OR BSD-2-Clause; the Apache-2.0 arm is GPL-3.0-compatible"),
    "setuptools": ("mit", "setuptools (MIT); includes the top-level _distutils_hack shim"),
    "openssl": ("apache-2.0", "OpenSSL 3.x (libssl/libcrypto) is Apache-2.0"),
    "zlib": ("zlib", "zlib data-compression library (Zlib licence)"),
    "bzip2": ("bzip2", "bzip2 library (bzip2 licence)"),
    "xz": ("0bsd", "liblzma / xz-utils library is public domain (0BSD)"),
    "libffi": ("mit", "libffi (MIT)"),
    "expat": ("mit", "libexpat (MIT)"),
    "readline": ("gpl-3.0-or-later", "GNU Readline is GPL-3.0-or-later"),
    "ncurses": ("mit", "ncurses / libtinfo is MIT/X11"),
    "libgcc": ("gpl-3.0-or-later with gcc-runtime-library-exception", "GCC runtime (libgcc_s) carries the GCC Runtime Library Exception"),
}

# Top-level module name -> component.  Only *named* third-party packages are
# listed; a non-stdlib top-level module that is not here is unrecognised.
BUNDLE_PACKAGE_COMPONENT: dict[str, str] = {
    "gatepack": "gatepack",
    "pydantic": "pydantic",
    "pydantic_core": "pydantic-core",
    "annotated_types": "annotated-types",
    "typing_extensions": "typing-extensions",
    "typing_inspection": "typing-inspection",
    "packaging": "packaging",
    "setuptools": "setuptools",
    "_distutils_hack": "setuptools",
}

# CPython-runtime-provided top-level modules that are not in
# sys.stdlib_module_names but are generated or OS-provided, not third-party.
_CPYTHON_PROVIDED = frozenset({"sitecustomize", "usercustomize"})
_CPYTHON_PROVIDED_PREFIXES = ("_sysconfigdata_",)

# Shared-library name prefix -> component.
BUNDLE_LIB_PREFIX: list[tuple[str, str]] = [
    ("libpython", "cpython"),
    ("libssl", "openssl"),
    ("libcrypto", "openssl"),
    ("libz.", "zlib"),
    ("libbz2", "bzip2"),
    ("liblzma", "xz"),
    ("libffi", "libffi"),
    ("libexpat", "expat"),
    ("libreadline", "readline"),
    ("libtinfo", "ncurses"),
    ("libgcc_s", "libgcc"),
]


def _classify_bundle_module(name: str, stdlib: frozenset[str]) -> str | None:
    top = name.split(".")[0]
    if top in BUNDLE_PACKAGE_COMPONENT:
        return BUNDLE_PACKAGE_COMPONENT[top]
    if top in stdlib or top in _CPYTHON_PROVIDED:
        return "cpython"
    if any(top.startswith(prefix) for prefix in _CPYTHON_PROVIDED_PREFIXES):
        return "cpython"
    return None


def _classify_bundle_entry(name: str, typecode: str, stdlib: frozenset[str]) -> str | None:
    if name == "base_library.zip" or name.startswith("pyimod") or name.startswith("pyiboot"):
        return "pyinstaller-bootloader"
    if name.startswith("pyi_rth_"):
        return "pyinstaller-runtime-hooks"
    if "/lib-dynload/" in name or name.startswith("libpython"):
        return "cpython"
    if name.startswith("_gatepack_entry") or name.startswith("gatepack") or name.startswith("examples/"):
        return "gatepack"
    if name.startswith("pydantic_core"):
        return "pydantic-core"
    if name.startswith("pydantic"):
        return "pydantic"
    if name.startswith("setuptools") or name.startswith("_distutils_hack"):
        return "setuptools"
    if name.startswith("lib"):
        for prefix, component in BUNDLE_LIB_PREFIX:
            if name.startswith(prefix):
                return component
        return None  # an unrecognised shared library: fail
    if typecode in "mMs":
        return _classify_bundle_module(name, stdlib)
    return None


def audit_bundle(bundle: Path, *, out=print) -> tuple[int, int]:
    """Audit a PyInstaller onefile bundle. Returns (failures, component_count)."""
    try:
        modules, entries = _enumerate_bundle(bundle)
    except BundleFormatError as exc:
        out(f"FAIL [bundle] {bundle.name}: {exc}")
        return 1, 0
    except (OSError, ValueError, EOFError, struct.error) as exc:
        out(f"FAIL [bundle] {bundle.name}: could not be parsed ({exc})")
        return 1, 0

    stdlib = frozenset(sys.stdlib_module_names)
    per_component: dict[str, list[str]] = {}
    unrecognised: list[str] = []

    for mod in modules:
        component = _classify_bundle_module(mod, stdlib)
        if component is None:
            unrecognised.append(mod)
        else:
            per_component.setdefault(component, []).append(mod)

    for typecode, name in entries:
        if name == "PYZ.pyz":
            continue  # the PYZ is a container, not a component; its modules are walked above
        component = _classify_bundle_entry(name, typecode, stdlib)
        if component is None:
            unrecognised.append(name)
        else:
            per_component.setdefault(component, []).append(name)

    failures = 0
    for name in sorted(unrecognised):
        out(
            f"FAIL [bundle] {name}: unrecognised — the bundle ships a component "
            f"with no licence on record; identify its licence and add it to the "
            f"audit after review (never default it to compatible)"
        )
        failures += 1

    for component in sorted(per_component):
        if component not in BUNDLE_COMPONENTS:
            out(f"FAIL [bundle] {component}: unrecognised — no licence on record")
            failures += 1
            continue
        licence, rationale = BUNDLE_COMPONENTS[component]
        verdict, vrationale = _verdict_for_key(component, licence, True, licence)
        if verdict in ("incompatible", "unrecognised"):
            out(f"FAIL [bundle] {component}: {licence!r} — {vrationale}")
            failures += 1
        else:
            count = len(per_component[component])
            out(
                f"ok   [bundle] {component}: {licence!r} ({verdict}) — {rationale} "
                f"({count} file(s)/module(s))"
            )

    return failures, len(per_component)


# --- bundled-toolchain audit (scripts/bundle_toolchain.py) -------------------
#
# The packaged app ships the native EDA toolchain beside the core
# (``app/resources/bin/{yosys,sby,iverilog,vvp,z3,yosys-smtbmc,yosys-witness,
# berkeley-abc}`` plus ``lib/*.so`` shared libraries, Yosys's ``share/`` data
# and Icarus's ``x86_64-linux-gnu/ivl`` support tree).  Each binary is a
# separate work with its own licence — Yosys (ISC), sby (ISC), Icarus Verilog
# (GPL-2.0-*or-later*), z3 (MIT), ABC (UC Berkeley) — so it cannot be classified
# by its file contents; the bundler records the licence of every file it ships
# in ``toolchain-manifest.json`` and this audit checks that manifest against the
# actual tree.  The two rules a previous round got wrong apply here too:
#   * a file present on disk but absent from the manifest is an *unrecognised*
#     component — fail;
#   * a manifest entry whose licence is incompatible (e.g. a hypothetical
#     GPL-2.0-only Icarus) is a hard failure, naming the licence.


def _toolchain_manifest_path(resources_dir: Path) -> Path:
    return resources_dir / "bin" / TOOLCHAIN_MANIFEST


def audit_toolchain(resources_dir: Path, *, out=print) -> tuple[int, int]:
    """Audit the bundled toolchain tree against its manifest.

    Returns ``(failures, file_count)``.  Every file under ``resources_dir``
    (excluding the PyInstaller core ``bin/gatepack``, audited by
    :func:`audit_bundle`, and the manifest itself) must be named by the
    manifest, and every manifest licence must classify as compatible.
    """
    manifest_path = _toolchain_manifest_path(resources_dir)
    if not manifest_path.is_file():
        out(
            f"FAIL [toolchain] {manifest_path.name} not present under "
            f"{resources_dir}; the bundled toolchain must carry its licence manifest"
        )
        return 1, 0

    try:
        data = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as exc:
        out(f"FAIL [toolchain] {manifest_path.name} is not valid JSON ({exc})")
        return 1, 0

    # rel-path (POSIX, relative to resources_dir) -> (licence, component)
    declared: dict[str, tuple[str, str]] = {}
    for tool in data.get("tools", []):
        licence = tool.get("licence", "")
        component = tool.get("component", tool.get("name", "?"))
        for f in tool.get("files", []):
            declared[f"bin/{f}"] = (licence, component)
    for lib in data.get("shared_libs", []):
        f = lib.get("file", "")
        declared[f"bin/{f}" if f else f] = (lib.get("licence", ""), lib.get("component", "?"))
    data_dir_prefixes: list[tuple[str, str, str]] = [
        (d.get("path", ""), d.get("licence", ""), d.get("component", "?"))
        for d in data.get("data_dirs", [])
    ]

    failures = 0
    file_count = 0
    seen: set[str] = set()

    # every file actually present must be declared
    for path in sorted(resources_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(resources_dir).as_posix()
        if rel in ("bin/gatepack", f"bin/{TOOLCHAIN_MANIFEST}"):
            continue
        file_count += 1
        found = _toolchain_file_licence(rel, declared, data_dir_prefixes)
        if found is None:
            failures += 1
            out(
                f"FAIL [toolchain] {rel}: bundled but not named by the toolchain "
                f"manifest — a binary shipped without a licence on record"
            )
            continue
        licence, component = found
        seen.add(rel)
        verdict, rationale = _classify(component, licence, unmodified=True)
        if verdict in ("incompatible", "unrecognised"):
            failures += 1
            out(f"FAIL [toolchain] {rel}: {licence!r} — {rationale}")
        else:
            out(f"ok   [toolchain] {rel}: {licence!r} ({verdict}) — {component}")

    # every declared file must be present (a manifest that claims a file it did
    # not ship is a lie the audit must catch, not trust)
    for rel in sorted(declared):
        if rel not in seen:
            failures += 1
            out(f"FAIL [toolchain] {rel}: declared in the manifest but not present")

    return failures, file_count


def _toolchain_file_licence(
    rel: str,
    declared: dict[str, tuple[str, str]],
    data_dir_prefixes: list[tuple[str, str, str]],
) -> tuple[str, str] | None:
    """Return ``(licence, component)`` for a bundled file, or ``None``."""
    if rel in declared:
        return declared[rel]
    for prefix, licence, component in data_dir_prefixes:
        if rel == prefix or rel.startswith(prefix + "/"):
            return licence, component
    return None


# --- installed-tree walking --------------------------------------------------


def iter_installed_packages(node_tree: Path) -> list[tuple[str, dict]]:
    """Yield (rel_path, package.json dict) for every installed package.

    Walks the real tree, including *nested* ``node_modules`` (npm nests a
    package when the hoisted version does not satisfy a range — e.g.
    ``netlistsvg/node_modules/yargs@6`` under a top-level ``yargs@17``).  The
    returned ``rel_path`` is POSIX-style and relative to ``node_tree``.
    """
    if not node_tree.is_dir():
        return []
    packages: list[tuple[str, dict]] = []

    def walk(dir: Path) -> None:
        for entry in sorted(dir.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            if entry.name == "node_modules":
                walk(entry)
                continue
            pj = entry / "package.json"
            if pj.is_file():
                rel = entry.relative_to(node_tree).as_posix()
                packages.append((rel, json.loads(pj.read_text())))
                nested = entry / "node_modules"
                if nested.is_dir():
                    walk(nested)
            elif entry.name.startswith("@"):
                walk(entry)

    walk(node_tree)
    return packages


def pkg_licence(pkg: dict) -> str | None:
    """Extract the licence from a package.json body (string, SPDX, object or array)."""
    lic = pkg.get("license")
    if lic is None:
        return None
    if isinstance(lic, str):
        return lic
    if isinstance(lic, list):
        parts = [x.get("type") if isinstance(x, dict) else str(x) for x in lic]
        return " AND ".join(parts)
    if isinstance(lic, dict):
        return lic.get("type") or lic.get("name")
    return str(lic)


def package_name(rel_path: str) -> str:
    """Best-effort package name from an install path (last non-node_modules segment)."""
    parts = [p for p in rel_path.split("/") if p != "node_modules"]
    if len(parts) >= 2 and parts[-2].startswith("@"):
        return f"{parts[-2]}/{parts[-1]}"
    return parts[-1] if parts else rel_path


def electron_builder_excludes(pack_config: Path) -> list[str]:
    """Extract node_modules exclude prefixes from an ``electron-builder.yml``.

    The audit must reflect what electron-builder actually packs.  Its
    node-module matcher honours only the *negative* ``!node_modules/.../**``
    globs in the ``files:`` block (positive patterns are dropped for
    ``node_modules``), so this reads exactly those and returns the package-path
    prefixes they name (e.g. ``node_modules/netlistsvg/node_modules/yargs``).
    A missing or unreadable config yields no exclusions, which is the same
    behaviour as a config that excludes nothing.
    """
    if not pack_config.is_file():
        return []
    prefixes: list[str] = []
    in_files = False
    for line in pack_config.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not in_files:
            if stripped == "files:" or line.startswith("files:"):
                in_files = True
            continue
        # Leave the ``files:`` block at the next top-level key.
        if line and not line[0].isspace() and not stripped.startswith("-"):
            break
        if stripped.startswith("- "):
            item = stripped[2:].strip().strip("'\"").strip()
            if item.startswith("!node_modules/"):
                prefix = item[1:]  # drop the '!'
                for suffix in ("/**/*", "/**"):
                    if prefix.endswith(suffix):
                        prefix = prefix[: -len(suffix)]
                        break
                prefix = prefix.rstrip("/")
                if prefix:
                    prefixes.append(prefix)
    return prefixes


def package_is_excluded(rel_path: str, prefixes: list[str]) -> bool:
    """True if the package at ``rel_path`` (relative to the node tree) is packed
    out by one of the electron-builder exclude prefixes."""
    if not prefixes:
        return False
    path = f"node_modules/{rel_path}"
    for prefix in prefixes:
        if path == prefix or path.startswith(prefix + "/"):
            return True
    return False


def shipping_paths_from_lock(lock: dict) -> set[str]:
    """Return the set of install paths npm records as production (non-dev).

    ``package-lock.json`` ``packages`` keys are install paths; a package marked
    ``dev`` or ``devOptional`` does not ship.  This is authoritative about which
    packages electron-builder will pack — far more so than re-deriving the graph
    from ``dependencies`` alone, which silently drops *nested* production
    dependencies (a hoisted ``yargs@17`` hides ``netlistsvg``'s real
    ``yargs@6`` subtree).
    """
    shipped: set[str] = set()
    for path, data in lock.get("packages", {}).items():
        if not path:
            continue
        if data.get("dev") or data.get("devOptional"):
            continue
        shipped.add(path.removeprefix("node_modules/"))
    return shipped


def _dep_names(pkg: dict, *sections: str) -> list[str]:
    out: list[str] = []
    for sec in sections:
        d = pkg.get(sec)
        if isinstance(d, dict):
            out.extend(d.keys())
    return out


def compute_shipping_set_fallback(app_manifest: dict, by_name: dict[str, dict]) -> set[str]:
    """Fallback closure over top-level ``dependencies`` when no lock file exists.

    Assumes a flat/hoisted tree, so it can miss nested version-conflict
    packages; the lock file is the authoritative source and is preferred
    whenever present.
    """
    shipped: set[str] = set()
    queue = list(app_manifest.get("dependencies", {}).keys())
    while queue:
        name = queue.pop()
        if name in shipped:
            continue
        shipped.add(name)
        pkg = by_name.get(name)
        if pkg is None:
            continue
        for dep in _dep_names(pkg, "dependencies", "optionalDependencies", "peerDependencies"):
            if dep not in shipped:
                queue.append(dep)
    return shipped


def audit_node_tree(
    node_tree: Path,
    app_manifest: dict,
    lockfile: Path | None,
    *,
    exclude_prefixes: list[str] | None = None,
    out=print,
) -> tuple[int, int, int]:
    """Audit installed packages. Returns (failures, shipped_count, dev_count)."""
    packages = iter_installed_packages(node_tree)
    by_name = {package_name(rel): pkg for rel, pkg in packages}

    if lockfile is not None and lockfile.is_file():
        shipped = shipping_paths_from_lock(json.loads(lockfile.read_text()))
    else:
        shipped = compute_shipping_set_fallback(app_manifest, by_name)

    exclude_prefixes = exclude_prefixes or []

    failures = 0
    shipped_count = 0
    dev_count = 0

    for rel, pkg in packages:
        name = package_name(rel)
        excluded = package_is_excluded(rel, exclude_prefixes)
        ships = (rel in shipped) and not excluded
        if ships:
            shipped_count += 1
        else:
            dev_count += 1

        lic = pkg_licence(pkg)
        if lic is None:
            verdict, rationale = "unrecognised", "package declares no license field"
        else:
            verdict, rationale = classify_node_licence(name, lic, unmodified=True)

        marker = "ships" if ships else ("excl " if excluded else "dev  ")
        if verdict == "unrecognised":
            failures += 1
            out(f"FAIL [{marker}] {name}: {lic!r} — {rationale}")
        elif verdict == "incompatible" and ships:
            failures += 1
            out(f"FAIL [{marker}] {name}: {lic!r} — {rationale}")
        elif verdict == "incompatible":
            out(f"warn [{marker}] {name}: {lic!r} — {rationale} (not shipped; non-blocking)")
        elif verdict == "conditional":
            out(f"ok   [{marker}] {name}: {lic!r} (conditional, unmodified) — {rationale}")
        elif ships:
            out(f"ok   [{marker}] {name}: {lic!r} (compatible) — {rationale}")
        # dev/excluded-compatible packages are counted but not printed: they
        # are the build-tooling and packed-out noise this audit is told not to
        # drown in.

    return failures, shipped_count, dev_count


def _audit_manifest(manifest: Path, *, out=print, err=print) -> tuple[int, int]:
    data = json.loads(manifest.read_text())
    dependencies = data.get("dependencies", [])
    if not dependencies:
        err("error: dependency manifest declares no dependencies")
        return 1, 0
    failures = 0
    for dep in dependencies:
        name = dep.get("name", "<unnamed>")
        licence = dep.get("licence", "")
        unmodified = bool(dep.get("unmodified", True))
        verdict, rationale = _classify(name, licence, unmodified)
        if verdict in ("incompatible", "unrecognised"):
            out(f"FAIL {name}: {licence!r} — {rationale}")
            failures += 1
        else:
            out(f"ok   {name}: {licence!r} ({verdict}) — {rationale}")
    return failures, len(dependencies)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="audit dependency licences against GPL-3.0")
    parser.add_argument(
        "--manifest",
        default=str(DEFAULT_MANIFEST),
        help="declared-dependency manifest path (default: %(default)s)",
    )
    parser.add_argument(
        "--node-tree",
        default=None,
        help="installed npm tree to audit (opt-in; default: %(default)s)",
    )
    parser.add_argument(
        "--app-manifest",
        default=str(DEFAULT_APP_MANIFEST),
        help="app package.json used to split shipped vs dev (default: %(default)s)",
    )
    parser.add_argument(
        "--lockfile",
        default=None,
        help="package-lock.json used for the authoritative shipped set "
        "(default: <app-manifest dir>/package-lock.json)",
    )
    parser.add_argument(
        "--require-node-tree",
        action="store_true",
        help="audit the default app/node_modules and fail if it is absent or empty",
    )
    parser.add_argument(
        "--bundle",
        default=None,
        help="PyInstaller onefile core bundle to audit (default: %(default)s)",
    )
    parser.add_argument(
        "--require-bundle",
        action="store_true",
        help="audit the default bundled core and fail if it is absent or empty",
    )
    parser.add_argument(
        "--toolchain",
        default=None,
        help="bundled toolchain resources dir to audit against its manifest "
        "(default: %(default)s)",
    )
    parser.add_argument(
        "--require-toolchain",
        action="store_true",
        help="audit the default bundled toolchain and fail if it is absent",
    )
    parser.add_argument(
        "--pack-config",
        default=str(REPO / "app" / "electron-builder.yml"),
        help="electron-builder.yml whose 'files' excludes determine what packs "
        "(default: %(default)s); a missing file means no exclusions",
    )
    args = parser.parse_args(argv)

    manifest = Path(args.manifest)
    if not manifest.exists():
        print(f"error: dependency manifest not found: {manifest}", file=sys.stderr)
        return 1

    manifest_failures, manifest_count = _audit_manifest(
        manifest, out=lambda s: print(s), err=lambda s: print(s, file=sys.stderr)
    )
    total_failures = manifest_failures

    # The installed-tree audit is opt-in: the declared-manifest audit is the
    # default (and the only thing the `test` job, which has no node_modules,
    # can run).  --require-node-tree selects the default tree and demands it.
    if args.node_tree is not None:
        node_tree = Path(args.node_tree)
    elif args.require_node_tree:
        node_tree = DEFAULT_NODE_TREE
    else:
        node_tree = None

    node_failures = 0
    shipped_count = 0
    dev_count = 0

    if node_tree is None:
        print("note: installed-tree audit not requested (pass --require-node-tree or --node-tree)")
    elif not node_tree.is_dir():
        print(f"error: installed tree not present: {node_tree}", file=sys.stderr)
        return 1
    else:
        packages = iter_installed_packages(node_tree)
        if not packages:
            print(f"error: installed tree is empty: {node_tree}", file=sys.stderr)
            return 1
        app_manifest_path = Path(args.app_manifest)
        if not app_manifest_path.exists():
            print(
                f"error: app manifest not found ({app_manifest_path}); cannot "
                f"distinguish shipped from dev dependencies",
                file=sys.stderr,
            )
            return 1
        lockfile = Path(args.lockfile) if args.lockfile else app_manifest_path.parent / "package-lock.json"
        app_manifest = json.loads(app_manifest_path.read_text())
        node_failures, shipped_count, dev_count = audit_node_tree(
            node_tree,
            app_manifest,
            lockfile,
            exclude_prefixes=electron_builder_excludes(Path(args.pack_config)),
            out=print,
        )
        total_failures += node_failures

    # The bundled-core audit is opt-in for the same reason as the node tree:
    # the `test` job has no PyInstaller and no bundle, so it audits the manifest
    # only.  --require-bundle selects the default bundle and demands it.
    if args.bundle is not None:
        bundle = Path(args.bundle)
    elif args.require_bundle:
        bundle = DEFAULT_BUNDLE
    else:
        bundle = None

    bundle_failures = 0
    bundle_components = 0
    if bundle is None:
        print("note: bundled-core audit not requested (pass --require-bundle or --bundle)")
    elif not bundle.is_file():
        print(f"error: bundled core not present: {bundle}", file=sys.stderr)
        return 1
    else:
        bundle_failures, bundle_components = audit_bundle(bundle, out=lambda s: print(s))
        total_failures += bundle_failures

    # The bundled-toolchain audit is opt-in for the same reason as the node tree
    # and bundle: the `test` job has no docker and no bundled toolchain.
    if args.toolchain is not None:
        toolchain = Path(args.toolchain)
    elif args.require_toolchain:
        toolchain = DEFAULT_TOOLCHAIN
    else:
        toolchain = None

    toolchain_failures = 0
    toolchain_files = 0
    if toolchain is None:
        print("note: bundled-toolchain audit not requested (pass --require-toolchain or --toolchain)")
    elif not _toolchain_manifest_path(toolchain).is_file():
        print(f"error: toolchain manifest not present: {_toolchain_manifest_path(toolchain)}", file=sys.stderr)
        return 1
    else:
        toolchain_failures, toolchain_files = audit_toolchain(
            toolchain, out=lambda s: print(s)
        )
        total_failures += toolchain_failures

    if total_failures:
        print(
            f"licence audit: {total_failures} dependency(s) not GPL-3.0-compatible",
            file=sys.stderr,
        )
        return 1

    if shipped_count + dev_count:
        node_note = f"installed tree {shipped_count} shipped + {dev_count} dev/other"
    elif node_tree is None:
        node_note = "installed tree not requested"
    else:
        node_note = "installed tree empty"
    if bundle is None:
        bundle_note = "bundle not requested"
    else:
        bundle_note = f"bundle {bundle_components} component(s)"
    if toolchain is None:
        toolchain_note = "toolchain not requested"
    else:
        toolchain_note = f"toolchain {toolchain_files} file(s)"
    print(
        f"licence audit: {manifest_count + shipped_count + dev_count + bundle_components} "
        f"dependency(s) GPL-3.0-compatible ({manifest_count} manifest, {node_note}, "
        f"{bundle_note}, {toolchain_note})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
