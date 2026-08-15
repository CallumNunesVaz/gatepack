"""Tests for provenance forward-matching (§15.1).

Synthetic pre/post netlist pairs exercise every matching shape the design calls
out: net-attribute carriers, cell-attribute (sequential) carriers, cone-signature
matching, merged cells, duplicated cells, deleted cells, renamed cells, the
sequential name fallback, and the per-carrier coverage breakdown.  The matcher
operates on JSON only — no Yosys involved.
"""

from __future__ import annotations

import json

from gatepack.provenance import (
    match_netlists,
    parse_netlist_json,
)
from gatepack.provenance.match import Link, MatchResult

from tests.unit.helpers import netlist_json

LIB = {"INV": "!A", "AND2": "A&B", "NAND2": "!(A&B)", "OR2": "A|B", "XOR2": "A^B"}
FLOPS = {"DFF", "DFF_R"}


def _match(premap_data, mapped_data, **kwargs):
    return match_netlists(
        parse_netlist_json(premap_data),
        parse_netlist_json(mapped_data),
        library_functions=LIB,
        flop_types=FLOPS,
        **kwargs,
    )


def _links_by_kind(result: MatchResult, kind: str) -> list[Link]:
    return [link for link in result.links if link.kind == kind]


# --- net-attribute carrier (primary, combinational) --------------------------


def test_net_attribute_matches_combinational():
    # The mapped net `y` survives abc (carries gp_src), so the mapped AND2 is
    # traced by net provenance — no structural match needed, and the premap AND
    # is left unmatched on its own side.
    premap = netlist_json(
        inputs=("a", "b"),
        outputs=("y",),
        cells=(
            {"name": "g1", "type": "$_AND_", "connections": {"A": "a", "B": "b", "Y": "y"}},
        ),
        net_sources={"y": "d.yaml:5:expressions.f"},
    )
    mapped = netlist_json(
        inputs=("a", "b"),
        outputs=("y",),
        cells=(
            {"name": "and1", "type": "AND2", "connections": {"A": "a", "B": "b", "Y": "y"}},
        ),
        net_sources={"y": "d.yaml:5:expressions.f"},
    )
    result = _match(premap, mapped)
    links = _links_by_kind(result, "net_attribute")
    assert len(links) == 1
    assert links[0].mapped_cells == ("and1",)
    assert links[0].premap_cells == ()
    assert links[0].confidence == "high"
    assert links[0].source is not None
    assert links[0].source.path == "expressions.f"
    # net is primary: no cone link is produced for this cell
    assert _links_by_kind(result, "one_to_one") == []
    assert result.unmatched_premap == ("g1",)
    assert result.coverage_by_carrier["net_attribute"] == 100.0
    assert result.coverage_by_carrier["cone_signature"] == 0.0


# --- sequential carrier (cell attribute, exact; name fallback) ---------------


def test_sequential_attribute_direct():
    # dfflibmap preserves the flop's cell attribute, so the mapped flop's own
    # gp_src is read directly — exact, not heuristic.
    premap = netlist_json(
        inputs=("clk", "din"),
        outputs=("q",),
        cells=(
            {"name": "state_A", "type": "$_DFF_P_",
             "connections": {"D": "din", "CK": "clk", "Q": "q"},
             "gp_src": "d.yaml:9:states"},
        ),
    )
    mapped = netlist_json(
        inputs=("clk", "din"),
        outputs=("q",),
        cells=(
            {"name": "state_A", "type": "DFF",
             "connections": {"D": "din", "CK": "clk", "Q": "q"},
             "gp_src": "d.yaml:9:states"},
        ),
    )
    result = _match(premap, mapped)
    links = _links_by_kind(result, "sequential")
    assert len(links) == 1
    assert links[0].premap_cells == ("state_A",)
    assert links[0].mapped_cells == ("state_A",)
    assert links[0].confidence == "high"
    assert links[0].source is not None
    assert links[0].source.path == "states"
    assert result.coverage_by_carrier["cell_attribute"] == 100.0


