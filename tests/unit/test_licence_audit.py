"""Tests for the §4 licence audit script.

The audit is a standalone CI script, so it is exercised via subprocess exactly
as CI runs it.  The policy that matters most — EPL-2.0 accepted *conditionally*
only when consumed unmodified — is pinned here so a future edit cannot silently
turn an assumption into an assertion.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
AUDIT = REPO / "scripts" / "licence_audit.py"


def _run(manifest: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(AUDIT), "--manifest", str(manifest)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )


def test_committed_manifest_is_compatible():
    proc = _run(REPO / "scripts" / "dependencies.json")
    assert proc.returncode == 0, proc.stderr
    assert "GPL-3.0-compatible" in proc.stdout


def test_epl_2_0_requires_unmodified(tmp_path):
    manifest = tmp_path / "deps.json"
    manifest.write_text(
        json.dumps(
            {
                "dependencies": [
                    {
                        "name": "elkjs",
                        "licence": "EPL-2.0",
                        "unmodified": False,
                    }
                ]
            }
        )
    )
    proc = _run(manifest)
    assert proc.returncode == 1
    assert "elkjs" in proc.stdout


def test_epl_2_0_unmodified_is_accepted(tmp_path):
    manifest = tmp_path / "deps.json"
    manifest.write_text(
        json.dumps(
            {
                "dependencies": [
                    {
                        "name": "elkjs",
                        "licence": "EPL-2.0",
                        "unmodified": True,
                    }
                ]
            }
        )
    )
    proc = _run(manifest)
    assert proc.returncode == 0


def test_gpl_2_0_only_is_incompatible(tmp_path):
    manifest = tmp_path / "deps.json"
    manifest.write_text(
        json.dumps({"dependencies": [{"name": "x", "licence": "GPL-2.0"}]})
    )
    proc = _run(manifest)
    assert proc.returncode == 1
    assert "GPL-2.0-only" in proc.stdout


def test_unrecognised_licence_is_incompatible(tmp_path):
    manifest = tmp_path / "deps.json"
    manifest.write_text(
        json.dumps({"dependencies": [{"name": "x", "licence": "WTFPL-None"}]})
    )
    proc = _run(manifest)
    assert proc.returncode == 1
    assert "no policy entry" in proc.stdout
