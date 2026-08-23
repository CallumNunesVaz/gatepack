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
import json
import sys
from pathlib import Path

from gatepack import __version__, parts as parts_mod
from gatepack import api
from gatepack import pinmap as pinmap_mod
from gatepack import refs as refs_mod
from gatepack.diagnostic import (
    GP_ASYNC_REFUSED,
    GP_COMPILE,
    GP_INTERNAL,
    GP_IO,
    GP_LIBRARY,
    GP_SYNTH_UNAVAILABLE,
    GP_VCC,
    Diagnostic,
    error,
)
from gatepack.estimate import VccIncompatibleError, one_hot_init_cost, run_estimate
from gatepack.frontend import AsyncRefused, CompileError, compile_design_file
from gatepack.liberty.generator import generate, sanitize_library_name
from gatepack.liberty.validate import LibertyError
from gatepack.parts import DropReason, Exclusion, load_parts
from gatepack.project import (
    ProjectError,
    bundle,
    explode_to_dir,
    library_divergence,
    load_project,
)
from gatepack.doctor import run_doctor
from gatepack.verify.base import CheckStatus
from gatepack.verify.run import run_verify

# Exit-code contract (§C6, pinned in tests/contract):
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_ASYNC_REFUSED = 3


def _json_ok(command: str, payload: dict) -> None:
    """Emit the ``ok: true`` envelope — one JSON object to stdout, nothing else."""
    sys.stdout.write(api.dump(api.envelope_ok(command, payload)))


def _json_err(command: str, diag: Diagnostic) -> None:
    """Emit the ``ok: false`` envelope; the human message still goes to stderr."""
    sys.stdout.write(api.dump(api.envelope_err(command, diag)))
    print(f"{diag.severity}: {diag.message}", file=sys.stderr)


