"""Provenance forward-matching (§15.1): pre-map cells -> mapped cells.

The mapped netlist's provenance arrives by two distinct carriers, and the
matching treats them very differently (docs/M0-FINDINGS.md §3–4):

* **Sequential cells carry their ``gp_src`` cell attribute through
  ``dfflibmap``.**  The flop keeps its identity and its attribute intact, so the
  mapped flop's own attribute is read directly — exact, not a heuristic.  Name
  matching against the pre-map flop is retained only as a fallback when the
  attribute is absent.

* **Combinational cells do not survive ``abc`` with a cell attribute**, but the
  attribute attached to a *net* (a ``wire`` declaration) survives ``abc``
  intact.  So the **primary** combinational signal is net provenance: a mapped
  cell is associated with source via the ``gp_src`` of the nets it drives.
  Cone-signature structural matching is the **secondary** signal, for cells
  whose nets were themselves optimised away.

This module keeps the cone-signature machinery for that secondary signal: for
every cell it computes a functional cone signature (the cell's output as a truth
table over the cone's leaf signals — primary inputs and sequential-cell
outputs), then links cells whose signatures agree.  The link is honest about
multiplicity and confidence:

* one pre-map cell <-> one mapped cell      -> ``one_to_one`` (``high``)
* several pre-map -> one mapped (ABC merge) -> ``merged``    (``medium``)
* one pre-map -> several mapped (duplicate) -> ``duplicated`` (``medium``)
* several <-> several (ambiguous)           -> ``many_to_many`` (``low``)

Where ABC restructured beyond recognition (or a cone grew past ``max_support``)
there is simply no link; the cell is reported unmatched on its own side and the
map says so rather than implying a false correspondence.

Coverage is reported **broken down by carrier** (§18): net attribute, cell
attribute (sequential), cone-signature match, and unmatched — because those
carry very different trustworthiness.  A single blended percentage would hide
exactly the thing that matters.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Callable, Collection, Mapping

from gatepack.provenance.capture import Cell, Netlist, SourceRef

MAX_SUPPORT = 20

# Coverage carriers, in fixed report order (§18).
CARRIERS = (
    "net_attribute",
    "cell_attribute",
    "cone_signature",
    "sequential_name",
    "unmatched",
)

_CONE_KINDS = frozenset({"one_to_one", "merged", "duplicated", "many_to_many"})


def _carrier(kind: str) -> str:
    if kind == "net_attribute":
        return "net_attribute"
    if kind == "sequential":
        return "cell_attribute"
    if kind == "sequential_by_name":
        return "sequential_name"
    return "cone_signature"


@dataclass(frozen=True)
class Link:
    """One provenance edge between pre-map and mapped cells."""

    kind: str
    premap_cells: tuple[str, ...]
    mapped_cells: tuple[str, ...]
    confidence: str
    source: SourceRef | None


@dataclass(frozen=True)
class MatchResult:
    """The forward-match outcome plus the §18 per-carrier coverage breakdown."""

    links: tuple[Link, ...]
    unmatched_premap: tuple[str, ...]
    unmatched_mapped: tuple[str, ...]
    total_mapped: int
    matched_mapped: int
    traceable_mapped: int
    coverage_by_carrier: Mapping[str, float]
    carrier_counts: Mapping[str, int]

    def as_dict(self) -> dict:
        return {
            "total_mapped_cells": self.total_mapped,
            "matched_mapped_cells": self.matched_mapped,
            "traceable_mapped_cells": self.traceable_mapped,
            "coverage_by_carrier": {
                carrier: {
                    "count": self.carrier_counts[carrier],
                    "percent": round(self.coverage_by_carrier[carrier], 4),
                }
                for carrier in CARRIERS
            },
            "links": [
                {
                    "kind": link.kind,
                    "confidence": link.confidence,
                    "premap_cells": list(link.premap_cells),
                    "mapped_cells": list(link.mapped_cells),
                    "source": link.source.raw if link.source is not None else None,
                }
                for link in self.links
            ],
            "unmatched_premap_cells": list(self.unmatched_premap),
            "unmatched_mapped_cells": list(self.unmatched_mapped),
        }


# --- Yosys internal single-bit primitives, evaluated for cone signatures. ---
_PREMAP_PRIMITIVES: dict[str, Callable[[Mapping[str, bool]], bool]] = {
    "$_BUF_": lambda i: i["A"],
    "$_NOT_": lambda i: not i["A"],
    "$_AND_": lambda i: i["A"] and i["B"],
    "$_NAND_": lambda i: not (i["A"] and i["B"]),
    "$_OR_": lambda i: i["A"] or i["B"],
    "$_NOR_": lambda i: not (i["A"] or i["B"]),
    "$_XOR_": lambda i: i["A"] != i["B"],
    "$_XNOR_": lambda i: not (i["A"] != i["B"]),
    "$_ANDNOT_": lambda i: i["A"] and not i["B"],
    "$_ORNOT_": lambda i: i["A"] or not i["B"],
    "$_MUX_": lambda i: i["B"] if i["S"] else i["A"],
    "$_NMUX_": lambda i: (not i["B"]) if i["S"] else (not i["A"]),
    "$_AOI3_": lambda i: not ((i["A"] and i["B"]) or i["C"]),
    "$_OAI3_": lambda i: not ((i["A"] or i["B"]) and i["C"]),
    "$_AOI4_": lambda i: not ((i["A"] and i["B"]) or (i["C"] and i["D"])),
    "$_OAI4_": lambda i: not ((i["A"] or i["B"]) and (i["C"] or i["D"])),
}

_OUTPUT_PORTS_FALLBACK: dict[str, tuple[str, ...]] = {
    "$_BUF_": ("Y",),
    "$_NOT_": ("Y",),
    "$_AND_": ("Y",),
    "$_NAND_": ("Y",),
    "$_OR_": ("Y",),
    "$_NOR_": ("Y",),
    "$_XOR_": ("Y",),
    "$_XNOR_": ("Y",),
    "$_ANDNOT_": ("Y",),
    "$_ORNOT_": ("Y",),
    "$_MUX_": ("Y",),
    "$_NMUX_": ("Y",),
    "$_AOI3_": ("Y",),
    "$_OAI3_": ("Y",),
    "$_AOI4_": ("Y",),
    "$_OAI4_": ("Y",),
    "$_DFF_P_": ("Q",),
    "$_DFF_N_": ("Q",),
    "$_DFF_PN0_": ("Q",),
    "$_DFF_PN1_": ("Q",),
    "$_DFFE_P_": ("Q",),
    "$_DFFE_N_": ("Q",),
    "$_DFFSR_PNN_": ("Q",),
    "$_DLATCH_": ("Q",),
    "$_SR_": ("Q",),
}


@dataclass(frozen=True)
class _Prepared:
    netlist: Netlist
    leaf_key: Mapping[str, tuple[str, str]]
    driver: Mapping[str, tuple[str, str]]
    evaluators: Mapping[str, Callable[[Mapping[str, bool]], bool]]
    output_ports: Mapping[str, tuple[str, ...]]


def match_netlists(
    premap: Netlist,
    mapped: Netlist,
    library_functions: Mapping[str, str] | None = None,
    flop_types: Collection[str] | None = None,
    max_support: int = MAX_SUPPORT,
) -> MatchResult:
    """Forward-match ``premap`` cells to ``mapped`` cells and report coverage.

    ``library_functions`` maps a mapped cell type to its boolean function over
    pins ``A``/``B``/``C``/... (the ``parts.csv`` ``function`` column);
    ``flop_types`` names the mapped sequential types (F-cells).  Types absent
    from both are opaque leaf boundaries, so their cones cannot be traced.
    """
    library_functions = dict(library_functions or {})
    flop_types = set(flop_types or ())

    p_prep = _prepare(premap, _PREMAP_PRIMITIVES)
    m_prep = _prepare(
        mapped,
        {t: _library_evaluator(fn) for t, fn in library_functions.items()},
    )

    premap_sources = _cell_sources(premap, p_prep)
    mapped_flop_sources = _cell_attribute_sources(mapped)

    p_sigs = _signatures(premap, p_prep, max_support)
    m_sigs = _signatures(mapped, m_prep, max_support)

    links: list[Link] = []
    matched_premap: set[str] = set()
    matched_mapped: set[str] = set()

    # 1. sequential cells: read the attribute off the mapped flop (exact),
    #    falling back to name matching only when the attribute is absent.
    seq_links, seq_premap, seq_mapped = _match_sequential(
        premap, mapped, flop_types, premap_sources, mapped_flop_sources
    )
    links += seq_links
    matched_premap |= seq_premap
    matched_mapped |= seq_mapped

    # 2. combinational cells: net provenance is the primary signal.
    net_links, net_mapped = _match_net_attributes(
        mapped, m_prep, mapped.net_sources, matched_mapped
    )
    links += net_links
    matched_mapped |= net_mapped

    # 3. combinational cells whose nets were optimised away: cone signature.
    cone_links, cone_premap, cone_mapped = _match_combinational(
        premap,
        mapped,
        p_sigs,
        m_sigs,
        premap_sources,
        skip_premap=matched_premap,
        skip_mapped=matched_mapped,
    )
    links += cone_links
    matched_premap |= cone_premap
    matched_mapped |= cone_mapped

    total = len(mapped.cells)
    carrier_by_mapped: dict[str, str] = {name: "unmatched" for name in mapped.cells}
    for link in links:
        carrier = _carrier(link.kind)
        for name in link.mapped_cells:
            carrier_by_mapped[name] = carrier

    carrier_counts = {carrier: 0 for carrier in CARRIERS}
    for name in mapped.cells:
        carrier_counts[carrier_by_mapped[name]] += 1
    coverage_by_carrier = {
        carrier: (carrier_counts[carrier] / total * 100.0) if total else 0.0
        for carrier in CARRIERS
    }

    traceable = sum(
        1
        for name in matched_mapped
        if any(name in link.mapped_cells and link.source is not None for link in links)
    )

    return MatchResult(
        links=tuple(sorted(links, key=_link_sort_key)),
        unmatched_premap=tuple(sorted(set(premap.cells) - matched_premap)),
        unmatched_mapped=tuple(sorted(set(mapped.cells) - matched_mapped)),
        total_mapped=total,
        matched_mapped=len(matched_mapped),
        traceable_mapped=traceable,
        coverage_by_carrier=coverage_by_carrier,
        carrier_counts=carrier_counts,
    )


def _library_evaluator(function: str) -> Callable[[Mapping[str, bool]], bool]:
    from gatepack.frontend import expr

    ast = expr.parse(function)

    def evaluate(inputs: Mapping[str, bool]) -> bool:
        return expr.evaluate(ast, dict(inputs))

    return evaluate


def _cell_attribute_sources(netlist: Netlist) -> dict[str, SourceRef]:
    """``cell name -> SourceRef`` from the cell's own ``gp_src`` attribute."""
    return {
        name: cell.source
        for name, cell in netlist.cells.items()
        if cell.source is not None
    }


