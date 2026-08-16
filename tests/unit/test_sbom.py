"""Tests for the release SBOM generator (``scripts/sbom.py``).

The SBOM must reuse ``scripts/licence_audit.py``'s enumeration — it imports the
audit module rather than re-walking the trees — so the two can never disagree
about what is in the npm tree or the bundled core.  These tests build a
synthetic node tree and a synthetic PyInstaller archive (the same shape the
audit's own tests use) and pin the properties that matter:

1. shipped vs dev is read from the lock file, not guessed;
2. the bundle's components and licences come from the audit's table;
3. ``--require-node-tree`` / ``--require-bundle`` fail when the input is absent,
   so an SBOM that enumerated nothing cannot be mistaken for a generated one;
4. the output is deterministic (no timestamp, sorted components).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SBOM = REPO / "scripts" / "sbom.py"

# The audit's own synthetic-bundle builder — reused, not reimplemented, so the
# SBOM test and the audit test agree on the archive shape.
from tests.unit.test_licence_audit_bundle import build_synthetic_bundle  # noqa: E402


def _load_sbom():
    spec = importlib.util.spec_from_file_location("sbom_under_test", SBOM)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_node_tree(root: Path) -> None:
    (root / "node_modules" / "foo").mkdir(parents=True)
    (root / "node_modules" / "foo" / "package.json").write_text(
        json.dumps({"name": "foo", "version": "1.0.0", "license": "MIT"})
    )
    (root / "node_modules" / "bar").mkdir(parents=True)
    (root / "node_modules" / "bar" / "package.json").write_text(
        json.dumps({"name": "bar", "version": "2.0.0", "license": "Apache-2.0"})
    )
    (root / "package-lock.json").write_text(
        json.dumps(
            {
                "packages": {
                    "node_modules/foo": {"version": "1.0.0"},
                    "node_modules/bar": {"version": "2.0.0", "dev": True},
                }
            }
        )
    )
    (root / "package.json").write_text(json.dumps({"name": "gatepack-app", "version": "0.1.0"}))


def test_sbom_lists_npm_components_with_shipped_flags(tmp_path):
    _make_node_tree(tmp_path)
    mod = _load_sbom()
    sbom = mod.generate_sbom(
        node_tree=tmp_path / "node_modules",
        app_manifest=tmp_path / "package.json",
        lockfile=tmp_path / "package-lock.json",
        pack_config=tmp_path / "electron-builder.yml",  # absent -> no excludes
        bundle=None,
        name="gatepack",
        version="0.1.0",
    )
    by_name = {c["name"]: c for c in sbom["components"]}
    assert set(by_name) == {"foo", "bar"}
    assert by_name["foo"]["licenses"][0]["expression"] == "MIT"
    assert by_name["foo"]["purl"] == "pkg:npm/foo@1.0.0"
    shipped = {p["value"] for p in by_name["foo"]["properties"] if p["name"] == "gatepack:shipped"}
    dev = {p["value"] for p in by_name["bar"]["properties"] if p["name"] == "gatepack:shipped"}
    assert shipped == {"true"}
    assert dev == {"false"}


def test_sbom_bundle_components_come_from_the_audit(tmp_path):
    bundle = build_synthetic_bundle(
        tmp_path / "core",
        modules=["gatepack", "pydantic", "os", "sys"],
        entries=[("b", "libssl.so.3")],
    )
    mod = _load_sbom()
    sbom = mod.generate_sbom(
        node_tree=None,
        app_manifest=tmp_path / "package.json",
        lockfile=None,
        pack_config=tmp_path / "electron-builder.yml",
        bundle=bundle,
        name="gatepack",
        version="0.1.0",
    )
    by_name = {c["name"]: c for c in sbom["components"]}
    assert "pydantic" in by_name
    assert by_name["pydantic"]["licenses"][0]["license"]["name"] == "mit"
    assert "openssl" in by_name
    assert by_name["openssl"]["licenses"][0]["license"]["name"] == "apache-2.0"
    assert "gatepack" in by_name
    assert by_name["gatepack"]["licenses"][0]["license"]["name"] == "gpl-3.0-or-later"


def test_sbom_is_deterministic(tmp_path):
    _make_node_tree(tmp_path)
    mod = _load_sbom()
    kw = dict(
        node_tree=tmp_path / "node_modules",
        app_manifest=tmp_path / "package.json",
        lockfile=tmp_path / "package-lock.json",
        pack_config=tmp_path / "electron-builder.yml",
        bundle=None,
        name="gatepack",
        version="0.1.0",
    )
    a = json.dumps(mod.generate_sbom(**kw), sort_keys=True)
    b = json.dumps(mod.generate_sbom(**kw), sort_keys=True)
    assert a == b


def test_require_node_tree_fails_when_absent(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(SBOM), "--node-tree", str(tmp_path / "nope"), "--require-node-tree"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "not present or empty" in proc.stderr


def test_require_bundle_fails_when_absent(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(SBOM), "--bundle", str(tmp_path / "nope"), "--require-bundle"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "not present" in proc.stderr
