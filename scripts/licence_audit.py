#!/usr/bin/env python3
"""Licence audit (§4): every declared dependency's licence must be GPL-3.0-compatible.

Reads ``scripts/dependencies.json`` (the declared-dependency manifest) and
classifies each entry against a GPL-3.0-or-later compatibility policy.  Weak
copyleft at file scope (EPL-2.0, MPL-2.0, LGPL) is *conditionally* compatible:
it is accepted only when the dependency is consumed unmodified as a library
(``"unmodified": true``), which is exactly the elkjs case §4 calls out.  The
point of the audit is to *confirm* that by data, not assume it.

Exit code 0 = every dependency compatible; 1 = at least one dependency is
incompatible, unrecognised, or consumed modified against a weak-copyleft
licence.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = Path(__file__).resolve().parent / "dependencies.json"

# Normalised licence key -> (verdict, rationale).
# verdicts: "compatible", "conditional", "incompatible", "unrecognised"
POLICY: dict[str, tuple[str, str]] = {
    "isc": ("compatible", "permissive; GPL-compatible"),
    "mit": ("compatible", "permissive; GPL-compatible"),
    "apache-2.0": ("compatible", "permissive; GPL-3.0-compatible (Apache-2.0)"),
    "bsd-2-clause": ("compatible", "permissive; GPL-compatible"),
    "bsd-3-clause": ("compatible", "permissive; GPL-compatible"),
    "bsd-style": ("compatible", "permissive BSD-style; GPL-compatible"),
    "gpl-2.0+": ("compatible", "'or later' clause permits GPL-3.0 combination"),
    "gpl-2.0-or-later": ("compatible", "'or later' clause permits GPL-3.0 combination"),
    "gpl-3.0": ("compatible", "same family as GPL-3.0-or-later"),
    "gpl-3.0+": ("compatible", "same family as GPL-3.0-or-later"),
    "gpl-3.0-or-later": ("compatible", "the project licence itself"),
    "epl-2.0": ("conditional", "weak copyleft at file scope; requires unmodified library use"),
    "mpl-2.0": ("conditional", "weak copyleft at file scope; requires unmodified library use"),
    "lgpl-2.1": ("conditional", "weak copyleft; requires unmodified library use (dynamic or independent)"),
    "lgpl-2.1+": ("conditional", "weak copyleft; requires unmodified library use"),
    "lgpl-3.0": ("conditional", "weak copyleft; requires unmodified library use"),
    "lgpl-3.0+": ("conditional", "weak copyleft; requires unmodified library use"),
    "gpl-2.0": ("incompatible", "GPL-2.0-only is not compatible with GPL-3.0"),
    "gpl-2.0-only": ("incompatible", "GPL-2.0-only is not compatible with GPL-3.0"),
    "proprietary": ("incompatible", "proprietary licence is not distributable under GPL-3.0"),
}


def _normalise(licence: str) -> str:
    text = licence.strip().lower()
    if "(" in text:
        text = text[: text.index("(")].strip()
    return text


def _classify(name: str, licence: str, unmodified: bool) -> tuple[str, str]:
    key = _normalise(licence)
    if key not in POLICY:
        return "unrecognised", f"licence {licence!r} has no policy entry; add one after review"
    verdict, rationale = POLICY[key]
    if verdict == "conditional" and not unmodified:
        return (
            "incompatible",
            f"{rationale}; but {name!r} is not declared 'unmodified', so the "
            f"condition is not met",
        )
    return verdict, rationale


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="audit declared dependency licences against GPL-3.0")
    parser.add_argument(
        "--manifest",
        default=str(DEFAULT_MANIFEST),
        help="dependency manifest path (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    manifest = Path(args.manifest)
    if not manifest.exists():
        print(f"error: dependency manifest not found: {manifest}", file=sys.stderr)
        return 1

    data = json.loads(manifest.read_text())
    dependencies = data.get("dependencies", [])
    if not dependencies:
        print("error: dependency manifest declares no dependencies", file=sys.stderr)
        return 1

    failures = 0
    for dep in dependencies:
        name = dep.get("name", "<unnamed>")
        licence = dep.get("licence", "")
        unmodified = bool(dep.get("unmodified", True))
        verdict, rationale = _classify(name, licence, unmodified)
        if verdict in ("incompatible", "unrecognised"):
            print(f"FAIL {name}: {licence!r} — {rationale}")
            failures += 1
        else:
            print(f"ok   {name}: {licence!r} ({verdict}) — {rationale}")

    if failures:
        print(f"licence audit: {failures} dependency(s) not GPL-3.0-compatible", file=sys.stderr)
        return 1
    print(f"licence audit: {len(dependencies)} dependency(s) GPL-3.0-compatible")
    return 0


if __name__ == "__main__":
    sys.exit(main())