def _cell_sources(netlist: Netlist, prep: _Prepared) -> dict[str, SourceRef]:
    """``cell name -> SourceRef``: cell attribute first, else output-net attribute.

    Sequential cells carry ``gp_src`` on the cell; combinational cells carry it
    on the net their output drives.
    """
    sources = _cell_attribute_sources(netlist)
    for name, cell in netlist.cells.items():
        if name in sources:
            continue
        for port in prep.output_ports.get(name, ()):
            ref = cell.connections.get(port)
            if ref is not None and ref.net:
                src = netlist.net_sources.get(ref.net)
                if src is not None:
                    sources[name] = src
                    break
    return sources


def _prepare(
    netlist: Netlist,
    evaluators: Mapping[str, Callable[[Mapping[str, bool]], bool]],
) -> _Prepared:
    """Build the leaf/driver maps for one side of the match.

    ``evaluators`` defines the combinational cell types of this side; every
    other cell is treated as a sequential/opaque leaf boundary.
    """
    leaf_key: dict[str, tuple[str, str]] = {}
    driver: dict[str, tuple[str, str]] = {}
    output_ports: dict[str, tuple[str, ...]] = {}

    for net in netlist.inputs:
        leaf_key.setdefault(net, ("input", net))

    for name, cell in netlist.cells.items():
        ops = _output_ports_of(cell)
        output_ports[name] = ops
        if cell.type in evaluators:
            for port in ops:
                ref = cell.connections.get(port)
                if ref is not None and ref.net and not ref.is_unknown:
                    driver[ref.net] = (name, port)
        else:
            for port in ops:
                ref = cell.connections.get(port)
                if ref is not None and ref.net:
                    leaf_key.setdefault(ref.net, ("seq", name))

    for cell in netlist.cells.values():
        for ref in cell.connections.values():
            if ref.net and ref.net not in driver and ref.net not in leaf_key:
                leaf_key[ref.net] = ("undriven", ref.net)

    return _Prepared(
        netlist=netlist,
        leaf_key=leaf_key,
        driver=driver,
        evaluators=evaluators,
        output_ports=output_ports,
    )