def test_sequential_name_fallback_without_attribute():
    # Attribute absent on the mapped flop -> name matching is the fallback,
    # at lower confidence.
    premap = netlist_json(
        inputs=("clk", "din"),
        outputs=("q",),
        cells=(
            {"name": "state_A", "type": "$_DFF_P_",
             "connections": {"D": "din", "CK": "clk", "Q": "q"},
             "gp_src": "d.yaml:9:states"},
        ),
    )
    mapped = netlist_json(
        inputs=("clk", "din"),
        outputs=("q",),
        cells=(
            {"name": "state_A", "type": "DFF",
             "connections": {"D": "din", "CK": "clk", "Q": "q"}},
        ),
    )
    result = _match(premap, mapped)
    links = _links_by_kind(result, "sequential_by_name")
    assert len(links) == 1
    assert links[0].confidence == "medium"
    assert links[0].source is not None
    assert links[0].source.path == "states"
    assert result.coverage_by_carrier["sequential_name"] == 100.0


def test_sequential_unmatched_without_attribute_or_name():
    # A mapped flop with no attribute and no same-named premap flop is unmatched.
    premap = netlist_json(
        inputs=("clk", "din"),
        outputs=("q",),
        cells=(
            {"name": "other", "type": "$_DFF_P_",
             "connections": {"D": "din", "CK": "clk", "Q": "q"}},
        ),
    )
    mapped = netlist_json(
        inputs=("clk", "din"),
        outputs=("q",),
        cells=(
            {"name": "state_A", "type": "DFF",
             "connections": {"D": "din", "CK": "clk", "Q": "q"}},
        ),
    )
    result = _match(premap, mapped)
    assert result.unmatched_mapped == ("state_A",)
    assert result.coverage_by_carrier["unmatched"] == 100.0


# --- cone-signature carrier (secondary, combinational) -----------------------


def test_one_to_one_rename():
    # The mapped net `y` lost its gp_src (optimised away), so the mapped XOR2 is
    # traced structurally to the premap XOR; source comes from the premap net.
    premap = netlist_json(
        inputs=("a", "b"),
        outputs=("y",),
        cells=(
            {"name": "x1", "type": "$_XOR_", "connections": {"A": "a", "B": "b", "Y": "y"}},
        ),
        net_sources={"y": "d.yaml:7:output_logic.y"},
    )
    mapped = netlist_json(
        inputs=("a", "b"),
        outputs=("y",),
        cells=(
            {"name": "g99", "type": "XOR2", "connections": {"A": "a", "B": "b", "Y": "y"}},
        ),
    )
    result = _match(premap, mapped)
    links = _links_by_kind(result, "one_to_one")
    assert len(links) == 1
    assert links[0].premap_cells == ("x1",)
    assert links[0].mapped_cells == ("g99",)
    assert links[0].confidence == "high"
    assert links[0].source is not None
    assert links[0].source.path == "output_logic.y"
    assert result.coverage_by_carrier["cone_signature"] == 100.0


def test_absorption_not_plus_and_to_nand():
    # $_NOT_($_AND_(a,b)) in premap becomes a single NAND2 in mapped.  The NOT's
    # output is the surviving function; the AND is absorbed and goes unmatched.
    premap = netlist_json(
        inputs=("a", "b"),
        outputs=("y",),
        cells=(
            {"name": "g1", "type": "$_AND_", "connections": {"A": "a", "B": "b", "Y": "w1"}},
            {"name": "g2", "type": "$_NOT_", "connections": {"A": "w1", "Y": "y"}},
        ),
        net_sources={"w1": "d.yaml:5:expressions.f", "y": "d.yaml:6:output_logic.y"},
    )
    mapped = netlist_json(
        inputs=("a", "b"),
        outputs=("y",),
        cells=(
            {"name": "n1", "type": "NAND2", "connections": {"A": "a", "B": "b", "Y": "y"}},
        ),
    )
    result = _match(premap, mapped)
    links = _links_by_kind(result, "one_to_one")
    assert [(l.premap_cells, l.mapped_cells) for l in links] == [(("g2",), ("n1",))]
    assert result.unmatched_premap == ("g1",)
    assert result.coverage_by_carrier["cone_signature"] == 100.0


