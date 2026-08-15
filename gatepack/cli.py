"""gatepack command-line interface (§17).

Subcommands implemented in M1:

* ``gatepack lib check <csv> [--vcc V] [--allow-single-source]`` — validate the
  CSV and its citations, reporting what would be dropped and why.
* ``gatepack lib gen <csv> -o <lib> [--vcc V] [--allow-single-source]`` — emit a
  Liberty file.

Exit code is non-zero on validation failure (malformed data or a missing
``<name>.refs.md`` citation) so CI can gate on it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from gatepack import __version__, parts as parts_mod
from gatepack import refs as refs_mod
from gatepack.liberty.generator import generate, sanitize_library_name
from gatepack.liberty.validate import LibertyError
from gatepack.parts import DropReason, Exclusion, load_parts


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gatepack",
        description="compile truth tables and FSMs into discrete-logic BOMs",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    lib = sub.add_parser("lib", help="cell-library tools")
    lib_sub = lib.add_subparsers(dest="lib_command", required=True)

    check = lib_sub.add_parser(
        "check", help="validate a parts.csv and its datasheet citations"
    )
    check.add_argument("csv", help="path to parts.csv")
    check.add_argument(
        "--vcc",
        type=float,
        default=parts_mod.DEFAULT_VCC,
        help="project supply voltage (default: %(default)s V)",
    )
    check.add_argument(
        "--allow-single-source",
        action="store_true",
        help="do not exclude single-sourced cells",
    )

    gen = lib_sub.add_parser(
        "gen", help="emit a Liberty file from a parts.csv"
    )
    gen.add_argument("csv", help="path to parts.csv")
    gen.add_argument("-o", "--output", required=True, help="output .lib path")
    gen.add_argument(
        "--vcc",
        type=float,
        default=parts_mod.DEFAULT_VCC,
        help="project supply voltage (default: %(default)s V)",
    )
    gen.add_argument(
        "--allow-single-source",
        action="store_true",
        help="include single-sourced cells",
    )
    gen.add_argument(
        "--name",
        help="library name (default: derived from the CSV filename)",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "lib":
        if args.lib_command == "check":
            return _cmd_lib_check(args)
        if args.lib_command == "gen":
            return _cmd_lib_gen(args)
    parser.error(f"unknown command {args.command!r}")
    return 2


def _cmd_lib_check(args: argparse.Namespace) -> int:
    csv_path = Path(args.csv)
    try:
        parts = load_parts(csv_path)
    except parts_mod.PartError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    _, excluded = parts_mod.select_for_liberty(
        parts, project_vcc=args.vcc, allow_single_source=args.allow_single_source
    )
    missing, refs_path = refs_mod.check_citations(parts, csv_path)

    print(f"loaded {len(parts)} cells from {csv_path}")
    _print_exclusions(excluded)

    if not refs_path.exists():
        print(f"error: refs file not found: {refs_path}", file=sys.stderr)
        return 1
    if missing:
        print(
            f"error: {len(missing)} cell(s) missing a {refs_path.name} citation:",
            file=sys.stderr,
        )
        for cell in missing:
            print(f"  - {cell}", file=sys.stderr)
        return 1

    print(f"citations: all {len(parts)} cells have a {refs_path.name} entry")

    citations = refs_mod.parse_refs(refs_path)
    unverified = [
        cell
        for cell, status in citations.items()
        if "unverified" in status.lower() or "placeholder" in status.lower()
    ]
    if unverified:
        print(
            f"warning: {len(unverified)} cell(s) carry unverified/placeholder "
            "electrical data",
            file=sys.stderr,
        )
    return 0


def _cmd_lib_gen(args: argparse.Namespace) -> int:
    csv_path = Path(args.csv)
    try:
        parts = load_parts(csv_path)
    except parts_mod.PartError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    name = args.name or sanitize_library_name(csv_path.stem)
    try:
        result = generate(
            parts,
            library_name=name,
            project_vcc=args.vcc,
            allow_single_source=args.allow_single_source,
        )
    except (LibertyError, parts_mod.PartError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    _print_exclusions(result.excluded)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(result.text)
    print(f"wrote {out}: library {name!r}, {len(result.cells)} cells")
    return 0


def _print_exclusions(excluded: list[Exclusion]) -> None:
    if not excluded:
        return
    print(f"dropped {len(excluded)} cell(s):")
    for exc in excluded:
        print(f"  - {exc}")
    counts = {reason: sum(1 for e in excluded if e.reason == reason)
              for reason in DropReason}
    summary = ", ".join(
        f"{reason.value}: {counts[reason]}" for reason in DropReason if counts[reason]
    )
    if summary:
        print(f"  summary: {summary}")


if __name__ == "__main__":
    sys.exit(main())
