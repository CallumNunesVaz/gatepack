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
from gatepack.verify.base import CheckResult, CheckStatus

if TYPE_CHECKING:  # pragma: no cover - type annotations only
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
    if status == "not_run" and check.detail:
        out["skippedReason"] = check.detail
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
    "mapped_cell_counts",
    "metric",
    "verify_payload",
]
