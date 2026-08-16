"""Tests for the bundled-core licence audit (§4, extended to the PyInstaller core).

The audit must see what the bundle *actually contains*, not the declared
dependency list.  These tests build a minimal but structurally-faithful
PyInstaller onefile archive (bootloader prefix + CArchive + PYZ, the exact
layout parsed by ``scripts/licence_audit.py``) so the enumeration and
classification paths are exercised without PyInstaller being installed.

The two properties that matter, both of which a previous round would have got
wrong:

1. A component the table does not name is a **failure**, not a pass — an
   unrecognised Python package (``evilpkg``) and an unrecognised shared library
   (``libevil.so.1``) must both reject.
2. A component with a known-*incompatible* licence rejects with that licence
   named — not defaulted to compatible.
"""

from __future__ import annotations

import importlib.util
import json
import marshal
import struct
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
AUDIT = REPO / "scripts" / "licence_audit.py"
MANIFEST = REPO / "scripts" / "dependencies.json"


def _load_audit_module():
    spec = importlib.util.spec_from_file_location("licence_audit_under_test", AUDIT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_synthetic_bundle(
    path: Path,
    modules: list[str],
    entries: list[tuple[str, str]] | None = None,
) -> Path:
    """Write a minimal PyInstaller onefile archive with the given PYZ modules.

    ``modules`` are dotted module names frozen in the PYZ; ``entries`` are
    ``(typecode, name)`` CArchive TOC entries (e.g. ``("b", "libssl.so.3")``).
    The bootloader prefix is arbitrary bytes — the audit never inspects it.
    """
    entries = entries or []
    bootloader = b"\x7fELF" + b"X" * 60

    pyz_toc = [(name, (0, 0, 0)) for name in modules]
    pyz_body = (
        b"PYZ\x00"
        + b"\x00" * 4  # python bytecode magic (4 bytes on CPython >= 3.3)
        + struct.pack("!i", 12)  # TOC immediately follows the 12-byte header
        + marshal.dumps(pyz_toc)
    )

    def toc_entry(typecode: str, name: str, offset: int, length: int) -> bytes:
        name_b = name.encode()
        entry_length = 18 + len(name_b)
        if entry_length % 16:
            entry_length += 16 - (entry_length % 16)
        name_padded = name_b + b"\0" * (entry_length - 18 - len(name_b))
        return (
            struct.pack("!IIIIBc", entry_length, offset, length, length, 0, typecode.encode())
            + name_padded
        )

    toc_bytes = toc_entry("z", "PYZ.pyz", 0, len(pyz_body))
    for typecode, name in entries:
        toc_bytes += toc_entry(typecode, name, 0, 0)

    toc_offset = len(pyz_body)
    toc_length = len(toc_bytes)
    cookie_len = struct.calcsize("!8sIIII64s")
    pkg_length = len(pyz_body) + toc_length + cookie_len
    cookie = struct.pack(
        "!8sIIII64s",
        b"MEI\014\013\012\013\016",
        pkg_length,
        toc_offset,
        toc_length,
        0x030C0000,
        b"libpython3.12.so.1.0",
    )

    path.write_bytes(bootloader + pyz_body + toc_bytes + cookie)
    return path


def _run_cli(bundle: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(AUDIT), "--bundle", str(bundle), *extra],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )


def test_bundle_audit_accepts_known_components(tmp_path):
    bundle = build_synthetic_bundle(
        tmp_path / "core",
        modules=["gatepack", "gatepack.cli", "pydantic", "os", "sys", "json"],
        entries=[("b", "libssl.so.3"), ("b", "libpython3.12.so.1.0")],
    )
    proc = _run_cli(bundle)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "gatepack: 'gpl-3.0-or-later'" in proc.stdout
    assert "pydantic: 'mit'" in proc.stdout
    assert "openssl: 'apache-2.0'" in proc.stdout


def test_bundle_audit_rejects_unknown_python_package(tmp_path):
    bundle = build_synthetic_bundle(
        tmp_path / "core",
        modules=["gatepack", "pydantic", "os", "evilpkg"],
    )
    proc = _run_cli(bundle)
    assert proc.returncode == 1, proc.stdout
    assert "evilpkg" in proc.stdout
    assert "unrecognised" in proc.stdout


def test_bundle_audit_rejects_unknown_shared_library(tmp_path):
    bundle = build_synthetic_bundle(
        tmp_path / "core",
        modules=["gatepack", "os"],
        entries=[("b", "libevil.so.1")],
    )
    proc = _run_cli(bundle)
    assert proc.returncode == 1, proc.stdout
    assert "libevil.so.1" in proc.stdout


def test_bundle_audit_rejects_incompatible_component(tmp_path):
    # The "make it fail" case: a component whose licence is on record and is
    # *incompatible* (GPL-2.0-only) must reject, naming the licence.
    module = _load_audit_module()
    module.BUNDLE_PACKAGE_COMPONENT["evilpkg"] = "evilcomponent"
    module.BUNDLE_COMPONENTS["evilcomponent"] = (
        "gpl-2.0-only",
        "test: a known-incompatible licence",
    )
    bundle = build_synthetic_bundle(tmp_path / "core", modules=["gatepack", "evilpkg"])
    out: list[str] = []
    failures, _count = module.audit_bundle(bundle, out=lambda s: out.append(s))
    text = "\n".join(out)
    assert failures >= 1
    assert "gpl-2.0-only" in text
    assert "evilcomponent" in text


def test_bundle_audit_rejects_non_pyinstaller_file(tmp_path):
    not_a_bundle = tmp_path / "core"
    not_a_bundle.write_text("this is not a PyInstaller binary\n")
    proc = _run_cli(not_a_bundle)
    assert proc.returncode == 1, proc.stdout
    assert "PyInstaller" in proc.stdout


def test_require_bundle_fails_when_absent(tmp_path):
    proc = subprocess.run(
        [
            sys.executable,
            str(AUDIT),
            "--bundle",
            str(tmp_path / "does-not-exist"),
            "--require-bundle",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "not present" in proc.stderr
