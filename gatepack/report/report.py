"""C8 — report generator (§12 C8).

Assembles C7 output into ``report.md``.  Every estimate carries its assumptions
**inline**, never in a footnote.  The report states plainly that tPD excludes PCB
parasitics and is not STA (§13.3), and that dynamic current excludes routing
capacitance and is not a budget.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from gatepack.analysis.clock import TimingReport
from gatepack.analysis.cpld import blockers_summary, cpld_alternative_flow
from gatepack.analysis.faults import FaultReport
from gatepack.analysis.power import DynamicCurrent, StaticCurrent
from gatepack.analysis.scoap import ScoapReport
from gatepack.diagnostic import Diagnostic
from gatepack.emit.bom import BomRow
from gatepack.emit.refdes import RefdesDelta
from gatepack.pack.packer import PackingStats
from gatepack.provenance.coverage import CoverageReport


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
    provenance: CoverageReport | None = None
    cell_refdes: Mapping[str, str] | None = None


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
    lines.append("| part | manufacturers | package | qty | refdes | tier | electrical data |")
    lines.append("|---|---|---|---|---|---|---|")
    for row in inp.packed_bom:
        verification = "unverified" if row.unverified else "verified"
        lines.append(
            f"| {row.part_number} | {row.manufacturers} | {row.package} | "
            f"{row.quantity} | {';'.join(row.refdes)} | {row.tier} | {verification} |"
        )
    lines.append("")
    unverified = [r for r in inp.packed_bom if r.unverified]
    if unverified:
        lines.append(
            "_The BOM above marks parts whose electrical figures (package, "
            "gates-per-package, tPD, leakage, supply range) rest on unverified/"
            "placeholder data from `parts.csv`. These figures must not be used as "
            "design data until a real, pinned datasheet citation backs them "
            "(`libraries/74aup.refs.md`). A wrong `gates_per_pkg` on a multi-gate "
            "part yields a netlist that physically cannot be built._"
        )
        lines.append("")
        lines.append(
            f"Unverified parts in this BOM: "
            f"{', '.join(sorted({r.part_number for r in unverified}))}."
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
            lines.append(f"- worst path: {_timing_path(t.worst_path, inp.cell_refdes)}")
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

    lines.append("## Provenance (§15.1, M11b)")
    lines.append("")
    if inp.provenance is not None:
        p = inp.provenance
        lines.append(
            "_Measured from premap.json vs mapped.json. `exact` = the construct's "
            "`gp_src` attribute survives into the final netlist; `inferred` = it "
            "survived `abc` but was dropped by `opt_clean` (recovered from a "
            "post-`abc`, pre-`opt_clean` capture, and not resolvable onto specific "
            "gates — M0-FINDINGS §4a); `absent` = no link at all, reported by name "
            "below rather than as a bare percentage._"
        )
        lines.append("")
        lines.append("By carrier:")
        lines.append("")
        lines.append("| carrier | total | exact | inferred | absent |")
        lines.append("|---|---|---|---|---|")
        lines.append(_provenance_carrier_row("net", p.net))
        lines.append(_provenance_carrier_row("cell", p.cell))
        lines.append("")
        lines.append("By construct kind:")
        lines.append("")
        lines.append("| kind | total | exact | inferred | absent |")
        lines.append("|---|---|---|---|---|")
        for kind in _provenance_kinds(p):
            k = p.by_kind[kind]
            lines.append(
                f"| {kind} | {k.total} | {k.exact} | {k.inferred} | {k.absent} |"
            )
        lines.append("")
        unlinked = _provenance_unlinked(p)
        if unlinked:
            lines.append(f"Constructs with no link: {', '.join(unlinked)}")
        else:
            lines.append("Constructs with no link: none.")
        lines.append("")
        lines.append(
            f"_Aggregate coverage {_fmt(p.coverage * 100)}% of constructs linked; "
            "the per-kind table above is the figure that matters — the aggregate "
            "conceals a weak axis such as transitions at 2/5 (§20 M11b)._"
        )
        lines.append("")
    else:
        lines.append(
            "- provenance not computed (no provenance map passed to the report "
            "generator; premap.json/mapped.json required)."
        )
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


def _timing_path(
    path: Sequence[str], cell_refdes: Mapping[str, str] | None
) -> str:
    """Render a worst-path cell list as refdes (``U6 -> U19 -> U2``) when known.

    ABC's internal node names (``$abc$148$...``) are unreadable; the reader wants
    refdes.  ``cell_refdes`` maps a mapped cell name to its reference designator
    (from ``refdes.json``); where it is absent the raw name is kept rather than
    guessed at.
    """
    if cell_refdes is None:
        return " -> ".join(path)
    return " -> ".join(cell_refdes.get(name, name) for name in path)


def _provenance_carrier_row(label: str, cov) -> str:
    return f"| {label} | {cov.total} | {cov.exact} | {cov.inferred} | {cov.absent} |"


def _provenance_kinds(p: CoverageReport) -> tuple[str, ...]:
    order = ("states", "transitions", "output_logic", "inputs", "reset")
    present = [k for k in order if k in p.by_kind]
    rest = sorted(k for k in p.by_kind if k not in order)
    return tuple(present + rest)


def _provenance_unlinked(p: CoverageReport) -> list[str]:
    unlinked: list[str] = []
    for kind in _provenance_kinds(p):
        unlinked.extend(p.by_kind[kind].unlinked)
    return unlinked
