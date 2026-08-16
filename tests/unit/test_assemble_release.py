"""Tests for the release-assembly step (``scripts/assemble_release.py``).

This is the piece that makes the unsigned state *visible*: it turns the
per-platform ``SIGNING-STATUS.txt`` markers into a ``SHA256SUMS.txt`` and a
release body that say "unsigned" when they are.  The properties that matter:

1. checksums are real (``sha256sum -c`` must verify them) and cover every
   artefact;
2. an unsigned build announces itself — a user must learn "unsigned" from the
   project, not from Gatekeeper;
3. a signed build does not say "unsigned";
4. absent any marker the status is ``unknown``, never a fabricated "signed";
5. the output is deterministic.
"""

from __future__ import annotations

import hashlib
import importlib.util
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "assemble_release.py"


def _load():
    spec = importlib.util.spec_from_file_location("assemble_release_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_source(root: Path, statuses: dict[str, str]) -> Path:
    """A per-platform artefact tree with the given SIGNING-STATUS markers."""
    for platform, status in statuses.items():
        d = root / f"gatepack-{platform}"
        d.mkdir(parents=True)
        (d / "SIGNING-STATUS.txt").write_text(status + "\n")
        (d / f"gatepack-core-{platform}").write_text(f"binary-{platform}")
    return root


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_checksums_are_real_and_complete(tmp_path):
    mod = _load()
    source = _make_source(tmp_path / "in", {"linux": "unsigned"})
    mod.assemble(source, tmp_path / "out", "0.1.0")

    sums = (tmp_path / "out" / "SHA256SUMS").read_text()
    expected = _sha256(b"binary-linux")
    assert f"{expected}  gatepack-core-linux" in sums

    # `sha256sum -c` must verify it (proves the hashes are genuine).
    proc = subprocess.run(
        ["sha256sum", "-c", "SHA256SUMS"],
        cwd=str(tmp_path / "out"),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "OK" in proc.stdout


def test_unsigned_announces_itself(tmp_path):
    mod = _load()
    source = _make_source(tmp_path / "in", {"linux": "unsigned", "windows": "unsigned"})
    written = mod.assemble(source, tmp_path / "out", "0.1.0")

    sums_text = written["SHA256SUMS.txt"].read_text()
    notes = written["RELEASE-NOTES.md"].read_text()
    assert "UNSIGNED" in sums_text
    assert "UNSIGNED" in notes
    assert "Gatekeeper" in notes and "SmartScreen" in notes


def test_signed_does_not_claim_unsigned(tmp_path):
    mod = _load()
    source = _make_source(tmp_path / "in", {"linux": "signed", "macos": "signed"})
    written = mod.assemble(source, tmp_path / "out", "0.1.0")

    sums_text = written["SHA256SUMS.txt"].read_text()
    notes = written["RELEASE-NOTES.md"].read_text()
    assert "UNSIGNED" not in sums_text
    assert "Gatekeeper" not in notes
    assert "unsigned" not in notes


def test_missing_marker_reports_unknown_not_signed(tmp_path):
    mod = _load()
    source = tmp_path / "in"
    d = source / "gatepack-linux"
    d.mkdir(parents=True)
    (d / "gatepack-core-linux").write_text("x")
    written = mod.assemble(source, tmp_path / "out", "0.1.0")
    assert "unknown" in written["SHA256SUMS.txt"].read_text()


def test_mixed_status_is_reported_as_mixed(tmp_path):
    mod = _load()
    source = _make_source(tmp_path / "in", {"linux": "signed", "windows": "unsigned"})
    written = mod.assemble(source, tmp_path / "out", "0.1.0")
    assert "mixed" in written["SHA256SUMS.txt"].read_text()


def test_output_is_deterministic(tmp_path):
    mod = _load()
    source = _make_source(tmp_path / "in", {"linux": "unsigned"})
    a = mod.assemble(source, tmp_path / "out-a", "0.1.0")
    b = mod.assemble(source, tmp_path / "out-b", "0.1.0")
    for name in ("SHA256SUMS", "SHA256SUMS.txt", "RELEASE-NOTES.md"):
        assert a[name].read_text() == b[name].read_text()
