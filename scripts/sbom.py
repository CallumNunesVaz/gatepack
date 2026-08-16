#!/usr/bin/env python3
"""Generate a CycloneDX SBOM for the gatepack release (both dependency trees).

The release ships two dependency trees that are audited separately and must not
drift: the npm tree (``app/node_modules``, audited as "shipped" vs "dev" against
``package-lock.json`` and the ``electron-builder.yml`` excludes) and the bundled
Python core (``app/resources/bin/gatepack``, a PyInstaller onefile).  This
script reuses ``scripts/licence_audit.py``'s enumeration *by importing it*, so
the SBOM can never disagree with the audit about what is in each tree — the two
read the same functions over the same inputs.

The output is a CycloneDX 1.4 JSON document, deterministic by construction:
components are sorted by name and no timestamp is written, so two runs over the
same inputs are byte-identical (matching §C6's "no timestamps in a payload").

``--require-node-tree`` and ``--require-bundle`` turn a missing input into a
hard failure rather than an empty section, for the same reason the audit's
flags do: an SBOM that enumerated nothing is indistinguishable from one that
was never generated.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LICENCE_AUDIT = Path(__file__).resolve().parent / "licence_audit.py"
DEFAULT_NODE_TREE = REPO / "app" / "node_modules"
DEFAULT_APP_MANIFEST = REPO / "app" / "package.json"
DEFAULT_BUNDLE = REPO / "app" / "resources" / "bin" / "gatepack"
DEFAULT_BUNDLE_EXE = REPO / "app" / "resources" / "bin" / "gatepack.exe"


def _load_audit():
    """Load ``scripts/licence_audit.py`` as a module (it has no package)."""
    spec = importlib.util.spec_from_file_location("licence_audit_sbom", LICENCE_AUDIT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _node_components(audit, node_tree: Path, app_manifest: Path, lockfile: Path | None, pack_config: Path) -> list[dict]:
    """Enumerate the installed npm tree with the audit's own shipped/dev split."""
    packages = audit.iter_installed_packages(node_tree)
    if not packages:
        return []

    if lockfile is not None and lockfile.is_file():
        shipped = audit.shipping_paths_from_lock(json.loads(lockfile.read_text()))
    else:
        by_name = {audit.package_name(rel): pkg for rel, pkg in packages}
        shipped = audit.compute_shipping_set_fallback(json.loads(app_manifest.read_text()), by_name)

    excludes = audit.electron_builder_excludes(pack_config)
    components: list[dict] = []
    for rel, pkg in packages:
        name = audit.package_name(rel)
        ships = (rel in shipped) and not audit.package_is_excluded(rel, excludes)
        lic = audit.pkg_licence(pkg)
        version = pkg.get("version")
        component: dict = {
            "type": "library",
            "name": name,
            "version": version,
            "licenses": [{"expression": lic}] if lic else [],
            "properties": [{"name": "gatepack:shipped", "value": "true" if ships else "false"}],
        }
        if version:
            component["purl"] = f"pkg:npm/{name}@{version}"
        components.append(component)
    return components


def _bundle_components(audit, bundle: Path) -> list[dict]:
    """Enumerate the PyInstaller core with the audit's own classification.

    Each enumerated module/file is mapped to a component through the audit's
    ``_classify_bundle_module`` / ``_classify_bundle_entry``, and the component
    licence comes from the audit's ``BUNDLE_COMPONENTS`` table — never from a
    second source that could disagree with it.
    """
    modules, entries = audit._enumerate_bundle(bundle)
    stdlib = frozenset(sys.stdlib_module_names)

    per_component: dict[str, list[str]] = {}
    for mod in modules:
        component = audit._classify_bundle_module(mod, stdlib)
        if component is not None:
            per_component.setdefault(component, []).append(mod)
    for typecode, name in entries:
        if name == "PYZ.pyz":
            continue
        component = audit._classify_bundle_entry(name, typecode, stdlib)
        if component is not None:
            per_component.setdefault(component, []).append(name)

    components: list[dict] = []
    for component in sorted(per_component):
        files = per_component[component]
        entry = audit.BUNDLE_COMPONENTS.get(component)
        if entry is None:
            licence, rationale = None, "unrecognised component (the licence audit will fail on it)"
        else:
            licence, rationale = entry
        comp: dict = {
            "type": "library",
            "name": component,
            "version": None,
            "licenses": [{"license": {"name": licence}}] if licence else [],
            "properties": [
                {"name": "gatepack:component-files", "value": str(len(files))},
                {"name": "gatepack:licence-rationale", "value": rationale},
            ],
        }
        components.append(comp)
    return components


