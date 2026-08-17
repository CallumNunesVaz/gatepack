"""Tests for the bundled-toolchain licence audit (scripts/licence_audit.py).

The bundled toolchain is a set of separate works (Yosys ISC, sby ISC, Icarus
GPL-2.0-or-later, z3 MIT, ABC UC-Berkeley) whose licences cannot be read from
their binaries; the bundler records them in ``toolchain-manifest.json`` and the
audit checks that manifest against the actual tree.

The property that matters — and that a previous round would have got wrong — is
that the audit fails closed in both directions:

1. a *declared* binary whose licence is incompatible (a hypothetical
   GPL-2.0-only Icarus — the "or later" is what makes the real one compatible)
   is rejected, naming the licence;
2. a *present but undeclared* binary (one the manifest does not name) is
   rejected — a binary shipped without a licence on record is a hole, not a
   pass.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
AUDIT = REPO / "scripts" / "licence_audit.py"


def _load_audit_module():
    spec = importlib.util.spec_from_file_location("licence_audit_under_test", AUDIT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_manifest(resources: Path, tools: list[dict]) -> None:
    (resources / "bin").mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "tools": tools,
        "shared_libs": [],
        "data_dirs": [],
    }
    (resources / "bin" / "toolchain-manifest.json").write_text(
        json.dumps(manifest) + "\n"
    )


def _run(resources: Path):
    module = _load_audit_module()
    out: list[str] = []
    failures, count = module.audit_toolchain(resources, out=lambda s: out.append(s))
    return failures, count, "\n".join(out)


def test_toolchain_audit_accepts_compatible_toolchain(tmp_path):
    resources = tmp_path / "resources"
    (resources / "bin").mkdir(parents=True)
    _write_manifest(
        resources,
        [
            {
                "name": "yosys",
                "component": "Yosys",
                "licence": "ISC",
                "files": ["yosys"],
            },
            {
                "name": "iverilog",
                "component": "Icarus Verilog",
                "licence": "GPL-2.0-or-later",
                "files": ["iverilog"],
            },
        ],
    )
    (resources / "bin" / "yosys").write_bytes(b"x")
    (resources / "bin" / "iverilog").write_bytes(b"x")

    failures, count, text = _run(resources)
    assert failures == 0, text
    assert count == 2
    assert "GPL-2.0-or-later" in text


def test_toolchain_audit_rejects_incompatible_licence(tmp_path):
    # The "make it fail" case the prompt demands: a bundled binary declared with
    # a known-*incompatible* licence (GPL-2.0-only) must reject, naming it.
    # GPL-2.0-only is incompatible with this GPL-3.0 app; the "or later" clause
    # of the real Icarus is exactly what the audit must *not* infer away.
    resources = tmp_path / "resources"
    (resources / "bin").mkdir(parents=True)
    _write_manifest(
        resources,
        [
            {
                "name": "iverilog",
                "component": "Icarus Verilog",
                "licence": "GPL-2.0-only",
                "files": ["iverilog"],
            }
        ],
    )
    (resources / "bin" / "iverilog").write_bytes(b"x")

    failures, _count, text = _run(resources)
    assert failures >= 1
    assert "GPL-2.0-only" in text
    assert "incompatible" in text or "not compatible" in text


def test_toolchain_audit_rejects_undeclared_binary(tmp_path):
    # A binary present in the tree but absent from the manifest has no licence
    # on record; the audit must reject it rather than assume it is compatible.
    resources = tmp_path / "resources"
    (resources / "bin").mkdir(parents=True)
    _write_manifest(
        resources,
        [{"name": "yosys", "component": "Yosys", "licence": "ISC", "files": ["yosys"]}],
    )
    (resources / "bin" / "yosys").write_bytes(b"x")
    (resources / "bin" / "mystery-tool").write_bytes(b"x")

    failures, _count, text = _run(resources)
    assert failures >= 1
    assert "mystery-tool" in text
    assert "not named" in text


def test_toolchain_audit_rejects_declared_but_missing_file(tmp_path):
    # A manifest that claims a file it did not ship is a lie; the audit must not
    # trust it (a "declared compatible" entry with nothing on disk proves
    # nothing about what actually ships).
    resources = tmp_path / "resources"
    (resources / "bin").mkdir(parents=True)
    _write_manifest(
        resources,
        [
            {
                "name": "yosys",
                "component": "Yosys",
                "licence": "ISC",
                "files": ["yosys", "yosys-extra"],
            }
        ],
    )
    (resources / "bin" / "yosys").write_bytes(b"x")

    failures, _count, text = _run(resources)
    assert failures >= 1
    assert "yosys-extra" in text
    assert "not present" in text


def test_toolchain_audit_fails_without_manifest(tmp_path):
    resources = tmp_path / "resources"
    (resources / "bin").mkdir(parents=True)
    (resources / "bin" / "yosys").write_bytes(b"x")

    failures, _count, text = _run(resources)
    assert failures == 1
    assert "toolchain-manifest.json" in text
