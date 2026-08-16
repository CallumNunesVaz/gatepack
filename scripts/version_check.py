#!/usr/bin/env python3
"""Version consistency check: ``pyproject.toml`` and ``app/package.json`` must agree.

The Python core and the desktop application are released together as v0.1.0, so
their versions are the same number in two files.  Nothing links the two, and a
previous milestone recorded version skew that "had to be pinned by measurement"
(docs/M6-FINDINGS.md §5).  This check fails when the two drift, so a release
cannot be cut from a tree whose halves disagree.

Exit 0 = versions match; 1 = they drift, or a file cannot be read.  The two
file paths are overridable so a test can assert the failure case without
rearranging the repo.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_PYPROJECT = REPO / "pyproject.toml"
DEFAULT_PACKAGE_JSON = REPO / "app" / "package.json"


def pyproject_version(text: str) -> str | None:
    """Return the ``[project] version = "..."`` value, or None when absent."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("version"):
            m = re.search(r'version\s*=\s*"([^"]+)"', stripped)
            if m:
                return m.group(1)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="check pyproject.toml and app/package.json versions agree")
    parser.add_argument("--pyproject", default=str(DEFAULT_PYPROJECT))
    parser.add_argument("--package-json", default=str(DEFAULT_PACKAGE_JSON))
    parser.add_argument(
        "--tag",
        default=None,
        help="release tag (e.g. v0.1.0); assert it matches the agreed version "
        "so a tag-triggered release cannot be cut from a tree whose version "
        "disagrees with the tag",
    )
    args = parser.parse_args(argv)

    pyproject = Path(args.pyproject)
    package_json = Path(args.package_json)

    if not pyproject.exists():
        print(f"error: {pyproject} not found", file=sys.stderr)
        return 1
    if not package_json.exists():
        print(f"error: {package_json} not found", file=sys.stderr)
        return 1

    py = pyproject_version(pyproject.read_text())
    if py is None:
        print("error: no version found in pyproject.toml", file=sys.stderr)
        return 1

    pkg = json.loads(package_json.read_text())
    js = pkg.get("version")
    if not js:
        print("error: no version found in app/package.json", file=sys.stderr)
        return 1

    if py != js:
        print(
            f"version drift: pyproject.toml={py!r} != app/package.json={js!r}",
            file=sys.stderr,
        )
        return 1

    if args.tag:
        tag_version = args.tag.lstrip("vV")
        if tag_version != py:
            print(
                f"tag/version mismatch: tag={args.tag!r} != version={py!r}",
                file=sys.stderr,
            )
            return 1

    print(f"versions agree: {py} (pyproject.toml == app/package.json)")
    if args.tag:
        print(f"tag agrees: {args.tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