def generate_sbom(
    *,
    node_tree: Path | None,
    app_manifest: Path,
    lockfile: Path | None,
    pack_config: Path,
    bundle: Path | None,
    name: str,
    version: str,
) -> dict:
    audit = _load_audit()

    components: list[dict] = []
    if node_tree is not None:
        components.extend(_node_components(audit, node_tree, app_manifest, lockfile, pack_config))
    if bundle is not None:
        components.extend(_bundle_components(audit, bundle))

    components.sort(key=lambda c: c["name"])

    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.4",
        "version": 1,
        "metadata": {
            "tools": [
                {
                    "vendor": "gatepack",
                    "name": "gatepack-sbom",
                    "version": version,
                }
            ],
            "component": {
                "type": "application",
                "name": name,
                "version": version,
                "licenses": [{"expression": "GPL-3.0-or-later"}],
            },
        },
        "components": components,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="generate a CycloneDX SBOM for the release")
    parser.add_argument("--node-tree", default=None, help="installed npm tree (opt-in)")
    parser.add_argument("--require-node-tree", action="store_true", help="use the default npm tree and fail if absent/empty")
    parser.add_argument("--app-manifest", default=str(DEFAULT_APP_MANIFEST))
    parser.add_argument("--lockfile", default=None, help="package-lock.json (default: <app-manifest dir>/package-lock.json)")
    parser.add_argument("--pack-config", default=str(REPO / "app" / "electron-builder.yml"))
    parser.add_argument("--bundle", default=None, help="PyInstaller core bundle (opt-in)")
    parser.add_argument("--require-bundle", action="store_true", help="use the default bundle and fail if absent")
    parser.add_argument("--name", default="gatepack", help="application name (default: %(default)s)")
    parser.add_argument("--version", default=None, help="version (default: read from app/package.json)")
    parser.add_argument("-o", "--output", default=None, help="write to this file (default: stdout)")
    args = parser.parse_args(argv)

    node_tree: Path | None
    if args.node_tree is not None:
        node_tree = Path(args.node_tree)
    elif args.require_node_tree:
        node_tree = DEFAULT_NODE_TREE
    else:
        node_tree = None

    if node_tree is not None:
        audit = _load_audit()
        if not node_tree.is_dir() or not audit.iter_installed_packages(node_tree):
            print(f"error: installed tree not present or empty: {node_tree}", file=sys.stderr)
            return 1

    bundle: Path | None
    if args.bundle is not None:
        bundle = Path(args.bundle)
    elif args.require_bundle:
        bundle = DEFAULT_BUNDLE if DEFAULT_BUNDLE.is_file() else DEFAULT_BUNDLE_EXE
    else:
        bundle = None

    if bundle is not None and not bundle.is_file():
        print(f"error: bundled core not present: {bundle}", file=sys.stderr)
        return 1

    app_manifest = Path(args.app_manifest)
    if not app_manifest.is_file():
        print(f"error: app manifest not found: {app_manifest}", file=sys.stderr)
        return 1

    version = args.version or json.loads(app_manifest.read_text()).get("version", "0.0.0")

    lockfile = Path(args.lockfile) if args.lockfile else app_manifest.parent / "package-lock.json"

    try:
        sbom = generate_sbom(
            node_tree=node_tree,
            app_manifest=app_manifest,
            lockfile=lockfile,
            pack_config=Path(args.pack_config),
            bundle=bundle,
            name=args.name,
            version=version,
        )
    except Exception as exc:  # noqa: BLE001 — surface any enumeration failure loudly
        print(f"error: SBOM generation failed: {exc}", file=sys.stderr)
        return 1

    text = json.dumps(sbom, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(text)
        print(f"wrote {args.output} ({len(sbom['components'])} component(s))")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