def test_merged_cells():
    # Two identical premap inverters collapse to one mapped inverter.
    premap = netlist_json(
        inputs=("a",),
        outputs=("y1", "y2"),
        cells=(
            {"name": "n1", "type": "$_NOT_", "connections": {"A": "a", "Y": "y1"}},
            {"name": "n2", "type": "$_NOT_", "connections": {"A": "a", "Y": "y2"}},
        ),
        net_sources={"y1": "d.yaml:3:inputs[0]", "y2": "d.yaml:4:inputs[1]"},
    )
    mapped = netlist_json(
        inputs=("a",),
        outputs=("y1",),
        cells=(
            {"name": "inv", "type": "INV", "connections": {"A": "a", "Y": "y1"}},
        ),
    )
    result = _match(premap, mapped)
    links = _links_by_kind(result, "merged")
    assert len(links) == 1
    assert set(links[0].premap_cells) == {"n1", "n2"}
    assert links[0].mapped_cells == ("inv",)
    assert links[0].confidence == "medium"
    assert links[0].source is not None
    assert result.coverage_by_carrier["cone_signature"] == 100.0


def test_duplicated_cells():
    # One premap AND is duplicated into two mapped ANDs (fanout).
    premap = netlist_json(
        inputs=("a", "b"),
        outputs=("y", "y2"),
        cells=(
            {"name": "g1", "type": "$_AND_", "connections": {"A": "a", "B": "b", "Y": "y"}},
        ),
        net_sources={"y": "d.yaml:5:expressions.f"},
    )
    mapped = netlist_json(
        inputs=("a", "b"),
        outputs=("y", "y2"),
        cells=(
            {"name": "and1", "type": "AND2", "connections": {"A": "a", "B": "b", "Y": "y"}},
            {"name": "and2", "type": "AND2", "connections": {"A": "a", "B": "b", "Y": "y2"}},
        ),
    )
    result = _match(premap, mapped)
    links = _links_by_kind(result, "duplicated")
    assert len(links) == 1
    assert links[0].premap_cells == ("g1",)
    assert set(links[0].mapped_cells) == {"and1", "and2"}
    assert links[0].confidence == "medium"


def test_deleted_cells():
    # The OR gate is dropped from the mapped netlist (absorbed/removed); it is
    # reported unmatched on the premap side rather than silently paired.
    premap = netlist_json(
        inputs=("a", "b"),
        outputs=("y", "y2"),
        cells=(
            {"name": "g1", "type": "$_AND_", "connections": {"A": "a", "B": "b", "Y": "y"}},
            {"name": "extra", "type": "$_OR_", "connections": {"A": "a", "B": "b", "Y": "y2"}},
        ),
        net_sources={"y": "d.yaml:5:expressions.f", "y2": "d.yaml:6:expressions.g"},
    )
    mapped = netlist_json(
        inputs=("a", "b"),
        outputs=("y",),
        cells=(
            {"name": "and1", "type": "AND2", "connections": {"A": "a", "B": "b", "Y": "y"}},
        ),
    )
    result = _match(premap, mapped)
    assert result.unmatched_premap == ("extra",)
    assert result.unmatched_mapped == ()
    assert result.coverage_by_carrier["cone_signature"] == 100.0


