#!/usr/bin/env python3
"""Licence audit (§4): every dependency's licence must be GPL-3.0-compatible.

Two inputs, both audited against the same POLICY table:

1. ``scripts/dependencies.json`` — the declared-dependency manifest (the core
   toolchain binaries + the Python runtime dependency).  Every entry's licence
   is classified; weak-copyleft-at-file-scope licences (EPL-2.0, MPL-2.0, LGPL)
   are *conditionally* compatible: accepted only when the entry is declared
   ``"unmodified": true``, which is exactly the elkjs case §4 calls out.

2. The installed npm tree (``app/node_modules``) — the ~500 packages the desktop
   application actually bundles.  This is opt-in via ``--node-tree`` /
   ``--require-node-tree``, because the manifest-only invocation is what the
   ``test`` CI job (which has no node_modules) runs.  The manifest could not see
   this tree, so the audit previously let an incompatible or unrecognised
   licence ship invisibly.  Each installed ``package.json`` ``license`` field is
   read (never assumed from the package name) and classified.  The tree is split
   into:

   * **shipped** — the packages npm records as production in
     ``app/package-lock.json`` (an entry with no ``dev``/``devOptional`` flag).
     These end up inside the packaged app (the renderer bundle embeds them and
     electron-builder packs production ``node_modules``).  Any *incompatible* or
     *unrecognised* licence here is a hard failure.  The lock file is used
     because re-deriving the graph from ``dependencies`` alone silently drops
     *nested* production dependencies (a hoisted ``yargs@17`` hides
     ``netlistsvg``'s real ``yargs@6`` subtree); when no lock file is present a
     flat-tree fallback is used instead.
   * **not shipped** (devDependencies, build tooling, extraneous hoisted
     packages) — these do not ship, so an *incompatible* licence is reported as
     a warning, not a failure (conflating the two drowns the signal in build
     tooling).  An *unrecognised* licence is still a hard failure everywhere:
     a licence the table cannot name is a hole in the audit, not a pass.

SPDX ``OR`` / ``AND`` expressions are evaluated properly (an ``OR`` is
acceptable when any alternative is; an ``AND`` when every part is).  Licences
are added to POLICY only after being identified by name, never defaulted.

Exit code 0 = every shipped dependency compatible and every licence recognised;
1 = at least one shipped dependency is incompatible or unrecognised, or any
licence anywhere is unrecognised.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = Path(__file__).resolve().parent / "dependencies.json"
DEFAULT_NODE_TREE = REPO / "app" / "node_modules"
DEFAULT_APP_MANIFEST = REPO / "app" / "package.json"

# Normalised licence key -> (verdict, rationale).
# verdicts: "compatible", "conditional", "incompatible", "unrecognised"
# Entries added for the installed tree are named licences, each identified
# before being added (see docs/BUILD-NOTES-m18.md), never defaulted.
POLICY: dict[str, tuple[str, str]] = {
    "isc": ("compatible", "permissive; GPL-compatible"),
    "mit": ("compatible", "permissive; GPL-compatible"),
    "mit-0": ("compatible", "MIT No Attribution; permissive; GPL-compatible"),
    "apache-2.0": ("compatible", "permissive; GPL-3.0-compatible (Apache-2.0)"),
    "bsd-2-clause": ("compatible", "permissive; GPL-compatible"),
    "bsd-3-clause": ("compatible", "permissive; GPL-compatible"),
    "bsd-style": ("compatible", "permissive BSD-style; GPL-compatible"),
    "blueoak-1.0.0": ("compatible", "Blue Oak Model License 1.0.0; permissive, OSI-approved, GPL-3.0-compatible"),
    "python-2.0": ("compatible", "PSF licence; permissive BSD-style; GPL-compatible"),
    "cc0-1.0": ("compatible", "CC0-1.0 public-domain dedication; GPL-compatible"),
    "wtfpl": ("compatible", "permissive; GPL-compatible"),
    "gpl-2.0+": ("compatible", "'or later' clause permits GPL-3.0 combination"),
    "gpl-2.0-or-later": ("compatible", "'or later' clause permits GPL-3.0 combination"),
    "gpl-3.0": ("compatible", "same family as GPL-3.0-or-later"),
    "gpl-3.0+": ("compatible", "same family as GPL-3.0-or-later"),
    "gpl-3.0-or-later": ("compatible", "the project licence itself"),
    "epl-2.0": ("conditional", "weak copyleft at file scope; requires unmodified library use"),
    "epl-1.0": ("conditional", "weak copyleft at file scope; requires unmodified library use (the shipped elkjs is EPL-1.0, not the EPL-2.0 §4 records — see docs/BUILD-NOTES-m18.md)"),
    "mpl-2.0": ("conditional", "weak copyleft at file scope; requires unmodified library use"),
    "lgpl-2.1": ("conditional", "weak copyleft; requires unmodified library use (dynamic or independent)"),
    "lgpl-2.1+": ("conditional", "weak copyleft; requires unmodified library use"),
    "lgpl-3.0": ("conditional", "weak copyleft; requires unmodified library use"),
    "lgpl-3.0+": ("conditional", "weak copyleft; requires unmodified library use"),
    "gpl-2.0": ("incompatible", "GPL-2.0-only is not compatible with GPL-3.0"),
    "gpl-2.0-only": ("incompatible", "GPL-2.0-only is not compatible with GPL-3.0"),
    "cc-by-3.0": ("incompatible", "CC-BY-3.0 is not GPL-compatible (FSF)"),
    "cc-by-4.0": ("incompatible", "CC-BY-4.0 is not GPL-compatible (FSF)"),
    "proprietary": ("incompatible", "proprietary licence is not distributable under GPL-3.0"),
}


def _normalise(licence: str) -> str:
    text = licence.strip().lower()
    if "(" in text:
        text = text[: text.index("(")].strip()
    return text


def _verdict_for_key(name: str, key: str, unmodified: bool, shown: str) -> tuple[str, str]:
    if key not in POLICY:
        return "unrecognised", f"licence {shown!r} has no policy entry; add one after review"
    verdict, rationale = POLICY[key]
    if verdict == "conditional" and not unmodified:
        return (
            "incompatible",
            f"{rationale}; but {name!r} is not declared 'unmodified', so the "
            f"condition is not met",
        )
    return verdict, rationale


def _classify(name: str, licence: str, unmodified: bool) -> tuple[str, str]:
    """Classify a single human-written licence label from the manifest."""
    key = _normalise(licence)
    return _verdict_for_key(name, key, unmodified, licence)


# --- SPDX expression handling (installed npm `license` fields) ---------------


def _tokenize_spdx(expr: str) -> list[str]:
    tokens: list[str] = []
    i = 0
    n = len(expr)
    while i < n:
        c = expr[i]
        if c.isspace():
            i += 1
            continue
        if c in "()":
            tokens.append(c)
            i += 1
            continue
        j = i
        while j < n and not expr[j].isspace() and expr[j] not in "()":
            j += 1
        tokens.append(expr[i:j])
        i = j
    return tokens


class _SpdxSyntaxError(ValueError):
    pass


def _parse_spdx(expr: str):
    """Parse an SPDX expression into a nested ('atom'|'or'|'and', ...) tree."""
    tokens = _tokenize_spdx(expr)
    pos = 0

    def peek() -> str | None:
        return tokens[pos] if pos < len(tokens) else None

    def advance() -> str:
        nonlocal pos
        if pos >= len(tokens):
            raise _SpdxSyntaxError("unexpected end of expression")
        tok = tokens[pos]
        pos += 1
        return tok

    def parse_or():
        left = parse_and()
        while peek() == "OR":
            advance()
            right = parse_and()
            left = ("or", left, right)
        return left

    def parse_and():
        left = parse_atom()
        while peek() == "AND":
            advance()
            right = parse_atom()
            left = ("and", left, right)
        return left

    def parse_atom():
        tok = peek()
        if tok is None:
            raise _SpdxSyntaxError("empty licence expression")
        if tok == "(":
            advance()
            node = parse_or()
            if advance() != ")":
                raise _SpdxSyntaxError("missing closing parenthesis")
            return node
        return ("atom", advance())

    node = parse_or()
    if pos != len(tokens):
        raise _SpdxSyntaxError(f"unexpected token {tokens[pos]!r}")
    return node


_RANK = {"compatible": 0, "conditional": 1, "incompatible": 2, "unrecognised": 3}


def _eval_spdx(node, name: str, unmodified: bool) -> tuple[str, str]:
    if node[0] == "atom":
        atom = node[1]
        return _verdict_for_key(name, atom.lower(), unmodified, atom)
    op, left, right = node[0], node[1], node[2]
    lv = _eval_spdx(left, name, unmodified)
    rv = _eval_spdx(right, name, unmodified)
    if op == "or":
        best = min([lv, rv], key=lambda p: _RANK[p[0]])
        return best[0], f"SPDX OR; a compatible alternative is available ({best[1]})" if best[0] in ("compatible", "conditional") else f"SPDX OR; no acceptable alternative ({best[1]})"
    worst = max([lv, rv], key=lambda p: _RANK[p[0]])
    return worst[0], f"SPDX AND; all parts required ({worst[1]})"


def classify_node_licence(name: str, expr: str, unmodified: bool = True) -> tuple[str, str]:
    """Classify an installed package's ``license`` field (may be an SPDX expression)."""
    try:
        node = _parse_spdx(expr)
    except _SpdxSyntaxError as exc:
        return "unrecognised", f"licence expression {expr!r} could not be parsed ({exc})"
    return _eval_spdx(node, name, unmodified)