def _command_error(exc: BaseException) -> Diagnostic:
    """Map a caught exception to a stable machine-readable diagnostic."""
    if isinstance(exc, AsyncRefused):
        return error(GP_ASYNC_REFUSED, str(exc))
    if isinstance(exc, CompileError):
        return error(GP_COMPILE, str(exc))
    if isinstance(exc, VccIncompatibleError):
        return error(GP_VCC, str(exc))
    if isinstance(exc, (parts_mod.PartError, LibertyError)):
        return error(GP_LIBRARY, str(exc))
    if isinstance(exc, OSError):
        return error(GP_IO, str(exc))
    if isinstance(exc, RuntimeError):
        return error(GP_SYNTH_UNAVAILABLE, str(exc))
    return error(GP_INTERNAL, str(exc))


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
    check.add_argument(
        "--json", action="store_true", help="emit one machine-readable JSON object to stdout"
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
    compile_p.add_argument("design", help="path to design.yaml or .gpk")
    compile_p.add_argument(
        "-o", "--output", default="build", help="output directory (default: %(default)s)"
    )
    compile_p.add_argument(
        "--json", action="store_true", help="emit one machine-readable JSON object to stdout"
    )

    estimate = sub.add_parser(
        "estimate", help="run the front-end + synthesis and emit the §6 viability verdict"
    )
    estimate.add_argument("design", help="path to design.yaml or .gpk")
    estimate.add_argument("--library", required=True, help="path to parts.csv")
    estimate.add_argument(
        "--build", default="build", help="build directory (default: %(default)s)"
    )
    estimate.add_argument(
        "--json", action="store_true", help="emit one machine-readable JSON object to stdout"
    )

    verify = sub.add_parser(
        "verify", help="C4: equivalence + exhaustive simulation + mutation (§12)"
    )
    verify.add_argument("design", help="path to design.yaml or .gpk")
    verify.add_argument("--library", required=True, help="path to parts.csv")
    verify.add_argument(
        "--build", default="build", help="build directory (default: %(default)s)"
    )
    verify.add_argument(
        "--properties-only",
        action="store_true",
        help="run only the §11 property checks (sby), not synthesis/equivalence/sim",
    )
    verify.add_argument(
        "--json", action="store_true", help="emit one machine-readable JSON object to stdout"
    )

    simulate_p = sub.add_parser(
        "simulate", help="C11: the exhaustive divergence table (expected vs mapped)"
    )
    simulate_p.add_argument("design", help="path to design.yaml or .gpk")
    simulate_p.add_argument(
        "--library", help="path to parts.csv (needed to evaluate the mapped netlist)"
    )
    simulate_p.add_argument(
        "--build", default="build", help="build directory (default: %(default)s)"
    )
    simulate_p.add_argument(
        "--mapped", help="path to a mapped.json; overrides --build/mapped.json"
    )
    simulate_p.add_argument(
        "--json", action="store_true", help="emit one machine-readable JSON object to stdout"
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
    build.add_argument(
        "--allow-unverified-gates-per-pkg",
        action="store_true",
        help=(
            "proceed even though a multi-gate part's gates_per_pkg is a "
            "placeholder; the resulting BOM may not be physically buildable"
        ),
    )
    build.add_argument(
        "--json", action="store_true", help="emit one machine-readable JSON object to stdout"
    )

    analyse = sub.add_parser(
        "analyse", help="C7 standalone: SCOAP + stuck-at over an existing build directory"
    )
    analyse.add_argument("dir", help="build/out directory containing mapped.json + cells.lib")
    analyse.add_argument(
        "--design", help="path to design.yaml (optional: exact flop count, constraints, data-input split)"
    )
    analyse.add_argument(
        "--library", help="path to parts.csv (optional: package cost + static current metrics)"
    )
    analyse.add_argument(
        "--json", action="store_true", help="emit one machine-readable JSON object to stdout"
    )

    provenance_p = sub.add_parser(
        "provenance",
        help="§15.1 provenance map over an existing build directory (for the GUI)",
    )
    provenance_p.add_argument("dir", help="build/out directory containing premap.json + mapped.json")
    provenance_p.add_argument(
        "--json", action="store_true", help="emit one machine-readable JSON object to stdout"
    )

    mapped_p = sub.add_parser(
        "mapped-netlist",
        help="emit the mapped netlist (Yosys write_json) for the schematic view",
    )
    mapped_p.add_argument("dir", help="build/out directory containing mapped.json")
    mapped_p.add_argument(
        "--json", action="store_true", help="emit one machine-readable JSON object to stdout"
    )

    packed_p = sub.add_parser(
        "packed-netlist",
        help="emit the packed view (package boundaries) for the schematic's packed layer",
    )
    packed_p.add_argument("dir", help="build/out directory containing packed.json")
    packed_p.add_argument(
        "--json", action="store_true", help="emit one machine-readable JSON object to stdout"
    )

    examples_p = sub.add_parser(
        "examples", help="bundled example projects (§18.1)"
    )
    examples_sub = examples_p.add_subparsers(dest="examples_command", required=True)
    list_p = examples_sub.add_parser("list", help="list the bundled examples")
    list_p.add_argument(
        "--json", action="store_true", help="emit one machine-readable JSON object to stdout"
    )
    extract_p = examples_sub.add_parser(
        "extract", help="copy a bundled example into a directory"
    )
    extract_p.add_argument("name", help="example name (see `gatepack examples list`)")
    extract_p.add_argument("-o", "--output", required=True, help="target directory")

    doctor_p = sub.add_parser(
        "doctor",
        help="report external-toolchain and bundled-resource status",
    )
    doctor_p.add_argument(
        "--json", action="store_true", help="emit one machine-readable JSON object to stdout"
    )

    project = sub.add_parser(
        "project", help="single-file project format (§10.4)"
    )
    project_sub = project.add_subparsers(dest="project_command", required=True)

    bundle_p = project_sub.add_parser(
        "bundle", help="exploded directory -> single-file .gpk"
    )
    bundle_p.add_argument("source", help="project directory (design.yaml + optional csv)")
    bundle_p.add_argument("-o", "--output", required=True, help="output .gpk path")

    explode_p = project_sub.add_parser(
        "explode", help="single-file .gpk -> exploded directory"
    )
    explode_p.add_argument("gpk", help="path to a .gpk file")
    explode_p.add_argument("-o", "--output", required=True, help="output directory")

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
    if args.command == "simulate":
        return _cmd_simulate(args)
    if args.command == "build":
        return _cmd_build(args)
    if args.command == "analyse":
        return _cmd_analyse(args)
    if args.command == "provenance":
        return _cmd_provenance(args)
    if args.command == "mapped-netlist":
        return _cmd_mapped_netlist(args)
    if args.command == "packed-netlist":
        return _cmd_packed_netlist(args)
    if args.command == "examples":
        if args.examples_command == "list":
            return _cmd_examples_list(args)
        if args.examples_command == "extract":
            return _cmd_examples_extract(args)
    if args.command == "doctor":
        return _cmd_doctor(args)
    if args.command == "project":
        if args.project_command == "bundle":
            return _cmd_project_bundle(args)
        if args.project_command == "explode":
            return _cmd_project_explode(args)
    parser.error(f"unknown command {args.command!r}")
    return EXIT_USAGE


def _cmd_lib_check(args: argparse.Namespace) -> int:
    csv_path = Path(args.csv)
    if csv_path.suffix == ".gpk":
        return _cmd_lib_check_gpk(csv_path)
    try:
        parts = load_parts(csv_path)
    except parts_mod.PartError as exc:
        if args.json:
            _json_err("lib", error(GP_LIBRARY, str(exc)))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 1

    included, excluded = parts_mod.select_for_liberty(
        parts, project_vcc=args.vcc, allow_single_source=args.allow_single_source
    )
    missing, refs_path = refs_mod.check_citations(parts, csv_path)
    citations = refs_mod.parse_refs(refs_path)

    # Pin-map consistency + placeholder count.  The pin map is optional: a
    # library with no ``<name>.pins.csv`` loads an empty map and skips these
    # checks without changing anything else.
    try:
        pinmaps = pinmap_mod.load_pinmaps_cited(csv_path)
    except pinmap_mod.PinMapError as exc:
        if args.json:
            _json_err("lib", error(GP_LIBRARY, str(exc)))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 1
    pin_violations = pinmap_mod.check_pinmaps(parts, pinmaps)
    pin_placeholder = sum(1 for pm in pinmaps.values() if not pm.is_verified)

    if args.json:
        # An inconsistent pin map is a hard error (a wrong pinout reaches a
        # board); the *placeholder count* is a finding, not a gate, and stays
        # out of the JSON payload so the IPC contract is unchanged.
        if pin_violations:
            _json_err(
                "lib",
                error(GP_LIBRARY, "pin map is inconsistent:\n" + "\n".join(pin_violations)),
            )
            return 1
        payload = api.library_check_payload(
            csv_path, parts, included, excluded, citations, refs_path
        )
        _json_ok("lib", payload)
        return EXIT_OK

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

    if pin_violations:
        print(
            f"error: {len(pin_violations)} pin-map consistency violation(s):",
            file=sys.stderr,
        )
        for violation in pin_violations:
            print(f"  - {violation}", file=sys.stderr)
        return 1

    cited = len(pinmaps) - pin_placeholder
    print(
        f"pin maps: {len(pinmaps)} part(s) mapped, {pin_placeholder} placeholder, "
        f"{cited} cited"
    )

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
        if args.json:
            _json_err("compile", _command_error(exc))
        else:
            print(f"refused: {exc}", file=sys.stderr)
        return EXIT_ASYNC_REFUSED
    except (CompileError, OSError) as exc:
        if args.json:
            _json_err("compile", _command_error(exc))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    generated = out / "generated.v"
    properties = out / "properties.sv"
    generated.write_text(result.verilog)
    properties.write_text(result.properties)

    if args.json:
        _json_ok(
            "compile",
            api.compile_payload(result.compiled, str(generated), str(properties)),
        )
        return EXIT_OK

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
        if args.json:
            _json_err("estimate", _command_error(exc))
        else:
            print(f"refused: {exc}", file=sys.stderr)
        return EXIT_ASYNC_REFUSED
    except (CompileError, parts_mod.PartError, LibertyError, VccIncompatibleError, OSError) as exc:
        if args.json:
            _json_err("estimate", _command_error(exc))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if args.json:
        cell_counts = api.mapped_cell_counts(Path(args.build) / "mapped.json")
        _json_ok("estimate", api.estimate_payload(result, cell_counts))
        return EXIT_OK

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
        result = run_verify(
            args.design,
            args.library,
            args.build,
            properties_only=args.properties_only,
        )
    except AsyncRefused as exc:
        if args.json:
            _json_err("verify", _command_error(exc))
        else:
            print(f"refused: {exc}", file=sys.stderr)
        return EXIT_ASYNC_REFUSED
    except (CompileError, parts_mod.PartError, LibertyError, OSError) as exc:
        if args.json:
            _json_err("verify", _command_error(exc))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if args.json:
        _json_ok("verify", api.verify_payload(result.report))
        return EXIT_OK if result.report.ok else EXIT_ERROR

    report = result.report
    print(f"verification: {report.checks and result.manifest['verification']['overall']}")
    for check in report.checks:
        suffix = f" (bound {check.bound})" if check.bound is not None else ""
        print(f"  {check.name + ':':26} {check.status.value}{suffix}")
        if check.detail:
            print(f"      {check.detail}")
    if report.mutations:
        for mutation in report.mutations:
            # A mutation that could not be applied is NOT an undetected one.
            # Rendering both as "NOT DETECTED" put three of those beside a
            # "mutation: passed" summary, which reads exactly like the vacuous
            # pass R2/R18 exist to prevent.
            if not getattr(mutation, "applicable", True):
                state = "not applicable"
            elif mutation.detected:
                state = "detected"
            elif mutation.equivalence_only:
                state = "caught by equivalence only"
            else:
                state = "NOT DETECTED"
            print(f"  mutation {mutation.mutation + ':':17} {state}")
    print(f"manifest: {result.paths['manifest']}")
    if report.ok:
        return EXIT_OK
    if report.has_failure:
        return EXIT_ERROR
    return EXIT_ERROR  # not-run is not a pass (§14: never claim an unrun proof)


def _cmd_simulate(args: argparse.Namespace) -> int:
    from gatepack.simulate import build_simulation_table, load_mapped
    from gatepack.parts import load_parts

    try:
        compiled = compile_design_file(args.design).compiled
    except AsyncRefused as exc:
        if args.json:
            _json_err("simulate", _command_error(exc))
        else:
            print(f"refused: {exc}", file=sys.stderr)
        return EXIT_ASYNC_REFUSED
    except (CompileError, OSError) as exc:
        if args.json:
            _json_err("simulate", _command_error(exc))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    try:
        mapped_path = args.mapped if args.mapped else str(Path(args.build) / "mapped.json")
        # Parts first: `load_mapped` needs them to resolve pin directions, which
        # Yosys's post-ABC write_json does not carry. Without that every output
        # evaluates to 'x' and the divergence column can never fire.
        parts = load_parts(args.library) if args.library else []
        mapped = load_mapped(mapped_path, parts)
    except (parts_mod.PartError, OSError) as exc:
        if args.json:
            _json_err("simulate", _command_error(exc))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    table = build_simulation_table(compiled, mapped, parts)

    if args.json:
        _json_ok("simulate", table)
        return EXIT_OK

    print(
        f"design: {compiled.design.name!r} "
        f"({compiled.design.timing_model}, {len(compiled.state_order)} state(s), "
        f"{len(compiled.input_names)} input(s))"
    )
    print(
        f"rows: {len(table['rows'])} "
        f"({'exhaustive' if table['exhaustive'] else 'capped (not exhaustive)'})"
    )
    if mapped is None:
        print("mapped netlist: none — no divergence column (synthesis not run)")
    else:
        diverging = sum(1 for row in table["rows"] if row["diverges"])
        print(f"mapped netlist: {mapped_path}")
        print(f"divergent rows: {diverging}")
    return EXIT_OK
def _cmd_build(args: argparse.Namespace) -> int:
    from gatepack.build import run_build

    try:
        result, paths = run_build(
            args.design,
            args.library,
            out_dir=args.out,
            mapped_json=args.mapped,
            spare_leakage_weight=args.spare_weight,
            allow_unverified_gates_per_pkg=args.allow_unverified_gates_per_pkg,
        )
    except RuntimeError as exc:
        if args.json:
            _json_err("build", _command_error(exc))
        else:
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
        if args.json:
            _json_err("build", _command_error(exc))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    # §C12: persist the packed view alongside the other artefacts so
    # `packed-netlist` can hand it to the renderer without re-deriving the
    # packing (and without a second representation that can disagree).  The
    # renderer keys its SVG by instance name, so `instanceCells` is computed
    # here through `CellNames.to_instance`, the one conversion that exists.
    if result.stable_names is not None:
        packed_path = Path(args.out) / "packed.json"
        packed_path.write_text(
            json.dumps(
                api.packed_view_payload(result.assigned, result.stable_names),
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )

    if args.json:
        mapped_json_path = args.mapped if args.mapped else str(Path(args.out) / "mapped.json")
        _json_ok("build", api.build_payload(result, paths, mapped_json_path))
        return EXIT_OK

    s = result.packed_stats
    print(f"packed: {s.package_count} package(s), {s.spare_count} spare gate(s), "
          f"pack_cost {s.pack_cost:g}")
    for name, path in sorted(paths.items()):
        print(f"wrote {path}")
    return EXIT_OK


def _cmd_provenance(args: argparse.Namespace) -> int:
    """§15.1 provenance map, for the application's linked selection (§15.2).

    The session manager has invoked `gatepack provenance <dir>` since M12; the
    subcommand did not exist, so `provenance()` had never returned data and
    M16's cross-highlights could not work at all.
    """
    from gatepack.provenance.coverage import (
        measure_coverage_from_dir,
        provenance_map_payload,
    )

    try:
        report = measure_coverage_from_dir(args.dir)
    except OSError as exc:
        if args.json:
            _json_err("provenance", _command_error(exc))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if report is None:
        message = (
            f"no captured netlists at {args.dir}: run `gatepack build` first "
            "(provenance is never reported as empty when nothing was measured)"
        )
        if args.json:
            _json_err("provenance", error(GP_IO, message))
        else:
            print(f"error: {message}", file=sys.stderr)
        return EXIT_ERROR

    payload = provenance_map_payload(report)
    if args.json:
        _json_ok("provenance", payload)
        return EXIT_OK

    print(f"provenance coverage: {payload['coverage'] * 100:.1f}% of constructs linked")
    print(f"linked constructs: {len(payload['entries'])}")
    return EXIT_OK


def _cmd_mapped_netlist(args: argparse.Namespace) -> int:
    """The mapped netlist as Yosys wrote it, for C12's schematic view.

    netlistsvg consumes `write_json` output directly, so this hands the file
    through unchanged rather than reshaping it — the renderer must not be given
    a second, divergent representation of the netlist.
    """
    import json as _json

    path = Path(args.dir) / "mapped.json"
    if not path.exists():
        message = (
            f"no mapped netlist at {path}: run `gatepack build` first "
            "(never faked here)"
        )
        if args.json:
            _json_err("mapped-netlist", error(GP_IO, message))
        else:
            print(f"error: {message}", file=sys.stderr)
        return EXIT_ERROR

    try:
        netlist = _json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        if args.json:
            _json_err("mapped-netlist", _command_error(exc))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if args.json:
        _json_ok("mapped-netlist", netlist)
        return EXIT_OK

    modules = list(netlist.get("modules", {}))
    print(f"mapped netlist: {path} ({', '.join(modules) or 'no modules'})")
    return EXIT_OK


def _cmd_packed_netlist(args: argparse.Namespace) -> int:
    """The §C12 packed layer: package boundaries over the mapped netlist.

    ``gatepack build`` writes ``packed.json`` (the ``PackedView`` payload, keyed
    by the same instance names the renderer gets from ``mappedNetlist()``), so
    this hands that file through unchanged rather than re-deriving the packing —
    the renderer must not be given a second, divergent view of the packages.
    """
    import json as _json

    path = Path(args.dir) / "packed.json"
    if not path.exists():
        message = (
            f"no packed view at {path}: run `gatepack build` first "
            "(never faked here)"
        )
        if args.json:
            _json_err("packed-netlist", error(GP_IO, message))
        else:
            print(f"error: {message}", file=sys.stderr)
        return EXIT_ERROR

    try:
        payload = _json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        if args.json:
            _json_err("packed-netlist", _command_error(exc))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if args.json:
        _json_ok("packed-netlist", payload)
        return EXIT_OK

    packages = payload.get("packages", [])
    print(f"packed view: {path} ({len(packages)} package(s))")
    return EXIT_OK


def _cmd_analyse(args: argparse.Namespace) -> int:
    from gatepack.analysis.summary import (
        AnalysisUnavailableError,
        dir_only_payload,
        full_analysis_payload,
    )

    try:
        if args.design and args.library:
            payload = full_analysis_payload(args.dir, args.design, args.library)
        else:
            payload = dir_only_payload(args.dir)
    except AnalysisUnavailableError as exc:
        if args.json:
            _json_err("analyse", error(GP_IO, str(exc)))
        else:
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
        if args.json:
            _json_err("analyse", _command_error(exc))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if args.json:
        _json_ok("analyse", payload)
        return EXIT_OK

    faults = payload["faults"]
    print(
        "stuck-at: "
        f"{faults['detected']} detected, {faults['undetected']} undetected, "
        f"{faults['redundant']} redundant, {faults['untestable']} untestable"
    )
    print(f"SCOAP delta: {len(payload['scoap'])} worst net(s)")
    for metric in payload["metrics"]:
        print(f"  {metric['name'] + ':':22} {metric['value']!s:>10} {metric['unit']}")
    if payload["cpldBlockers"]:
        print(f"CPLD blockers: {len(payload['cpldBlockers'])}")
    return EXIT_OK


def _cmd_lib_check_gpk(gpk_path: Path) -> int:
    # §10.4: an embedded library records a sha256 so divergence from an on-disk
    # library is detectable rather than silent.  `lib check <x>.gpk` reports it.
    try:
        project = load_project(gpk_path)
    except ProjectError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    library = project.library
    if library is None:
        print(f"{gpk_path}: no embedded library document")
        return EXIT_OK

    print(
        f"embedded library: source={library.source}, sha256={library.sha256}, "
        f"{len(library.parts)} part(s)"
    )
    status, detail = library_divergence(project, gpk_path.parent)
    if status == "none":
        return EXIT_OK
    if status == "match":
        print(f"library: {detail}")
        return EXIT_OK
    if status == "missing":
        print(f"note: {detail}", file=sys.stderr)
        return EXIT_OK
    print(f"error: {detail}", file=sys.stderr)
    return EXIT_ERROR


def _cmd_doctor(args: argparse.Namespace) -> int:
    """Report toolchain + bundled-resource status. A report, never a gate: a
    missing tool is a visible "missing" entry and ``allToolsPresent: false``,
    and the exit code stays 0 so the bundled core's self-test can always read a
    valid envelope regardless of what the host has."""
    payload = run_doctor()
    if args.json:
        _json_ok("doctor", payload)
        return EXIT_OK

    print(f"gatepack {payload['version']}")
    for tool in payload["tools"]:
        if tool["found"]:
            version = f" ({tool['version']})" if tool.get("version") else ""
            source = tool.get("source") or "?"
            print(f"  {tool['name']:<10} found [{source}]{version}")
        else:
            print(f"  {tool['name']:<10} MISSING")
        print(f"            {tool['purpose']}")
    resources = payload["resources"]
    print(
        "bundled resources: "
        f"common_frontend.ys={'ok' if resources['commonFrontendYs'] else 'MISSING'}, "
        f"M-cell models={'ok' if resources['mcellModels'] else 'MISSING'} "
        f"({resources['mcellCount']})"
    )
    pinmaps = pinmap_mod.bundled_pin_map_summary()
    if pinmaps is not None:
        print(
            "bundled library pin maps: "
            f"{pinmaps['total']} part(s), {pinmaps['placeholder']} placeholder, "
            f"{pinmaps['cited']} cited"
        )
    print(f"all required tools present: {payload['allToolsPresent']}")
    return EXIT_OK


def _cmd_examples_list(args: argparse.Namespace) -> int:
    from gatepack.examples import list_examples

    found = list_examples()
    if args.json:
        _json_ok("examples", api.examples_list_payload(found))
        return EXIT_OK

    if not found:
        print("no bundled examples found", file=sys.stderr)
        return EXIT_USAGE
    for example in found:
        marker = " (showcase)" if example.is_showcase else ""
        print(f"{example.name}{marker}")
        if example.summary:
            print(f"    {example.summary}")
    return EXIT_OK


def _cmd_examples_extract(args: argparse.Namespace) -> int:
    from gatepack.examples import ExampleError, extract

    try:
        written = extract(args.name, args.output)
    except ExampleError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    for path in written:
        print(f"wrote {path}")
    return EXIT_OK


def _cmd_project_bundle(args: argparse.Namespace) -> int:
    source = Path(args.source)
    try:
        project = load_project(source)
        text = bundle(source)
    except (ProjectError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)

    documents = ["design"]
    if project.truth_table is not None:
        documents.append("truth_table")
    if project.library is not None:
        documents.append("library")
    print(f"bundled {source} -> {out} ({', '.join(documents)})")
    return EXIT_OK


def _cmd_project_explode(args: argparse.Namespace) -> int:
    gpk_path = Path(args.gpk)
    try:
        text = gpk_path.read_text()
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    try:
        written = explode_to_dir(text, args.output)
    except ProjectError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    for path in written:
        print(f"wrote {path}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