def _output_ports_of(cell: Cell) -> tuple[str, ...]:
    if cell.port_directions:
        outputs = tuple(p for p, d in cell.port_directions.items() if d == "output")
        if outputs:
            return outputs
    return _OUTPUT_PORTS_FALLBACK.get(cell.type, ("Y",))


def _signatures(
    netlist: Netlist, prep: _Prepared, max_support: int
) -> dict[str, tuple[tuple[str, ...], str] | None]:
    memo: dict[str, tuple[str, ...] | None] = {}
    signatures: dict[str, tuple[tuple[str, ...], str] | None] = {}
    for name, cell in netlist.cells.items():
        if cell.type not in prep.evaluators:
            signatures[name] = None
            continue
        support = _support(name, prep, memo)
        if support is None:
            signatures[name] = None
            continue
        keys = tuple(sorted(support))
        if len(keys) > max_support:
            signatures[name] = None
            continue
        signatures[name] = (keys, _truth_table(name, keys, prep))
    return signatures


def _support(
    cell_name: str,
    prep: _Prepared,
    memo: dict[str, tuple[str, ...] | None],
    visiting: set[str] | None = None,
) -> tuple[str, ...] | None:
    if cell_name in memo:
        return memo[cell_name]
    if visiting is None:
        visiting = set()
    if cell_name in visiting:
        return None
    visiting.add(cell_name)

    cell = prep.netlist.cells[cell_name]
    outputs = prep.output_ports[cell_name]
    keys: set[tuple[str, str]] = set()
    for port, ref in cell.connections.items():
        if port in outputs:
            continue
        if ref.constant is not None:
            continue
        if not ref.net:
            return None
        if ref.net in prep.leaf_key:
            keys.add(prep.leaf_key[ref.net])
        elif ref.net in prep.driver:
            sub = _support(prep.driver[ref.net][0], prep, memo, visiting)
            if sub is None:
                return None
            keys.update(sub)
        else:
            keys.add(("undriven", ref.net))

    visiting.discard(cell_name)
    memo[cell_name] = tuple(keys)
    return tuple(keys)