def test_unmatched_mapped_cell_lowers_coverage():
    # A mapped cell with no premap counterpart is untraceable and lands in the
    # unmatched carrier of the §18 breakdown.
    premap = netlist_json(
        inputs=("a", "b"),
        outputs=("y",),
        cells=(
            {"name": "g1", "type": "$_AND_", "connections": {"A": "a", "B": "b", "Y": "y"}},
        ),
        net_sources={"y": "d.yaml:5:expressions.f"},
    )
    mapped = netlist_json(
        inputs=("a", "b"),
        outputs=("y", "w"),
        cells=(
            {"name": "and1", "type": "AND2", "connections": {"A": "a", "B": "b", "Y": "y"}},
            {"name": "nand1", "type": "NAND2", "connections": {"A": "a", "B": "b", "Y": "w"}},
        ),
    )
    result = _match(premap, mapped)
    assert result.unmatched_mapped == ("nand1",)
    assert result.total_mapped == 2
    assert result.matched_mapped == 1
    assert result.traceable_mapped == 1
    assert result.coverage_by_carrier["cone_signature"] == 50.0
    assert result.coverage_by_carrier["unmatched"] == 50.0


def test_many_to_many_is_low_confidence():
    # Two identical premap functions and two identical mapped functions: the
    # correspondence is ambiguous, so it must be labelled many-to-many / low.
    premap = netlist_json(
        inputs=("a",),
        outputs=("y1", "y2"),
        cells=(
            {"name": "n1", "type": "$_NOT_", "connections": {"A": "a", "Y": "y1"}},
            {"name": "n2", "type": "$_NOT_", "connections": {"A": "a", "Y": "y2"}},
        ),
        net_sources={"y1": "d.yaml:3:inputs[0]", "y2": "d.yaml:4:inputs[1]"},
    )
    mapped = netlist_json(
        inputs=("a",),
        outputs=("y1", "y2"),
        cells=(
            {"name": "i1", "type": "INV", "connections": {"A": "a", "Y": "y1"}},
            {"name": "i2", "type": "INV", "connections": {"A": "a", "Y": "y2"}},
        ),
    )
    result = _match(premap, mapped)
    links = _links_by_kind(result, "many_to_many")
    assert len(links) == 1
    assert links[0].confidence == "low"
    assert set(links[0].premap_cells) == {"n1", "n2"}
    assert set(links[0].mapped_cells) == {"i1", "i2"}


def test_constant_tie_matches_inverter():
    # A NAND2 with one input tied to 1 computes ~A, matching a premap NOT.
    premap = netlist_json(
        inputs=("a",),
        outputs=("y",),
        cells=(
            {"name": "n1", "type": "$_NOT_", "connections": {"A": "a", "Y": "y"}},
        ),
        net_sources={"y": "d.yaml:3:inputs[0]"},
    )
    mapped = netlist_json(
        inputs=("a",),
        outputs=("y",),
        cells=(
            {"name": "tied", "type": "NAND2", "connections": {"A": "a", "B": "1", "Y": "y"}},
        ),
    )
    result = _match(premap, mapped)
    links = _links_by_kind(result, "one_to_one")
    assert [(l.premap_cells, l.mapped_cells) for l in links] == [(("n1",), ("tied",))]
    assert result.coverage_by_carrier["cone_signature"] == 100.0


def test_max_support_leaves_cell_unmatched():
    # A cone wider than max_support is not signed and must be reported
    # unmatched, never guessed at.
    premap = netlist_json(
        inputs=("a", "b", "c"),
        outputs=("y",),
        cells=(
            {"name": "g1", "type": "$_AND_", "connections": {"A": "a", "B": "b", "Y": "w"}},
            {"name": "g2", "type": "$_AND_", "connections": {"A": "w", "B": "c", "Y": "y"}},
        ),
        net_sources={"w": "d.yaml:4:expressions.g", "y": "d.yaml:5:expressions.f"},
    )
    mapped = netlist_json(
        inputs=("a", "b", "c"),
        outputs=("y",),
        cells=(
            {"name": "and1", "type": "AND2", "connections": {"A": "a", "B": "b", "Y": "w"}},
            {"name": "and2", "type": "AND2", "connections": {"A": "w", "B": "c", "Y": "y"}},
        ),
    )
    result = _match(premap, mapped, max_support=2)
    # g2's cone spans a, b, c (support 3 > 2), so only g1 can be signed; g2/and2
    # are unmatched on their own sides.
    assert set(result.unmatched_premap) == {"g2"}
    assert set(result.unmatched_mapped) == {"and2"}
    assert result.coverage_by_carrier["cone_signature"] == 50.0
    assert result.coverage_by_carrier["unmatched"] == 50.0


