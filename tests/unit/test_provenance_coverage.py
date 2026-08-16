"""Unit tests for provenance coverage measurement (§15.1, M11b).

These pin the confidence model against synthetic netlists — the shape that a
real run must produce, without Yosys.  The real-run numbers are pinned by
``tests/toolchain/test_provenance_coverage.py`` and the golden fixtures in
``tests/fixtures/provenance/``.

The properties worth locking here, each because a previous milestone shipped a
status that measured nothing:

* ``exact`` means the ``gp_src`` attribute survives into the final netlist.
* ``inferred`` means the attribute survived ``abc`` but was dropped by
  ``opt_clean`` — recoverable only from the post-``abc`` capture.
* a construct with no link is *absent* (no entry), never an empty entry.
* coverage is per-construct, and the aggregate is not allowed to hide a weak
  kind (transitions at 2/5).
"""

from __future__ import annotations

from gatepack.provenance.coverage import (
    CarrierCoverage,
    classify_path,
    construct_label,
    measure_coverage,
    provenance_map_payload,
)
from gatepack.provenance.capture import parse_netlist_json

from tests.unit.helpers import netlist_json


def _premap(**kw):
    return parse_netlist_json(netlist_json(**kw))


def _mapped(**kw):
    return parse_netlist_json(netlist_json(**kw))


def test_classify_path():
    assert classify_path("states") == "states"
    assert classify_path("reset") == "reset"
    assert classify_path("transitions[3]") == "transitions"
    assert classify_path("output_logic.red") == "output_logic"
    assert classify_path("inputs[0]") == "inputs"
    assert classify_path("expressions.f") == "expressions"
    assert classify_path("weird") == "other"


def test_construct_label():
    assert construct_label("output_logic.red", "output_logic") == "red"
    assert construct_label("transitions[2]", "transitions") == "transitions[2]"
    assert construct_label("states", "states") == "states"


def test_exact_surviving_net():
    premap = _premap(
        inputs=("a",),
        outputs=("y",),
        cells=({"name": "g1", "type": "$_NOT_", "connections": {"A": "a", "Y": "y"}},),
        net_sources={"y": "d.yaml:7:output_logic.y"},
    )
    mapped = _mapped(
        inputs=("a",),
        outputs=("y",),
        cells=({"name": "i1", "type": "INV", "connections": {"A": "a", "Y": "y"}},),
        net_sources={"y": "d.yaml:7:output_logic.y"},
    )
    report = measure_coverage(premap, mapped)
    assert report.net == CarrierCoverage(total=1, exact=1, inferred=0, absent=0)
    assert report.by_kind["output_logic"].exact == 1
    assert report.by_kind["output_logic"].absent == 0
    assert report.coverage == 1.0


def test_inferred_from_post_abc_only():
    # The net survives abc (in post_abc) but opt_clean drops it, so without the
    # post-abc capture it is absent; with it, it is inferred.
    premap = _premap(
        inputs=("a",),
        outputs=("y",),
        cells=({"name": "g1", "type": "$_NOT_", "connections": {"A": "a", "Y": "t_0"}},),
        net_sources={"t_0": "d.yaml:9:transitions[0]"},
    )
    mapped = _mapped(inputs=("a",), outputs=("y",), cells=())
    post_abc = parse_netlist_json(
        netlist_json(
            inputs=("a",),
            outputs=("y",),
            cells=({"name": "i1", "type": "INV", "connections": {"A": "a", "Y": "t_0"}},),
            net_sources={"t_0": "d.yaml:9:transitions[0]"},
        )
    )

    without = measure_coverage(premap, mapped)
    assert without.net.absent == 1
    assert without.by_kind["transitions"].absent == 1
    assert without.by_kind["transitions"].unlinked == ("transitions[0]",)

    with_post = measure_coverage(premap, mapped, post_abc=post_abc)
    assert with_post.net.inferred == 1
    assert with_post.by_kind["transitions"].inferred == 1
    assert with_post.by_kind["transitions"].absent == 0


