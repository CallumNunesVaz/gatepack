"""Tests for the installer-reproducibility measurement (``scripts/repro_installer.py``).

The script is a *report*, not a gate: it must say REPRODUCIBLE when two build
outputs are byte-identical and NOT REPRODUCIBLE when any file differs, and it
must say NOT MEASURED (never a fabricated verdict) when electron-builder is
unavailable.  These pin the comparison verdict and the not-measured path; the
two-build electron-builder run is exercised only by hand / in CI because it is
minutes long.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "repro_installer.py"


def _load():
    spec = importlib.util.spec_from_file_location("repro_installer_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_compare_identical_trees():
    mod = _load()
    result = mod._compare({"a": "h1", "b": "h2"}, {"a": "h1", "b": "h2"})
    assert result["total"] == 2
    assert result["identical"] == ["a", "b"]
    assert result["differing"] == []
    assert result["missing"] == []


def test_compare_flags_differing_files():
    mod = _load()
    result = mod._compare({"a": "h1", "b": "h2"}, {"a": "h1", "b": "h3"})
    assert result["differing"] == ["b"]
    assert result["identical"] == ["a"]


def test_compare_flags_missing_files():
    mod = _load()
    result = mod._compare({"a": "h1", "b": "h2"}, {"a": "h1"})
    assert result["missing"] == ["b"]


def test_hash_tree(tmp_path):
    mod = _load()
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.txt").write_text("same")
    (tmp_path / "sub" / "b.txt").write_text("content")
    tree = mod._hash_tree(tmp_path)
    assert set(tree) == {"a.txt", "sub/b.txt"}
    assert len(tree["a.txt"]) == 64  # a sha256 hex digest


def test_not_measured_without_npx(tmp_path, monkeypatch):
    # Strip npx from PATH: the script must report NOT MEASURED, not a verdict.
    monkeypatch.setenv("PATH", "/nonexistent")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--targets", "dir", "--output-root", str(tmp_path / "o")],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0
    assert "NOT MEASURED" in proc.stdout