def _truth_table(cell_name: str, keys: tuple[str, ...], prep: _Prepared) -> str:
    cell = prep.netlist.cells[cell_name]
    out_ref = cell.connections.get(prep.output_ports[cell_name][0])
    out_net = out_ref.net if out_ref is not None else ""
    if not out_net:
        return "0"

    bits: list[str] = []
    for assignment in itertools.product((False, True), repeat=len(keys)):
        values = dict(zip(keys, assignment))
        bits.append("1" if _eval_net(out_net, values, prep, {}) else "0")
    return "".join(bits)


def _eval_net(
    net: str,
    values: Mapping[tuple[str, str], bool],
    prep: _Prepared,
    memo: dict[str, bool],
) -> bool:
    if net in memo:
        return memo[net]
    key = prep.leaf_key.get(net)
    if key is not None:
        result = values[key]
        memo[net] = result
        return result
    cell_name, _out_port = prep.driver[net]
    cell = prep.netlist.cells[cell_name]
    outputs = prep.output_ports[cell_name]
    inputs: dict[str, bool] = {}
    for port, ref in cell.connections.items():
        if port in outputs:
            continue
        if ref.constant is not None:
            inputs[port] = ref.constant
        else:
            inputs[port] = _eval_net(ref.net, values, prep, memo)
    result = prep.evaluators[cell.type](inputs)
    memo[net] = result
    return result


