"""Tests for the version-consistency check (``scripts/version_check.py``).

The check exists because a previous milestone recorded version skew between
``pyproject.toml`` and ``app/package.json`` (docs/M6-FINDINGS.md §5).  The
tag form (``--tag``) guards the other direction: a tag-triggered release must
not be cut from a tree whose version disagrees with the tag.  Every path here
is the *failure* path — a check that cannot fail is worth nothing.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CHECK = REPO / "scripts" / "version_check.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECK), *args],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )


def _write_pair(root: Path, py_version: str, js_version: str) -> tuple[Path, Path]:
    pyproject = root / "pyproject.toml"
    pyproject.write_text(f'[project]\nname = "gatepack"\nversion = "{py_version}"\n')
    package_json = root / "package.json"
    package_json.write_text(json.dumps({"name": "gatepack-app", "version": js_version}))
    return pyproject, package_json


def test_committed_versions_agree():
    proc = _run()
    assert proc.returncode == 0, proc.stderr
    assert "0.1.0" in proc.stdout


def test_drift_fails(tmp_path):
    pyproject, package_json = _write_pair(tmp_path, "0.1.0", "0.2.0")
    proc = _run("--pyproject", str(pyproject), "--package-json", str(package_json))
    assert proc.returncode == 1
    assert "drift" in proc.stderr


def test_tag_matches_version(tmp_path):
    pyproject, package_json = _write_pair(tmp_path, "0.1.0", "0.1.0")
    proc = _run(
        "--pyproject", str(pyproject), "--package-json", str(package_json), "--tag", "v0.1.0"
    )
    assert proc.returncode == 0, proc.stderr
    assert "tag agrees" in proc.stdout


def test_tag_mismatch_fails(tmp_path):
    pyproject, package_json = _write_pair(tmp_path, "0.1.0", "0.1.0")
    proc = _run(
        "--pyproject", str(pyproject), "--package-json", str(package_json), "--tag", "v0.2.0"
    )
    assert proc.returncode == 1
    assert "mismatch" in proc.stderr


def test_tag_without_v_prefix_matches(tmp_path):
    pyproject, package_json = _write_pair(tmp_path, "0.1.0", "0.1.0")
    proc = _run(
        "--pyproject", str(pyproject), "--package-json", str(package_json), "--tag", "0.1.0"
    )
    assert proc.returncode == 0, proc.stderr