def test_absent_construct_produces_no_entry():
    premap = _premap(
        inputs=("a",),
        outputs=("y",),
        cells=({"name": "g1", "type": "$_NOT_", "connections": {"A": "a", "Y": "t_0"}},),
        net_sources={"t_0": "d.yaml:9:transitions[0]"},
    )
    mapped = _mapped(inputs=("a",), outputs=("y",), cells=())
    report = measure_coverage(premap, mapped)
    # absent -> no entry at all, so "no link" is distinguishable from
    # "linked to nothing" (an entry with empty nets and cells).
    assert report.entries == ()
    # and no entry carries empty nets *and* empty cells (never present-but-empty)
    for entry in report.entries:
        assert entry.nets or entry.cells


def test_cell_carrier_is_distinct_from_net_carrier():
    premap = _premap(
        inputs=("clk", "d"),
        outputs=("q",),
        cells=(
            {"name": "state_A", "type": "$_DFF_P_",
             "connections": {"D": "d", "CK": "clk", "Q": "q"},
             "gp_src": "d.yaml:4:states"},
        ),
    )
    mapped = _mapped(
        inputs=("clk", "d"),
        outputs=("q",),
        cells=(
            {"name": "state_A", "type": "DFF",
             "connections": {"D": "d", "CK": "clk", "Q": "q"},
             "gp_src": "d.yaml:4:states"},
        ),
    )
    report = measure_coverage(premap, mapped)
    assert report.net.total == 0
    assert report.cell == CarrierCoverage(total=1, exact=1, inferred=0, absent=0)
    assert report.by_kind["states"].exact == 1


def test_coverage_fraction_and_payload_shape():
    # 2 transitions + 1 output: one transition exact, one absent, output exact.
    premap = _premap(
        inputs=("a",),
        outputs=("y", "w"),
        cells=(
            {"name": "g1", "type": "$_NOT_", "connections": {"A": "a", "Y": "t_0"}},
            {"name": "g2", "type": "$_NOT_", "connections": {"A": "a", "Y": "y"}},
        ),
        net_sources={
            "t_0": "d.yaml:9:transitions[0]",
            "y": "d.yaml:10:output_logic.y",
            "w": "d.yaml:11:transitions[1]",
        },
    )
    mapped = _mapped(
        inputs=("a",),
        outputs=("y",),
        cells=({"name": "i1", "type": "INV", "connections": {"A": "a", "Y": "y"}},),
        net_sources={"y": "d.yaml:10:output_logic.y"},
    )
    report = measure_coverage(premap, mapped)
    # constructs: transitions[0] (absent), transitions[1] (absent), output_logic.y (exact)
    assert report.by_kind["transitions"].total == 2
    assert report.by_kind["transitions"].absent == 2
    assert report.by_kind["output_logic"].exact == 1
    assert report.total_constructs == 3
    assert report.linked_constructs == 1
    assert abs(report.coverage - 1 / 3) < 1e-9

    payload = provenance_map_payload(report)
    assert payload["coverage"] == report.coverage
    assert isinstance(payload["entries"], list)
    for entry in payload["entries"]:
        # api.ts ProvenanceMap field-for-field
        assert set(entry) == {"pointer", "nets", "cells", "confidence"}
        assert entry["confidence"] in ("exact", "inferred")
        assert isinstance(entry["nets"], list)
        assert isinstance(entry["cells"], list)


def test_exact_net_entry_resolves_driver_cell():
    premap = _premap(
        inputs=("a",),
        outputs=("y",),
        cells=({"name": "g1", "type": "$_NOT_", "connections": {"A": "a", "Y": "y"}},),
        net_sources={"y": "d.yaml:7:output_logic.y"},
    )
    mapped = _mapped(
        inputs=("a",),
        outputs=("y",),
        cells=({"name": "i1", "type": "INV", "connections": {"A": "a", "Y": "y"}},),
        net_sources={"y": "d.yaml:7:output_logic.y"},
    )
    report = measure_coverage(premap, mapped)
    (entry,) = report.entries
    assert entry.pointer == "d.yaml:7:output_logic.y"
    assert entry.nets == ("y",)
    assert entry.cells == ("i1",)
    assert entry.confidence == "exact"


def test_measure_coverage_from_dir_missing_is_none(tmp_path):
    from gatepack.provenance.coverage import measure_coverage_from_dir

    assert measure_coverage_from_dir(tmp_path) is None
