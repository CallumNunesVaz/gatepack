"""C8 — report generator (§12 C8).

Assembles C7 output into ``report.md``.  Every estimate carries its assumptions
**inline**, never in a footnote.  The report states plainly that tPD excludes PCB
parasitics and is not STA (§13.3), and that dynamic current excludes routing
capacitance and is not a budget.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from gatepack.analysis.clock import TimingReport
from gatepack.analysis.cpld import blockers_summary, cpld_alternative_flow
from gatepack.analysis.faults import FaultReport
from gatepack.analysis.power import DynamicCurrent, StaticCurrent
from gatepack.analysis.scoap import ScoapReport
from gatepack.diagnostic import Diagnostic
from gatepack.emit.bom import BomRow
from gatepack.emit.refdes import RefdesDelta
from gatepack.pack.packer import PackingStats


@dataclass
class ReportInputs:
    design: str
    timing_model: str
    packed_stats: PackingStats
    unpacked_stats: PackingStats
    packed_bom: Sequence[BomRow] = field(default_factory=list)
    static_current: StaticCurrent | None = None
    spare_leakage_ua: float = 0.0
    dynamic_current: DynamicCurrent | None = None
    timing: TimingReport | None = None
    refdes_delta: RefdesDelta | None = None
    packages: Sequence[tuple[str, str]] = field(default_factory=list)  # (refdes, rationale)
    notes: Sequence[str] = field(default_factory=list)
    cpld_blockers: Sequence[Diagnostic] = field(default_factory=list)
    scoap: ScoapReport | None = None
    faults: FaultReport | None = None


def _fmt(value: float) -> str:
    return f"{value:g}"


def _scoap_value(value: int | None) -> str:
    return "∞" if value is None else str(value)


def emit_report(inp: ReportInputs) -> str:
    lines: list[str] = []
    lines.append(f"# {inp.design} — build report")
    lines.append("")
    lines.append(f"timing model: {inp.timing_model}")
    lines.append("")

    lines.append("## Packing (§9.7)")
    lines.append("")
    lines.append("| result | packages | spare gates | package cost | pack_cost |")
    lines.append("|---|---|---|---|---|")
    lines.append(
        _row("packed", inp.packed_stats) + _row("unpacked", inp.unpacked_stats)
    )
    lines.append("")
    lines.append(
        "_pack_cost = sum(package_cost) + spare_count * spare_leakage_weight. "
        "Package count and spare count are reported separately on purpose; "
        "spare gates are a cost, not free (§9.7)._"
    )
    lines.append("")

    lines.append("## Bill of materials")
    lines.append("")
    lines.append("| part | manufacturers | package | qty | refdes | tier |")
    lines.append("|---|---|---|---|---|---|")
    for row in inp.packed_bom:
        lines.append(
            f"| {row.part_number} | {row.manufacturers} | {row.package} | "
            f"{row.quantity} | {';'.join(row.refdes)} | {row.tier} |"
        )
    lines.append("")

    if inp.packages:
        lines.append("## Package grouping (per-package rationale)")
        lines.append("")
        lines.append("| refdes | rationale |")
        lines.append("|---|---|")
        for ref, rationale in inp.packages:
            lines.append(f"| {ref} | {rationale} |")
        lines.append("")

    lines.append("## Power (§13.3)")
    lines.append("")
    if inp.static_current is not None:
        sc = inp.static_current
        lines.append("Static current, broken out by tier (assumption: IQ values are "
                     "as cited in parts.csv; no temperature derating is applied "
                     "because the data model has no derating curve):")
        lines.append("")
        lines.append("| tier | static current (µA) |")
        lines.append("|---|---|")
        for tier, value in sc.by_tier.items():
            lines.append(f"| {tier} | {_fmt(value)} |")
        lines.append(f"| **total** | **{_fmt(sc.total_ua)}** |")
        lines.append("")
    lines.append(
        f"Spare-gate leakage penalty (estimate: each spare slot's idle IQ, §9.7): "
        f"{_fmt(inp.spare_leakage_ua)} µA"
    )
    lines.append("")
    if inp.dynamic_current is not None:
        dc = inp.dynamic_current
        lines.append(f"Dynamic current (estimate): {_fmt(dc.ua)} µA")
        lines.append(f"- {dc.note}")
        lines.append("")
    else:
        lines.append("Dynamic current: not estimated (no frequency/capacitance "
                     "assumptions supplied).")
        lines.append("")

    lines.append("## Timing (§13.3)")
    lines.append("")
    if inp.timing is not None:
        t = inp.timing
        lines.append(f"- worst-case combinational depth: {t.combinational_depth} levels")
        lines.append(f"- cumulative tPD: {_fmt(t.cumulative_tpd_ns)} ns")
        if t.worst_path:
            lines.append(f"- worst path: {' -> '.join(t.worst_path)}")
        lines.append(f"- note: {t.note}")
        lines.append("")
    else:
        lines.append("- timing not computed (no mapped netlist).")
        lines.append("")

    if inp.refdes_delta is not None:
        d = inp.refdes_delta
        lines.append("## Reference designator delta ([R4-19])")
        lines.append("")
        lines.append(f"- unchanged: {d.unchanged}")
        lines.append(f"- added: {len(d.added)}")
        lines.append(f"- removed: {len(d.removed)}")
        lines.append(f"- renumbered: {len(d.renumbered)}")
        if d.renumbered:
            lines.append("")
            for pkg_id, old, new in d.renumbered:
                lines.append(f"  - {pkg_id}: {old} -> {new}")
        lines.append("")

    lines.append("## Testability (SCOAP, §13.1)")
    lines.append("")
    if inp.scoap is not None:
        s = inp.scoap
        lines.append(f"- {s.note}.")
        lines.append("")
        lines.append("| net | CC0 | CC1 | observability |")
        lines.append("|---|---|---|---|")
        for n in s.delta:
            lines.append(
                f"| {n.net} | {_scoap_value(n.controllability0)} | "
                f"{_scoap_value(n.controllability1)} | {_scoap_value(n.observability)} |"
            )
        lines.append("")
        if s.unobservable:
            lines.append(
                "Unobservable nets (no path to any primary output; rendered as an "
                f"overlay by C12): {', '.join(s.unobservable)}"
            )
        else:
            lines.append("Unobservable nets: none.")
        lines.append("")
    else:
        lines.append("- SCOAP not computed (no mapped netlist).")
        lines.append("")

    lines.append("## Fault analysis (§13.2)")
    lines.append("")
    if inp.faults is not None:
        f = inp.faults
        lines.append(f"- single stuck-at; {f.note}.")
        lines.append(f"- uncollapsed faults (nets + cell pins): {f.uncollapsed}")
        lines.append(
            f"- collapsed faults (equivalence + dominance): {f.collapsed}"
        )
        lines.append(
            f"- detected: {f.detected}, undetected: {f.undetected}, "
            f"redundant: {f.redundant}, untestable: {f.untestable}"
        )
        if f.exhaustive:
            lines.append(f"- vector set: exhaustive ({f.vectors_applied} vectors)")
        else:
            lines.append(
                f"- vector set: PARTIAL — {f.vectors_applied} of "
                f"{f.vectors_total} vectors, so 'undetected' means a test may "
                f"exist outside the applied set"
            )
        lines.append("")
    else:
        lines.append("- fault analysis not computed (no mapped netlist).")
        lines.append("")

    lines.append("## CPLD fallback (§24.1)")
    lines.append("")
    lines.append(f"- blockers: {blockers_summary(inp.cpld_blockers)}")
    lines.append(f"- alternative flow: {cpld_alternative_flow()}")
    if inp.cpld_blockers:
        lines.append("")
        for b in inp.cpld_blockers:
            loc = f" ({b.path}:{b.line})" if b.line is not None else ""
            lines.append(f"- `{b.code}` {b.message}{loc}")
    lines.append("")

    if inp.notes:
        lines.append("## Notes")
        lines.append("")
        for note in inp.notes:
            lines.append(f"- {note}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _row(label: str, stats: PackingStats) -> str:
    return (
        f"| {label} | {stats.package_count} | {stats.spare_count} | "
        f"{_fmt(stats.package_cost)} | {_fmt(stats.pack_cost)} |\n"
    )
