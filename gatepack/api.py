"""The ``--json`` machine-output contract (app/shared/api.ts).

The Electron main process, renderer and this core all depend on the exact
envelope shape in ``app/shared/api.ts``.  This module emits it: field name for
field name, never a variant.  Two helpers build the two envelope halves and the
payload builders assemble each command's ``data`` object.

Fields that the analysis modules genuinely do not compute yet (SCOAP §13.1,
stuck-at §13.2) are emitted with an honest empty value — never fabricated — and
the gap is recorded in ``docs/BUILD-NOTES-M6.md``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Sequence, TYPE_CHECKING

from gatepack.diagnostic import Diagnostic
from gatepack.emit.bom import collect_bom
from gatepack.parts import Exclusion, Part
from gatepack.verify.base import CheckResult, CheckStatus

if TYPE_CHECKING:  # pragma: no cover - type annotations only
    from gatepack.examples import Example
    from gatepack.frontend.model import CompiledDesign

SCHEMA = 1

CPLD_ALTERNATIVE = (
    "flash CPLD (e.g. MAX V) driven by the portable inferred Verilog in generated.v"
)

# CheckStatus -> api.ts CheckStatus.  NOT_APPLICABLE (sim above the §21.4 cap)
# is an honest non-verdict, rendered as `not_run` with the reason in
# `skippedReason`.
_STATUS_MAP: dict[CheckStatus, str] = {
    CheckStatus.PASSED: "passed",
    CheckStatus.BOUNDED_PASS: "bounded",
    CheckStatus.FAILED: "failed",
    CheckStatus.NOT_RUN: "not_run",
    CheckStatus.NOT_APPLICABLE: "not_run",
}


# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------


def envelope_ok(command: str, data: dict, warnings: Sequence[Diagnostic] = ()) -> dict:
    return {
        "ok": True,
        "command": command,
        "schema": SCHEMA,
        "data": data,
        "warnings": [w.to_dict() for w in warnings],
    }


def envelope_err(
    command: str, error: Diagnostic, warnings: Sequence[Diagnostic] = ()
) -> dict:
    return {
        "ok": False,
        "command": command,
        "schema": SCHEMA,
        "error": error.to_dict(),
        "warnings": [w.to_dict() for w in warnings],
    }


def dump(envelope: dict) -> str:
    """Serialize an envelope as exactly one JSON object + trailing newline."""
    return json.dumps(envelope, sort_keys=True) + "\n"


# ---------------------------------------------------------------------------
# compile
# ---------------------------------------------------------------------------


def compile_payload(
    compiled: "CompiledDesign", verilog_path: str, properties_path: str
) -> dict:
    return {
        "verilogPath": verilog_path,
        "propertiesPath": properties_path,
        "flopCount": compiled.flop_count,
        "stateCount": len(compiled.state_order),
        "encoding": compiled.encoding,
        "johnsonSuggestion": compiled.johnson_suggestion,
    }


# ---------------------------------------------------------------------------
# estimate
# ---------------------------------------------------------------------------


def _estimate_reasons(verdict) -> list[str]:
    reasons: list[str] = []
    for name, metric in verdict.metrics.items():
        if metric.status == "red":
            reasons.append(f"{name} is red (value {_fmt(metric.value)})")
        elif metric.status == "amber":
            reasons.append(f"{name} is amber (value {_fmt(metric.value)})")
    return reasons


def _fmt(value) -> str:
    return "unknown" if value is None else f"{value:g}"


def estimate_payload(result, cell_counts: Mapping[str, int] | None = None) -> dict:
    verdict = result.verdict
    compiled = result.compiled
    package_count = verdict.metrics["package count"].value
    return {
        "verdict": verdict.overall,
        "reasons": _estimate_reasons(verdict),
        "packageCount": int(package_count) if package_count is not None else None,
        "flopCount": compiled.flop_count,
        "cellCounts": dict(cell_counts or {}),
        "alternative": CPLD_ALTERNATIVE if verdict.overall == "red" else None,
    }


def mapped_cell_counts(mapped_json_path: str | Path) -> dict[str, int]:
    """Per-type mapped cell counts from a Yosys ``mapped.json`` (empty if absent).

    ``packageCount`` in the estimate payload is the total of these counts; when
    Yosys has not run there is no ``mapped.json`` and both are empty/None —
    honest, never fabricated.
    """
    try:
        data = json.loads(Path(mapped_json_path).read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    counts: dict[str, int] = {}
    for module in data.get("modules", {}).values():
        for cell in module.get("cells", {}).values():
            ctype = cell.get("type", "")
            if ctype.startswith("$"):
                continue
            counts[ctype] = counts.get(ctype, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------


def check_payload(check: CheckResult) -> dict:
    status = _STATUS_MAP[check.status]
    out: dict = {
        "name": check.name,
        "kind": check.kind or "property",
        "status": status,
        "durationMs": check.duration_ms,
    }
    if check.bound is not None:
        out["bound"] = check.bound
    if status == "not_run":
        if check.detail:
            out["skippedReason"] = check.detail
    elif check.detail:
        # A failed/bounded check's reason is the difference between "your design
        # is wrong" and "the toolchain could not run" (e.g. an sby ERROR).  The
        # IPC `Check` contract does not type this field yet (api.ts/envelope.cts
        # are read-only here), so the app strips it; the CLI `--json` and the
        # manifest.json carry it, which is where a wrong-result diagnosis starts.
        out["detail"] = check.detail
    if check.counterexample is not None:
        out["counterexample"] = {
            "steps": [dict(step) for step in check.counterexample.steps],
            "pointers": list(check.counterexample.pointers),
        }
    return out


def verify_payload(report) -> dict:
    checks = [check_payload(c) for c in report.checks]
    all_passed = all(
        c["status"] == "passed" for c in checks
    )
    return {"checks": checks, "allPassed": all_passed}


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------


def bomline(row) -> dict:
    manufacturers = [m for m in row.manufacturers.split(";") if m]
    return {
        "partNumber": row.part_number,
        "manufacturers": manufacturers,
        "package": row.package,
        "quantity": row.quantity,
        "refdes": list(row.refdes),
        "tier": row.tier,
        # §C13 / api.ts: single-sourced is a hard visual marker.  This counts
        # manufacturers only, exactly as api.ts defines it (equivalents are not
        # part of the definition).
        "singleSourced": len(manufacturers) < 2,
        # How many gates this package holds. The packing view needs it to know
        # whether grouping can achieve anything, instead of hardcoding a claim.
        "gatesPerPackage": row.gates_per_pkg,
        # Whether this row's electrical figures rest on unverified/placeholder
        # data rather than a datasheet citation. The renderer must be able to
        # mark it without re-reading parts.csv.
        "unverified": row.unverified,
    }


def metric(name: str, value, unit: str, limit) -> dict:
    violated = limit is not None and value is not None and value > limit
    return {
        "name": name,
        "value": value,
        "unit": unit,
        "limit": limit,
        "violated": violated,
    }


def analysis_summary(compiled, result, cpld_blockers: Sequence[Diagnostic]) -> dict:
    constraints = compiled.design.constraints
    static = result.static_current
    timing = result.timing
    metrics = [
        metric(
            "package count",
            result.packed_stats.package_count,
            "packages",
            constraints.max_packages,
        ),
        metric("flop count", compiled.flop_count, "flops", constraints.max_flops),
        metric(
            "static current",
            static.total_ua if static is not None else None,
            "uA",
            constraints.max_static_ua,
        ),
        metric(
            "combinational depth",
            timing.combinational_depth if timing is not None else None,
            "levels",
            None,
        ),
        metric("pack cost", result.packed_stats.pack_cost, "area", None),
    ]
    return {
        "metrics": metrics,
        # §13.1 SCOAP delta table and §13.2 stuck-at classification.  Computed
        # by gatepack/analysis/{scoap,faults}.py over the resolved mapped
        # netlist and carried on the BuildResult; when synthesis did not run
        # there is no netlist and both degrade to an honest empty value (the
        # reason is stated in report.md, never as a fabricated number).
        "scoap": result.scoap.to_wire() if getattr(result, "scoap", None) else [],
        "faults": (
            result.faults.to_wire()
            if getattr(result, "faults", None)
            else {"detected": 0, "undetected": 0, "redundant": 0, "untestable": 0}
        ),
        "cpldBlockers": [d.to_dict() for d in cpld_blockers],
    }


def packed_view_payload(assigned, stable_names) -> dict:
    """The §C12 packed layer payload (``PackedView`` in app/shared/api.ts).

    ``assigned`` is the ``(refdes, PackageGroup)`` list from
    :func:`gatepack.emit.refdes.assign_refdes`; ``stable_names`` the
    :class:`~gatepack.netlist.CellNames` instance -> stable mapping.

    ``group.cells`` holds **stable** names (what ``packing.force_groups``
    records), while ``instanceCells`` must be the mapped-netlist **instance**
    names — that is what the rendered netlist is keyed by.  The conversion is
    ``stable_names.to_instance``, the one reverse lookup owned by ``CellNames``;
    it is never re-derived here (confusing the two spaces has caused four
    separate defects).
    """
    packages = []
    for ref, group in assigned:
        packages.append(
            {
                "refdes": ref,
                "partNumber": group.part.part_number or group.part.cell,
                "cells": list(group.cells),
                "instanceCells": [
                    stable_names.to_instance(stable) for stable in group.cells
                ],
                "capacity": group.capacity,
                "spare": group.spare,
                "rationale": group.rationale,
            }
        )
    return {"packages": packages}


def build_payload(result, paths: Mapping[str, Path], mapped_json_path: str | Path) -> dict:
    bom_rows = collect_bom(result.assigned)
    return {
        "bomPath": str(paths["bom"]),
        "netlistPath": str(paths["netlist"]),
        "reportPath": str(paths["report"]),
        "mappedJsonPath": str(mapped_json_path),
        "packageCount": result.packed_stats.package_count,
        "spareCount": result.packed_stats.spare_count,
        "packCost": result.packed_stats.pack_cost,
        "bom": [bomline(r) for r in bom_rows],
        "analysis": analysis_summary(result.compiled, result, result.cpld_blockers),
        # §C13: the application persists packing overrides as `force_groups`,
        # which the packer resolves against STABLE names. Everything the
        # renderer can see uses ABC's instance names, which change between
        # runs, so it needs this map to write an override that survives.
        # `stable_names` is a `CellNames` (instance -> stable); `dict()` of it
        # is exactly the `Record<string, string>` the contract requires.
        "stableCellNames": dict(result.stable_names) if result.stable_names else {},
    }


def build_async_payload(
    result, paths: Mapping[str, Path], mapped_json_path: str | Path
) -> dict:
    """The ``build`` payload for an *asynchronous* design.

    Same envelope shape as :func:`build_payload`, but the analysis block omits
    the synchronous-only metrics (flop count, combinational depth, SCOAP,
    stuck-at) rather than emitting numbers an asynchronous netlist does not
    support.  The reason for each omission is stated in ``report.md`` (§C8).
    """
    bom_rows = collect_bom(result.assigned)
    static = result.static_current
    metrics = [
        metric(
            "package count", result.packed_stats.package_count, "packages", None
        ),
        metric(
            "static current",
            static.total_ua if static is not None else None,
            "uA",
            None,
        ),
        metric("pack cost", result.packed_stats.pack_cost, "area", None),
    ]
    return {
        "bomPath": str(paths["bom"]),
        "netlistPath": str(paths["netlist"]),
        "reportPath": str(paths["report"]),
        "mappedJsonPath": str(mapped_json_path),
        "packageCount": result.packed_stats.package_count,
        "spareCount": result.packed_stats.spare_count,
        "packCost": result.packed_stats.pack_cost,
        "bom": [bomline(r) for r in bom_rows],
        "analysis": {
            "metrics": metrics,
            "scoap": [],
            "faults": {"detected": 0, "undetected": 0, "redundant": 0, "untestable": 0},
            "cpldBlockers": [],
        },
        "stableCellNames": dict(result.stable_names) if result.stable_names else {},
    }


# ---------------------------------------------------------------------------
# lib check (§C2)
# ---------------------------------------------------------------------------


def _citation_unverified(citation: str | None) -> bool:
    """True when a citation marks its electrical data as unverified/placeholder.

    ``citation`` is the last column of the ``<name>.refs.md`` row, e.g.
    ``"placeholder — unverified"``; a genuinely verified entry does not carry
    either word. ``None`` (uncited) is reported separately, so it is *not*
    "unverified" here — an uncited cell is a harder finding than an unverified
    one, and conflating the two hides which one the user is looking at.
    """
    if citation is None:
        return False
    lowered = citation.lower()
    return "unverified" in lowered or "placeholder" in lowered


def library_part_payload(
    part: Part, citation: str | None, excluded: Exclusion | None
) -> dict:
    return {
        "cell": part.cell,
        "tier": part.tier,
        "family": part.family,
        "partNumber": part.part_number,
        "function": part.function,
        "inputs": part.inputs,
        "gatesPerPackage": part.gates_per_pkg,
        "package": part.package,
        "manufacturers": list(part.mfrs),
        "equivalents": len(part.equivalents),
        "secondSourceCount": part.second_source_count,
        # "not cited" is an explicit null, never an absent key — the reader must
        # be able to tell "has a citation" from "was not checked".
        "citation": citation,
        "unverified": _citation_unverified(citation),
        "excluded": excluded is not None,
        "exclusionReason": excluded.reason.value if excluded is not None else None,
    }


def library_check_payload(
    csv_path: str | Path,
    parts: Sequence[Part],
    included: Sequence[Part],
    excluded: Sequence[Exclusion],
    citations: Mapping[str, str],
    refs_path: str | Path,
) -> dict:
    """The ``gatepack lib check --json`` report (§C2, app/shared/api.ts).

    A report, never a gate: the human CLI exits non-zero on a missing refs file
    or missing citations, but the JSON form always emits the full picture —
    ``refsPresent``, ``missingCitations`` and per-part ``citation`` — so the GUI
    can show *why* validation failed rather than a bare error. Only a malformed
    CSV (unparseable) is a hard ``ok: false``.
    """
    excluded_by_cell = {e.cell: e for e in excluded}
    return {
        "path": str(csv_path),
        "refsPath": str(refs_path),
        "refsPresent": Path(refs_path).exists(),
        "cellCount": len(parts),
        "includedCount": len(included),
        "excludedCount": len(excluded),
        "missingCitations": [p.cell for p in parts if p.cell not in citations],
        "parts": [
            library_part_payload(p, citations.get(p.cell), excluded_by_cell.get(p.cell))
            for p in parts
        ],
    }


def examples_list_payload(examples: Sequence["Example"]) -> dict:
    """The ``gatepack examples list --json`` payload (§18.1)."""
    return {
        "examples": [
            {
                "name": example.name,
                "summary": example.summary,
                "isShowcase": example.is_showcase,
            }
            for example in examples
        ]
    }


__all__ = [
    "CPLD_ALTERNATIVE",
    "SCHEMA",
    "analysis_summary",
    "bomline",
    "build_payload",
    "check_payload",
    "compile_payload",
    "dump",
    "envelope_err",
    "envelope_ok",
    "estimate_payload",
    "examples_list_payload",
    "library_check_payload",
    "library_part_payload",
    "mapped_cell_counts",
    "metric",
    "packed_view_payload",
    "verify_payload",
]