def _match_sequential(
    premap: Netlist,
    mapped: Netlist,
    flop_types: Collection[str],
    premap_sources: Mapping[str, SourceRef],
    mapped_flop_sources: Mapping[str, SourceRef],
) -> tuple[list[Link], set[str], set[str]]:
    """Match mapped flops by their own ``gp_src`` attribute (exact), then by name.

    ``dfflibmap`` preserves the flop's cell attribute and instance name, so the
    mapped flop carries its provenance directly.  Name matching against the
    pre-map flop is only a fallback for a flop whose attribute is absent.
    """
    premap_seq = {
        name
        for name, cell in premap.cells.items()
        if cell.type not in _PREMAP_PRIMITIVES and cell.type.startswith("$")
    }
    links: list[Link] = []
    matched_premap: set[str] = set()
    matched_mapped: set[str] = set()
    for name in sorted(mapped.cells):
        if mapped.cells[name].type not in flop_types:
            continue
        src = mapped_flop_sources.get(name)
        if src is not None:
            links.append(Link("sequential", (name,), (name,), "high", src))
            matched_mapped.add(name)
            if name in premap_seq:
                matched_premap.add(name)
        elif name in premap_seq:
            links.append(
                Link("sequential_by_name", (name,), (name,), "medium", premap_sources.get(name))
            )
            matched_mapped.add(name)
            matched_premap.add(name)
    return links, matched_premap, matched_mapped


def _match_net_attributes(
    mapped: Netlist,
    m_prep: _Prepared,
    net_sources: Mapping[str, SourceRef],
    skip_mapped: Collection[str],
) -> tuple[list[Link], set[str]]:
    """Associate combinational mapped cells with source via their nets' ``gp_src``.

    The net attribute survives ``abc``, so a mapped cell whose output net still
    carries ``gp_src`` is traced directly — the primary combinational signal.
    """
    links: list[Link] = []
    matched: set[str] = set()
    for name in sorted(mapped.cells):
        if name in skip_mapped:
            continue
        cell = mapped.cells[name]
        if cell.type not in m_prep.evaluators:
            continue
        for port in m_prep.output_ports.get(name, ()):
            ref = cell.connections.get(port)
            if ref is None or not ref.net:
                continue
            src = net_sources.get(ref.net)
            if src is not None:
                links.append(Link("net_attribute", (), (name,), "high", src))
                matched.add(name)
                break
    return links, matched


def _match_combinational(
    premap: Netlist,
    mapped: Netlist,
    p_sigs: Mapping[str, tuple[tuple[str, ...], str] | None],
    m_sigs: Mapping[str, tuple[tuple[str, ...], str] | None],
    sources: Mapping[str, SourceRef],
    skip_premap: Collection[str] = (),
    skip_mapped: Collection[str] = (),
) -> tuple[list[Link], set[str], set[str]]:
    """Structural (cone-signature) matching for cells not already traced."""
    groups: dict[tuple[tuple[str, ...], str], dict[str, list[str]]] = {}
    for name, sig in p_sigs.items():
        if sig is not None and name not in skip_premap:
            groups.setdefault(sig, {"p": [], "m": []})["p"].append(name)
    for name, sig in m_sigs.items():
        if sig is not None and name not in skip_mapped:
            groups.setdefault(sig, {"p": [], "m": []})["m"].append(name)

    links: list[Link] = []
    matched_premap: set[str] = set()
    matched_mapped: set[str] = set()
    for sig in sorted(groups, key=lambda s: (s[0], s[1])):
        p = sorted(groups[sig]["p"])
        m = sorted(groups[sig]["m"])
        if not p or not m:
            continue
        src = _pick_source(p, sources)
        if len(p) == 1 and len(m) == 1:
            links.append(Link("one_to_one", (p[0],), (m[0],), "high", src))
        elif len(p) == 1:
            links.append(Link("duplicated", (p[0],), tuple(m), "medium", src))
        elif len(m) == 1:
            links.append(Link("merged", tuple(p), (m[0],), "medium", src))
        else:
            links.append(Link("many_to_many", tuple(p), tuple(m), "low", src))
        matched_premap.update(p)
        matched_mapped.update(m)
    return links, matched_premap, matched_mapped


def _pick_source(names: list[str], sources: Mapping[str, SourceRef]) -> SourceRef | None:
    for name in names:
        if name in sources:
            return sources[name]
    return None


def _link_sort_key(link: Link) -> tuple:
    return (link.kind, link.mapped_cells, link.premap_cells)