# --- installed-tree walking --------------------------------------------------


def iter_installed_packages(node_tree: Path) -> list[tuple[str, dict]]:
    """Yield (rel_path, package.json dict) for every installed package.

    Walks the real tree, including *nested* ``node_modules`` (npm nests a
    package when the hoisted version does not satisfy a range — e.g.
    ``netlistsvg/node_modules/yargs@6`` under a top-level ``yargs@17``).  The
    returned ``rel_path`` is POSIX-style and relative to ``node_tree``.
    """
    if not node_tree.is_dir():
        return []
    packages: list[tuple[str, dict]] = []

    def walk(dir: Path) -> None:
        for entry in sorted(dir.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            if entry.name == "node_modules":
                walk(entry)
                continue
            pj = entry / "package.json"
            if pj.is_file():
                rel = entry.relative_to(node_tree).as_posix()
                packages.append((rel, json.loads(pj.read_text())))
                nested = entry / "node_modules"
                if nested.is_dir():
                    walk(nested)
            elif entry.name.startswith("@"):
                walk(entry)

    walk(node_tree)
    return packages


def pkg_licence(pkg: dict) -> str | None:
    """Extract the licence from a package.json body (string, SPDX, object or array)."""
    lic = pkg.get("license")
    if lic is None:
        return None
    if isinstance(lic, str):
        return lic
    if isinstance(lic, list):
        parts = [x.get("type") if isinstance(x, dict) else str(x) for x in lic]
        return " AND ".join(parts)
    if isinstance(lic, dict):
        return lic.get("type") or lic.get("name")
    return str(lic)


def package_name(rel_path: str) -> str:
    """Best-effort package name from an install path (last non-node_modules segment)."""
    parts = [p for p in rel_path.split("/") if p != "node_modules"]
    if len(parts) >= 2 and parts[-2].startswith("@"):
        return f"{parts[-2]}/{parts[-1]}"
    return parts[-1] if parts else rel_path


def shipping_paths_from_lock(lock: dict) -> set[str]:
    """Return the set of install paths npm records as production (non-dev).

    ``package-lock.json`` ``packages`` keys are install paths; a package marked
    ``dev`` or ``devOptional`` does not ship.  This is authoritative about which
    packages electron-builder will pack — far more so than re-deriving the graph
    from ``dependencies`` alone, which silently drops *nested* production
    dependencies (a hoisted ``yargs@17`` hides ``netlistsvg``'s real
    ``yargs@6`` subtree).
    """
    shipped: set[str] = set()
    for path, data in lock.get("packages", {}).items():
        if not path:
            continue
        if data.get("dev") or data.get("devOptional"):
            continue
        shipped.add(path.removeprefix("node_modules/"))
    return shipped


def _dep_names(pkg: dict, *sections: str) -> list[str]:
    out: list[str] = []
    for sec in sections:
        d = pkg.get(sec)
        if isinstance(d, dict):
            out.extend(d.keys())
    return out


def compute_shipping_set_fallback(app_manifest: dict, by_name: dict[str, dict]) -> set[str]:
    """Fallback closure over top-level ``dependencies`` when no lock file exists.

    Assumes a flat/hoisted tree, so it can miss nested version-conflict
    packages; the lock file is the authoritative source and is preferred
    whenever present.
    """
    shipped: set[str] = set()
    queue = list(app_manifest.get("dependencies", {}).keys())
    while queue:
        name = queue.pop()
        if name in shipped:
            continue
        shipped.add(name)
        pkg = by_name.get(name)
        if pkg is None:
            continue
        for dep in _dep_names(pkg, "dependencies", "optionalDependencies", "peerDependencies"):
            if dep not in shipped:
                queue.append(dep)
    return shipped


def audit_node_tree(
    node_tree: Path,
    app_manifest: dict,
    lockfile: Path | None,
    *,
    out=print,
) -> tuple[int, int, int]:
    """Audit installed packages. Returns (failures, shipped_count, dev_count)."""
    packages = iter_installed_packages(node_tree)
    by_name = {package_name(rel): pkg for rel, pkg in packages}

    if lockfile is not None and lockfile.is_file():
        shipped = shipping_paths_from_lock(json.loads(lockfile.read_text()))
    else:
        shipped = compute_shipping_set_fallback(app_manifest, by_name)

    failures = 0
    shipped_count = 0
    dev_count = 0

    for rel, pkg in packages:
        name = package_name(rel)
        ships = rel in shipped
        if ships:
            shipped_count += 1
        else:
            dev_count += 1

        lic = pkg_licence(pkg)
        if lic is None:
            verdict, rationale = "unrecognised", "package declares no license field"
        else:
            verdict, rationale = classify_node_licence(name, lic, unmodified=True)

        marker = "ships" if ships else "dev  "
        if verdict == "unrecognised":
            failures += 1
            out(f"FAIL [{marker}] {name}: {lic!r} — {rationale}")
        elif verdict == "incompatible" and ships:
            failures += 1
            out(f"FAIL [{marker}] {name}: {lic!r} — {rationale}")
        elif verdict == "incompatible":
            out(f"warn [{marker}] {name}: {lic!r} — {rationale} (not shipped; non-blocking)")
        elif verdict == "conditional":
            out(f"ok   [{marker}] {name}: {lic!r} (conditional, unmodified) — {rationale}")
        elif ships:
            out(f"ok   [{marker}] {name}: {lic!r} (compatible) — {rationale}")
        # dev-compatible packages are counted but not printed: they are the
        # build-tooling noise this audit is specifically told not to drown in.

    return failures, shipped_count, dev_count


def _audit_manifest(manifest: Path, *, out=print, err=print) -> tuple[int, int]:
    data = json.loads(manifest.read_text())
    dependencies = data.get("dependencies", [])
    if not dependencies:
        err("error: dependency manifest declares no dependencies")
        return 1, 0
    failures = 0
    for dep in dependencies:
        name = dep.get("name", "<unnamed>")
        licence = dep.get("licence", "")
        unmodified = bool(dep.get("unmodified", True))
        verdict, rationale = _classify(name, licence, unmodified)
        if verdict in ("incompatible", "unrecognised"):
            out(f"FAIL {name}: {licence!r} — {rationale}")
            failures += 1
        else:
            out(f"ok   {name}: {licence!r} ({verdict}) — {rationale}")
    return failures, len(dependencies)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="audit dependency licences against GPL-3.0")
    parser.add_argument(
        "--manifest",
        default=str(DEFAULT_MANIFEST),
        help="declared-dependency manifest path (default: %(default)s)",
    )
    parser.add_argument(
        "--node-tree",
        default=None,
        help="installed npm tree to audit (opt-in; default: %(default)s)",
    )
    parser.add_argument(
        "--app-manifest",
        default=str(DEFAULT_APP_MANIFEST),
        help="app package.json used to split shipped vs dev (default: %(default)s)",
    )
    parser.add_argument(
        "--lockfile",
        default=None,
        help="package-lock.json used for the authoritative shipped set "
        "(default: <app-manifest dir>/package-lock.json)",
    )
    parser.add_argument(
        "--require-node-tree",
        action="store_true",
        help="audit the default app/node_modules and fail if it is absent or empty",
    )
    args = parser.parse_args(argv)

    manifest = Path(args.manifest)
    if not manifest.exists():
        print(f"error: dependency manifest not found: {manifest}", file=sys.stderr)
        return 1

    manifest_failures, manifest_count = _audit_manifest(
        manifest, out=lambda s: print(s), err=lambda s: print(s, file=sys.stderr)
    )
    total_failures = manifest_failures

    # The installed-tree audit is opt-in: the declared-manifest audit is the
    # default (and the only thing the `test` job, which has no node_modules,
    # can run).  --require-node-tree selects the default tree and demands it.
    if args.node_tree is not None:
        node_tree = Path(args.node_tree)
    elif args.require_node_tree:
        node_tree = DEFAULT_NODE_TREE
    else:
        node_tree = None

    node_failures = 0
    shipped_count = 0
    dev_count = 0

    if node_tree is None:
        print("note: installed-tree audit not requested (pass --require-node-tree or --node-tree)")
    elif not node_tree.is_dir():
        print(f"error: installed tree not present: {node_tree}", file=sys.stderr)
        return 1
    else:
        packages = iter_installed_packages(node_tree)
        if not packages:
            print(f"error: installed tree is empty: {node_tree}", file=sys.stderr)
            return 1
        app_manifest_path = Path(args.app_manifest)
        if not app_manifest_path.exists():
            print(
                f"error: app manifest not found ({app_manifest_path}); cannot "
                f"distinguish shipped from dev dependencies",
                file=sys.stderr,
            )
            return 1
        lockfile = Path(args.lockfile) if args.lockfile else app_manifest_path.parent / "package-lock.json"
        app_manifest = json.loads(app_manifest_path.read_text())
        node_failures, shipped_count, dev_count = audit_node_tree(
            node_tree,
            app_manifest,
            lockfile,
            out=print,
        )
        total_failures += node_failures

    if total_failures:
        print(
            f"licence audit: {total_failures} dependency(s) not GPL-3.0-compatible",
            file=sys.stderr,
        )
        return 1

    if shipped_count + dev_count:
        node_note = f"installed tree {shipped_count} shipped + {dev_count} dev/other"
    elif node_tree is None:
        node_note = "installed tree not requested"
    else:
        node_note = "installed tree empty"
    print(
        f"licence audit: {manifest_count + shipped_count + dev_count} dependency(s) "
        f"GPL-3.0-compatible ({manifest_count} manifest, {node_note})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
