"""Provenance coverage measurement + ``ProvenanceMap`` payload (§15.1, M11b).

M11b's exit criterion is "coverage measured and reported on every golden;
partial links explicit".  This module turns the netlists a build already writes
into both halves of that: a coverage report (by carrier and by construct kind)
and the ``ProvenanceMap`` payload the GUI consumes (``app/shared/api.ts``).

Three netlists matter, and only two of them are written today:

* ``premap.json`` — the §15.1 capture point, written before ``dfflegalize`` /
  ``dfflibmap`` / ``abc``.  Every construct's ``gp_src`` attribute is intact here
  (22 nets on the traffic light).
* ``mapped.json`` — the final netlist, written after ``abc`` **and** ``clean``
  (``clean`` is Yosys's alias for ``opt_clean``).  Only the nets that survived
  ``opt_clean`` carry ``gp_src`` (16 on the traffic light).
* a **post-``abc``, pre-``opt_clean``** capture.  M0-FINDINGS §4a measures that
  ``abc`` preserves every one of the 22 net attributes and that ``opt_clean`` is
  the pass that drops six of them.  Those six are "available for free" at the
  post-``abc`` point and thrown away afterwards.  They are the **inferred**
  links: a net that demonstrably existed (its attribute is in the post-``abc``
  netlist) but whose wires were folded into the combinational cone and removed.

Confidence is therefore two-valued, exactly as ``api.ts`` pins it:

* ``exact`` — the construct's ``gp_src`` survives into the final netlist (a net
  or cell attribute that is still present after ``opt_clean``).
* ``inferred`` — the attribute survived ``abc`` but not ``opt_clean`` (it is in
  the post-``abc`` capture, absent from the final netlist).  These are the
  constructs ``abc`` folded and ``opt_clean`` dropped; they cannot be resolved
  onto specific gates (M0 §4a: "there is no bit"), so the entry names the
  dropped net and carries no cells.

A construct with **no** link at all is *absent*: it produces no entry, so the
GUI's "no link" state is distinguishable from "linked to nothing".  This is the
rule that matters most for honesty — an entry whose ``nets`` and ``cells`` are
both empty would render identically to "nothing produced", which is exactly the
false impression §15.2 forbids.

Coverage is reported **by carrier** (net vs cell) and **by construct kind**
(states, transitions, output logic, inputs, reset).  The aggregate is computed
but never presented alone: on the traffic light it is 73% of nets, and that
conceals the finding that matters — 2 of 5 transitions have an exact link, and
3 have none.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from gatepack.provenance.capture import (
    Cell,
    Netlist,
    SourceRef,
    capture_net_sources,
    capture_sources,
)

# Construct kinds, in fixed report order (§11 deliverables; the aggregate is
# deliberately second-class here).
CONSTRUCT_KINDS = ("states", "transitions", "output_logic", "inputs", "reset")

CONFIDENCE_EXACT = "exact"
CONFIDENCE_INFERRED = "inferred"


def classify_path(path: str) -> str:
    """Classify a provenance path (``gp_src`` third field) into a construct kind.

    The path is the third ``:``-separated field of a ``gp_src`` token and is
    emitted by C1 (``gatepack/frontend/verilog.py``): ``states`` for every state
    net, ``transitions[i]``, ``output_logic.<name>``, ``inputs[i]`` (synchroniser
    flops) and ``reset`` (reset synchroniser flops).  Anything else is returned
    under its own kind so it is still counted, never silently dropped.
    """
    if path == "states":
        return "states"
    if path == "reset":
        return "reset"
    if path.startswith("transitions["):
        return "transitions"
    if path.startswith("output_logic."):
        return "output_logic"
    if path.startswith("inputs["):
        return "inputs"
    if path.startswith("expressions."):
        return "expressions"
    if path.startswith("macros["):
        return "macros"
    return "other"


def construct_label(path: str, kind: str) -> str:
    """A human label for a construct path, for the "unlinked" list.

    ``output_logic.red`` is labelled ``red``; ``inputs[0]`` and
    ``transitions[2]`` keep their indexed form; ``states``/``reset`` as-is.
    """
    if kind == "output_logic":
        return path[len("output_logic.") :]
    return path


@dataclass(frozen=True)
class CarrierCoverage:
    """The exact/inferred/absent split for one provenance carrier."""

    total: int
    exact: int
    inferred: int
    absent: int

    @property
    def linked(self) -> int:
        return self.exact + self.inferred


@dataclass(frozen=True)
class KindCoverage:
    """Coverage of one construct kind, with the unlinked constructs named."""

    kind: str
    total: int
    exact: int
    inferred: int
    absent: int
    unlinked: tuple[str, ...]

    @property
    def linked(self) -> int:
        return self.exact + self.inferred


@dataclass(frozen=True)
class ProvenanceEntry:
    """One ``ProvenanceMap`` entry: a construct pointer and what it produced."""

    pointer: str
    nets: tuple[str, ...]
    cells: tuple[str, ...]
    confidence: str


@dataclass(frozen=True)
class CoverageReport:
    """The full M11b coverage picture plus the ``ProvenanceMap`` payload."""

    net: CarrierCoverage
    cell: CarrierCoverage
    by_kind: Mapping[str, KindCoverage]
    entries: tuple[ProvenanceEntry, ...]
    coverage: float

    @property
    def total_constructs(self) -> int:
        return sum(k.total for k in self.by_kind.values())

    @property
    def linked_constructs(self) -> int:
        return sum(k.linked for k in self.by_kind.values())


def measure_coverage(
    premap: Netlist,
    mapped: Netlist,
    post_abc: Netlist | None = None,
) -> CoverageReport:
    """Measure provenance coverage across ``premap`` -> ``mapped``.

    ``post_abc`` is the post-``abc``, pre-``opt_clean`` capture described in the
    module docstring.  When it is ``None`` the dropped constructs are reported
    **absent**, not inferred: without that capture there is no honest evidence
    distinguishing "``abc`` removed it" from "``opt_clean`` removed it", and a
    lower honest number is the deliverable (§M0.4a: never mark ``gp_src`` nets
    with ``keep`` to buy provenance).
    """
    premap_nets = capture_net_sources(premap)
    mapped_nets = capture_net_sources(mapped)
    post_nets = capture_net_sources(post_abc) if post_abc is not None else {}

    premap_cells = capture_sources(premap)
    mapped_cells = capture_sources(mapped)
    post_cells = capture_sources(post_abc) if post_abc is not None else {}

    net_cov = _carrier_coverage(premap_nets, mapped_nets, post_nets)
    cell_cov = _carrier_coverage(premap_cells, mapped_cells, post_cells)

    by_kind, entries = _constructs(
        premap_nets,
        mapped_nets,
        post_nets,
        premap_cells,
        mapped_cells,
        mapped,
    )

    total = sum(k.total for k in by_kind.values())
    linked = sum(k.linked for k in by_kind.values())
    coverage = (linked / total) if total else 0.0

    return CoverageReport(
        net=net_cov,
        cell=cell_cov,
        by_kind=by_kind,
        entries=entries,
        coverage=coverage,
    )


def _carrier_coverage(
    premap: Mapping[str, SourceRef],
    mapped: Mapping[str, SourceRef],
    post: Mapping[str, SourceRef],
) -> CarrierCoverage:
    exact = 0
    inferred = 0
    absent = 0
    for name in premap:
        if name in mapped:
            exact += 1
        elif name in post:
            inferred += 1
        else:
            absent += 1
    return CarrierCoverage(
        total=len(premap), exact=exact, inferred=inferred, absent=absent
    )


def _constructs(
    premap_nets: Mapping[str, SourceRef],
    mapped_nets: Mapping[str, SourceRef],
    post_nets: Mapping[str, SourceRef],
    premap_cells: Mapping[str, SourceRef],
    mapped_cells: Mapping[str, SourceRef],
    mapped: Netlist,
) -> tuple[Mapping[str, KindCoverage], tuple[ProvenanceEntry, ...]]:
    """Group every provenance path into a per-kind coverage split + entries.

    The full construct inventory is derived from the premap capture — that is
    where every construct's attribute is intact, so a construct that appears in
    the spec but produced no logic (constant-folded before capture) is honestly
    absent from the inventory rather than reported as "lost".
    """
    # path -> its premap nets/cells and its canonical SourceRef
    paths: dict[str, tuple[set[str], set[str], SourceRef | None]] = {}
    for net, ref in premap_nets.items():
        nets, cells, _ = paths.setdefault(ref.path, (set(), set(), ref))
        nets.add(net)
    for cell, ref in premap_cells.items():
        nets, cells, _ = paths.setdefault(ref.path, (set(), set(), ref))
        cells.add(cell)

    drivers = _drivers_by_net(mapped)

    counters: dict[str, list[int]] = {kind: [0, 0, 0] for kind in CONSTRUCT_KINDS}
    unlinked: dict[str, list[str]] = {kind: [] for kind in CONSTRUCT_KINDS}
    entries: list[ProvenanceEntry] = []

    for path in sorted(paths):
        premap_nets_, premap_cells_, ref = paths[path]
        kind = classify_path(path)
        tally = counters.setdefault(kind, [0, 0, 0])
        unl = unlinked.setdefault(kind, [])

        exact_nets = {n for n in premap_nets_ if n in mapped_nets}
        exact_cells = {c for c in premap_cells_ if c in mapped_cells}
        dropped_nets = {
            n for n in premap_nets_ if n not in mapped_nets and n in post_nets
        }

        tally[0] += 1  # total
        if exact_nets or exact_cells:
            tally[1] += 1  # exact
            cells = sorted(
                {drivers[n] for n in exact_nets if n in drivers} | exact_cells
            )
            entries.append(
                ProvenanceEntry(
                    pointer=ref.raw if ref is not None else path,
                    nets=tuple(sorted(exact_nets)),
                    cells=tuple(cells),
                    confidence=CONFIDENCE_EXACT,
                )
            )
        elif dropped_nets:
            tally[2] += 1  # inferred
            entries.append(
                ProvenanceEntry(
                    pointer=ref.raw if ref is not None else path,
                    nets=tuple(sorted(dropped_nets)),
                    cells=(),
                    confidence=CONFIDENCE_INFERRED,
                )
            )
        else:
            unl.append(construct_label(path, kind))  # absent

    by_kind = {
        kind: KindCoverage(
            kind=kind,
            total=counters[kind][0],
            exact=counters[kind][1],
            inferred=counters[kind][2],
            absent=len(unlinked.get(kind, ())),
            unlinked=tuple(sorted(unlinked.get(kind, ()))),
        )
        for kind in sorted(counters)
    }

    entries.sort(key=lambda e: e.pointer)
    return by_kind, tuple(entries)


def _drivers_by_net(netlist: Netlist) -> Mapping[str, str]:
    """Map a net to the name of the single cell driving it (output port)."""
    drivers: dict[str, str] = {}
    for name, cell in netlist.cells.items():
        for port in _output_ports(cell):
            ref = cell.connections.get(port)
            if ref is not None and ref.net:
                drivers.setdefault(ref.net, name)
    return drivers


def _output_ports(cell: Cell) -> tuple[str, ...]:
    """Output port(s) of a cell, from ``port_directions`` or a type heuristic.

    ``mapped.json`` carries no ``port_directions``, and the library cells are
    not the Yosys ``$_*`` primitives, so the fallback is by type name: a ``DFF*``
    drives ``Q``, everything else in the 74AUP library drives ``Y``.
    """
    if cell.port_directions:
        outputs = tuple(
            p for p, d in cell.port_directions.items() if d == "output"
        )
        if outputs:
            return outputs
    if "DFF" in cell.type or "DLATCH" in cell.type or "SR" in cell.type:
        return ("Q",)
    return ("Y",)


def measure_coverage_from_dir(
    build_dir: str | Path, module: str | None = None
) -> CoverageReport | None:
    """Read ``premap.json`` / ``mapped.json`` / ``post_abc.json`` and measure.

    ``post_abc.json`` is optional: when absent the dropped constructs are
    reported **absent** rather than inferred.  Returns ``None`` when the two
    required netlists are not present (an honest "not computed", never zeros).
    This is the entry point a ``gatepack provenance`` command or the report
    generator calls.
    """
    from gatepack.provenance.capture import read_netlist_json

    root = Path(build_dir)
    premap_path = root / "premap.json"
    mapped_path = root / "mapped.json"
    post_path = root / "post_abc.json"

    if not premap_path.exists() or not mapped_path.exists():
        return None

    premap = read_netlist_json(premap_path, module=module)
    mapped = read_netlist_json(mapped_path, module=module)
    post_abc = read_netlist_json(post_path, module=module) if post_path.exists() else None
    return measure_coverage(premap, mapped, post_abc=post_abc)


def explain_missing_coverage(build_dir: str | Path) -> str:
    """Why :func:`measure_coverage_from_dir` returned ``None``, in the user's terms.

    Two very different situations reach the same ``None``, and telling them
    apart matters because one of them is the user's fault and the other is not:

    * nothing has been built yet -- ``mapped.json`` is absent too; and
    * the design was built, but its flow never captured a pre-map netlist.

    An asynchronous design is the second case and always will be: it is
    synthesised straight from the flow table into a cube cover (§7.3), so there
    is no pre-map Yosys netlist for the mapped one to be compared against.
    Telling that user to "run `gatepack build` first" is simply false -- they
    just did -- and sends them round a loop that cannot terminate.  Fabricating
    a premap.json to make the number appear would be worse: coverage would read
    100% while measuring nothing.
    """
    root = Path(build_dir)
    if not (root / "mapped.json").exists():
        return (
            f"no captured netlists at {root}: run `gatepack build` first "
            "(provenance is never reported as empty when nothing was measured)"
        )
    return (
        f"no pre-map netlist at {root}: provenance measures which spec "
        "constructs survive synthesis by comparing premap.json against "
        "mapped.json, and this design was built without a pre-map stage. "
        "An asynchronous design is synthesised directly from its flow table "
        "(§7.3), so it has no pre-map netlist to compare against and its "
        "provenance coverage is not measurable rather than zero."
    )


def provenance_map_payload(report: CoverageReport) -> dict:
    """The ``ProvenanceMap`` payload, field-for-field with ``app/shared/api.ts``.

    ``entries`` holds only constructs that have a link; an absent construct is
    omitted (so the renderer's "no link" state stays distinct from "linked to
    nothing").  ``coverage`` is the fraction of constructs with at least one
    link, exact or inferred, in 0..1.
    """
    return {
        "entries": [
            {
                "pointer": entry.pointer,
                "nets": list(entry.nets),
                "cells": list(entry.cells),
                "confidence": entry.confidence,
            }
            for entry in report.entries
        ],
        "coverage": report.coverage,
    }


__all__ = [
    "CONSTRUCT_KINDS",
    "CONFIDENCE_EXACT",
    "CONFIDENCE_INFERRED",
    "CarrierCoverage",
    "CoverageReport",
    "KindCoverage",
    "ProvenanceEntry",
    "classify_path",
    "construct_label",
    "measure_coverage",
    "measure_coverage_from_dir",
    "provenance_map_payload",
]