# --- per-carrier coverage breakdown ------------------------------------------


def test_coverage_broken_down_by_carrier():
    # One cell each: net attribute, cell attribute (sequential), cone signature,
    # and unmatched — the §18 report must show them separately.
    premap = netlist_json(
        inputs=("a", "b", "clk", "din"),
        outputs=("y", "out_or", "q"),
        cells=(
            {"name": "g1", "type": "$_AND_", "connections": {"A": "a", "B": "b", "Y": "y"}},
            {"name": "g2", "type": "$_OR_", "connections": {"A": "a", "B": "b", "Y": "out_or"}},
            {"name": "state_A", "type": "$_DFF_P_",
             "connections": {"D": "din", "CK": "clk", "Q": "q"},
             "gp_src": "d.yaml:9:states"},
        ),
        net_sources={"y": "d.yaml:5:expressions.f", "out_or": "d.yaml:6:expressions.g"},
    )
    mapped = netlist_json(
        inputs=("a", "b", "clk", "din"),
        outputs=("y", "out_or", "q"),
        cells=(
            {"name": "and1", "type": "AND2", "connections": {"A": "a", "B": "b", "Y": "y"}},
            {"name": "or1", "type": "OR2", "connections": {"A": "a", "B": "b", "Y": "out_or"}},
            {"name": "state_A", "type": "DFF",
             "connections": {"D": "din", "CK": "clk", "Q": "q"},
             "gp_src": "d.yaml:9:states"},
            {"name": "extra", "type": "XOR2", "connections": {"A": "a", "B": "b", "Y": "w"}},
        ),
        net_sources={"out_or": "d.yaml:6:expressions.g"},
    )
    result = _match(premap, mapped)

    assert result.total_mapped == 4
    assert result.matched_mapped == 3
    assert result.traceable_mapped == 3

    counts = result.carrier_counts
    assert counts["net_attribute"] == 1      # or1 (net out_or survived)
    assert counts["cell_attribute"] == 1     # state_A (cell attribute)
    assert counts["cone_signature"] == 1     # and1 (net y optimised away)
    assert counts["unmatched"] == 1          # extra (XOR2, no counterpart)

    cov = result.coverage_by_carrier
    assert cov["net_attribute"] == 25.0
    assert cov["cell_attribute"] == 25.0
    assert cov["cone_signature"] == 25.0
    assert cov["unmatched"] == 25.0


def test_as_dict_is_deterministic_and_serializable():
    premap = netlist_json(
        inputs=("a",),
        outputs=("y",),
        cells=(
            {"name": "n1", "type": "$_NOT_", "connections": {"A": "a", "Y": "y"}},
        ),
        net_sources={"y": "d.yaml:3:inputs[0]"},
    )
    mapped = netlist_json(
        inputs=("a",),
        outputs=("y",),
        cells=(
            {"name": "i1", "type": "INV", "connections": {"A": "a", "Y": "y"}},
        ),
    )
    result = _match(premap, mapped)
    d1 = json.dumps(result.as_dict(), sort_keys=True)
    d2 = json.dumps(_match(premap, mapped).as_dict(), sort_keys=True)
    assert d1 == d2
    assert '"net_attribute"' in d1
    assert '"coverage_by_carrier"' in d1
