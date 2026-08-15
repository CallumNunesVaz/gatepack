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
from gatepack.estimate import VccIncompatibleError, one_hot_init_cost, run_estimate
from gatepack.frontend import AsyncRefused, CompileError, compile_design_file
from gatepack.liberty.generator import generate, sanitize_library_name
from gatepack.liberty.validate import LibertyError
from gatepack.parts import DropReason, Exclusion, load_parts
from gatepack.verify.base import CheckStatus
from gatepack.verify.run import run_verify

# Exit-code contract (§C6, pinned in tests/contract):
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_ASYNC_REFUSED = 3


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

    compile_p = sub.add_parser(
        "compile", help="C1 front-end: design.yaml -> behavioural Verilog + properties"
    )
    compile_p.add_argument("design", help="path to design.yaml")
    compile_p.add_argument(
        "-o", "--output", default="build", help="output directory (default: %(default)s)"
    )

    estimate = sub.add_parser(
        "estimate", help="run the front-end + synthesis and emit the §6 viability verdict"
    )
    estimate.add_argument("design", help="path to design.yaml")
    estimate.add_argument("--library", required=True, help="path to parts.csv")
    estimate.add_argument(
        "--build", default="build", help="build directory (default: %(default)s)"
    )

    verify = sub.add_parser(
        "verify", help="C4: equivalence + exhaustive simulation + mutation (§12)"
    )
    verify.add_argument("design", help="path to design.yaml")
    verify.add_argument("--library", required=True, help="path to parts.csv")
    verify.add_argument(
        "--build", default="build", help="build directory (default: %(default)s)"
    )

    build = sub.add_parser(
        "build", help="C5+C6+C7+C8: pack and emit BOM, KiCad netlist, report"
    )
    build.add_argument("design", help="path to design.yaml")
    build.add_argument("--library", required=True, help="path to parts.csv")
    build.add_argument("--out", default="out", help="output directory (default: %(default)s)")
    build.add_argument(
        "--mapped", help="path to a mapped.json; skips Yosys (default: run Yosys if present)"
    )
    build.add_argument(
        "--spare-weight",
        type=float,
        default=None,
        help="§9.7 spare leakage weight (default: %(default)s)",
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
    if args.command == "compile":
        return _cmd_compile(args)
    if args.command == "estimate":
        return _cmd_estimate(args)
    if args.command == "verify":
        return _cmd_verify(args)
    if args.command == "build":
        return _cmd_build(args)
    parser.error(f"unknown command {args.command!r}")
    return EXIT_USAGE


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


def _cmd_compile(args: argparse.Namespace) -> int:
    try:
        result = compile_design_file(args.design)
    except AsyncRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return EXIT_ASYNC_REFUSED
    except (CompileError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    generated = out / "generated.v"
    properties = out / "properties.sv"
    generated.write_text(result.verilog)
    properties.write_text(result.properties)

    compiled = result.compiled
    print(
        f"compiled {compiled.design.name!r}: {compiled.design.timing_model}, "
        f"{compiled.encoding} encoding, {len(compiled.state_order)} state(s)"
    )
    print(f"wrote {generated}")
    print(f"wrote {properties}")
    if compiled.johnson_suggestion:
        print(f"note: {compiled.johnson_suggestion}", file=sys.stderr)
    return EXIT_OK


def _cmd_estimate(args: argparse.Namespace) -> int:
    try:
        result = run_estimate(args.design, args.library, args.build)
    except AsyncRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return EXIT_ASYNC_REFUSED
    except (CompileError, parts_mod.PartError, LibertyError, VccIncompatibleError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    verdict = result.verdict
    design = result.compiled.design
    print(
        f"design: {design.name} ({design.timing_model}, {design.encoding}, "
        f"vcc {design.constraints.vcc:g} V)"
    )
    print(f"verdict: {verdict.overall.upper()}")
    for name, metric in verdict.metrics.items():
        value = "unknown" if metric.value is None else f"{metric.value:g}"
        print(f"  {name + ':':22} {value:>10}  ({metric.status})")
    print(f"message: {verdict.message}")
    print(f"manifest: {result.paths['manifest']}")
    one_hot_cost = one_hot_init_cost(result.compiled)
    if one_hot_cost is not None:
        print(
            f"one-hot initial state: {one_hot_cost.mechanism}; "
            f"NOR fan-in {one_hot_cost.nor_fanin} "
            f"(<= {one_hot_cost.nor_gate_upper_bound} NOR gates) + 1 OR input "
            f"counted in the gate budget"
        )
    if result.compiled.johnson_suggestion:
        print(f"note: {result.compiled.johnson_suggestion}", file=sys.stderr)
    return EXIT_OK


def _cmd_verify(args: argparse.Namespace) -> int:
    try:
        result = run_verify(args.design, args.library, args.build)
    except AsyncRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return EXIT_ASYNC_REFUSED
    except (CompileError, parts_mod.PartError, LibertyError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    report = result.report
    print(f"verification: {report.checks and result.manifest['verification']['overall']}")
    for check in report.checks:
        suffix = f" (bound {check.bound})" if check.bound is not None else ""
        print(f"  {check.name + ':':26} {check.status.value}{suffix}")
        if check.detail:
            print(f"      {check.detail}")
    if report.mutations:
        for mutation in report.mutations:
            state = "detected" if mutation.detected else "NOT DETECTED"
            print(f"  mutation {mutation.mutation + ':':17} {state}")
    print(f"manifest: {result.paths['manifest']}")
    if report.ok:
        return EXIT_OK
    if report.has_failure:
        return EXIT_ERROR
    return EXIT_ERROR  # not-run is not a pass (§14: never claim an unrun proof)
def _cmd_build(args: argparse.Namespace) -> int:
    from gatepack.build import run_build

    try:
        result, paths = run_build(
            args.design,
            args.library,
            out_dir=args.out,
            mapped_json=args.mapped,
            spare_leakage_weight=args.spare_weight,
        )
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except (
        AsyncRefused,
        CompileError,
        parts_mod.PartError,
        LibertyError,
        VccIncompatibleError,
        OSError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    s = result.packed_stats
    print(f"packed: {s.package_count} package(s), {s.spare_count} spare gate(s), "
          f"pack_cost {s.pack_cost:g}")
    for name, path in sorted(paths.items()):
        print(f"wrote {path}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
