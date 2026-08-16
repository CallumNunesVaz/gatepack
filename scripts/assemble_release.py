#!/usr/bin/env python3
"""Assemble the files that make a release *verifiable and honest* (§5.2, M18).

Takes a directory of per-platform artefacts (as produced by the release
matrix and downloaded into one tree) and writes, into an output directory:

  * ``SHA256SUMS`` — a standard GNU ``sha256sum`` listing, one line per
    artefact, sorted.  This is the machine-verifiable part: ``sha256sum -c``.
  * ``SHA256SUMS.txt`` — the same checksums plus the *signing status*, so a
    user downloading an unsigned binary learns that from the project, not from
    Gatekeeper / SmartScreen.
  * ``RELEASE-NOTES.md`` — the GitHub release body, carrying the same unsigned
    announcement when it applies.

Signing status is read from a ``SIGNING-STATUS.txt`` per platform (written by
the matrix job that built it — each platform says whether *its* installer was
signed).  The script never invents a status: absent any marker it says
``unknown``, and a mixed status is reported as mixed rather than collapsed to
"all signed" or "all unsigned".

Deterministic by construction: checksums are sorted and no timestamp is
written, so two runs over the same inputs are byte-identical.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

META_FILENAMES = frozenset(
    {"SIGNING-STATUS.txt", "SHA256SUMS", "SHA256SUMS.txt", "RELEASE-NOTES.md"}
)

_UNSIGNED_NOTICE = (
    "THESE INSTALLERS ARE UNSIGNED.\n"
    "No code-signing credentials are provisioned for this repository, and none\n"
    "are fabricated. macOS Gatekeeper and Windows SmartScreen will warn on\n"
    "these files; that is expected and visible by design. Do not treat this\n"
    "release as signed. Supply credentials per docs/RELEASING.md and re-run the\n"
    "release workflow to produce signed installers."
)


def _collect_artefacts(source: Path) -> tuple[list[Path], set[str]]:
    """Return (artefact files, distinct signing statuses) under ``source``."""
    files: list[Path] = []
    statuses: set[str] = set()
    for p in sorted(source.rglob("*")):
        if not p.is_file():
            continue
        if p.name == "SIGNING-STATUS.txt":
            statuses.update(line.strip() for line in p.read_text().splitlines() if line.strip())
            continue
        if p.name in META_FILENAMES:
            continue
        files.append(p)
    return files, statuses


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assemble(source: Path, out_dir: Path, version: str) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    artefacts, statuses = _collect_artefacts(source)

    if not statuses:
        status_text = "unknown"
    else:
        status_text = " ".join(sorted(statuses))

    unsigned = "unsigned" in statuses
    signed = "signed" in statuses

    # Flatten artefacts (installers, core bundles, SBOMs) into the output dir.
    checksums: list[tuple[str, str]] = []
    for src in artefacts:
        dst = out_dir / src.name
        if dst.exists():
            # Two platforms could in principle collide on a name; the matrix
            # names artefacts per platform precisely so this never happens.
            dst = out_dir / f"{src.parent.name}-{src.name}"
        shutil.copy2(src, dst)
        checksums.append((_sha256(dst), dst.name))

    checksums.sort(key=lambda pair: pair[1])

    with open(out_dir / "SHA256SUMS", "w", encoding="utf-8") as fh:
        for digest, name in checksums:
            fh.write(f"{digest}  {name}\n")

    if unsigned and signed:
        verdict = "mixed — some platforms signed, some unsigned; treat the unsigned ones as unsigned"
    elif signed:
        verdict = "signed and (on macOS) notarized"
    elif unsigned:
        verdict = "UNSIGNED"
    else:
        verdict = "unknown — no per-platform signing marker was found"

    with open(out_dir / "SHA256SUMS.txt", "w", encoding="utf-8") as fh:
        fh.write(f"gatepack v{version} — release artefact checksums\n\n")
        fh.write(f"Signing status: {verdict}\n")
        if unsigned:
            fh.write("\n" + _UNSIGNED_NOTICE + "\n")
        fh.write("\nVerify the download with:\n\n    sha256sum -c SHA256SUMS\n\n")
        for digest, name in checksums:
            fh.write(f"{digest}  {name}\n")

    with open(out_dir / "RELEASE-NOTES.md", "w", encoding="utf-8") as fh:
        fh.write(f"## gatepack v{version}\n\n")
        fh.write(
            "Compiles a truth table or finite-state machine into a bill of "
            "materials and a schematic netlist built from discrete 74AUP logic, "
            "formally verified on every build.\n\n"
        )
        fh.write(f"### Signing status\n\n{verdict}.\n\n")
        if unsigned:
            fh.write(
                "These installers are **unsigned** — no signing credentials are "
                "provisioned, and none are fabricated. macOS Gatekeeper and "
                "Windows SmartScreen will warn; that warning is the project "
                "telling you the truth rather than hiding it. See "
                "`docs/RELEASING.md` to supply credentials (the build is wired; "
                "that is the only remaining step).\n\n"
            )
        fh.write("### Verifying\n\n```\nsha256sum -c SHA256SUMS\n```\n\n")
        fh.write(
            "Each platform ships a CycloneDX SBOM (`sbom-*.json`) covering the "
            "npm tree and the bundled Python core.\n\n"
        )
        fh.write("### Known limitations\n\n")
        if unsigned:
            fh.write("- Installers are unsigned (see above).\n")
        fh.write("- KiCad import is unverified (deferred out of scope).\n")
        fh.write("- 16 of 22 library cells carry placeholder electrical data.\n")
        fh.write(
            "- Multi-gate `gates_per_pkg` values are unverified — a wrong one "
            "yields a netlist that physically cannot be built.\n\n"
        )
        fh.write("See `CHANGELOG.md` and `docs/RELEASING.md` for the full picture.\n")

    return {
        "SHA256SUMS": out_dir / "SHA256SUMS",
        "SHA256SUMS.txt": out_dir / "SHA256SUMS.txt",
        "RELEASE-NOTES.md": out_dir / "RELEASE-NOTES.md",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="assemble SHA256SUMS + release notes for the release"
    )
    parser.add_argument("source", help="directory of downloaded per-platform artefacts")
    parser.add_argument("out_dir", help="directory to write the assembled files into")
    parser.add_argument("--version", required=True, help="release version (no leading v)")
    args = parser.parse_args(argv)

    source = Path(args.source)
    if not source.is_dir():
        print(f"error: source directory not found: {source}", file=sys.stderr)
        return 1

    written = assemble(source, Path(args.out_dir), args.version)
    for name, path in written.items():
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
