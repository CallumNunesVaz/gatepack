"""Tests for the C6 emitters (BOM, refdes, KiCad netlist)."""

from __future__ import annotations

from gatepack.emit.bom import emit_bom
from gatepack.emit.kicad import emit_netlist
from gatepack.emit.refdes import assign_refdes, package_id, refdes_delta, refdes_map
from gatepack.netlist import stable_cell_names
from gatepack.pack.packer import PackerConfig, pack

from .cells import cell, netlist, part


def _nor(gpp: int = 1, area: float = 1.0, suffix: str | None = None):
    return part(
        "NOR2" if gpp == 1 else "NOR2x2",
        function="!(A|B)",
        inputs=2,
        gates_per_pkg=gpp,
        area=area,
        part_suffix=suffix,
    )


def test_bom_deduplicates_configurable_gate_suffix():
    # two configurable-gate configurations, distinct cells, same part_suffix
    cfg_a = part("INV_CFG", function="!A", inputs=1, part_suffix="1G57")
    cfg_b = part("NAND2_CFG", function="!(A&B)", inputs=2, part_suffix="1G57")
    cells = [
        cell("g0", cfg_a, {"A": "a", "Y": "n0"}),
        cell("g1", cfg_b, {"A": "a", "B": "b", "Y": "n1"}),
    ]
    result = pack(cells, [cfg_a, cfg_b])
    assigned = assign_refdes(result.packed)
    bom = emit_bom(assigned)
    # exactly one data row for part number 74AUP1G57, quantity 2
    lines = [l for l in bom.splitlines() if l.startswith("74AUP1G57")]
    assert len(lines) == 1
    assert lines[0].split(",")[4] == "2"


def test_bom_columns_and_sorted_refdes():
    nor = _nor()
    cells = [cell(f"g{i}", nor, {"A": "a", "B": "b", "Y": f"n{i}"}) for i in range(3)]
    result = pack(cells, [nor])
    assigned = assign_refdes(result.packed)
    bom = emit_bom(assigned)
    header = bom.splitlines()[0].split(",")
    assert header == [
        "part_number", "manufacturers", "equivalents", "package",
        "quantity", "refdes", "tier", "unit_price", "unverified",
    ]
    data = bom.splitlines()[1]
    assert data.startswith("74AUPNOR2")
    # refdes sorted: U1;U2;U3
    assert data.split(",")[5] == "U1;U2;U3"


def test_refdes_assignment_sorted_and_stable():
    nor = _nor()
    cells = [cell(f"g{i}", nor, {"A": "a", "B": "b", "Y": f"n{i}"}) for i in range(3)]
    result = pack(cells, [nor])
    a1 = assign_refdes(result.packed)
    a2 = assign_refdes(result.packed)
    assert [ref for ref, _ in a1] == [ref for ref, _ in a2] == ["U1", "U2", "U3"]


def test_refdes_delta_reports_renumbering():
    prev = {"A": "U1", "B": "U2"}
    curr = {"A": "U2", "C": "U1"}
    d = refdes_delta(prev, curr)
    assert d.added == ("C",)
    assert d.removed == ("B",)
    assert d.renumbered == (("A", "U1", "U2"),)
    assert d.unchanged == 0


def test_kicad_netlist_rails_and_tieoffs():
    nor = _nor()
    # a NOR2 with one input tied to 0 (GND) and the other connected
    cells = [cell("g0", nor, {"A": "0", "B": "sig", "Y": "out"})]
    names = stable_cell_names(netlist("top", cells, inputs=("sig",), outputs=("out",)))
    result = pack(cells, [nor], stable_names=names)
    assigned = assign_refdes(result.packed)
    text = emit_netlist(netlist("top", cells, inputs=("sig",), outputs=("out",)), assigned, names)
    # constant "0" becomes a GND rail node
    assert '"GND"' in text
    assert '"sig"' in text
    # no timestamps
    assert "date" not in text
    # no_connects present (empty section)
    assert "no_connects" in text


def test_kicad_netlist_no_connect_flags():
    inv = part("INV", function="!A", inputs=1)
    cells = [cell("g0", inv, {"Y": "out"})]  # input A genuinely unconnected
    names = stable_cell_names(netlist("top", cells, outputs=("out",)))
    result = pack(cells, [inv], stable_names=names)
    assigned = assign_refdes(result.packed)
    text = emit_netlist(netlist("top", cells, outputs=("out",)), assigned, names)
    assert "no_connect" in text
    # the unconnected input pin is flagged, not tied to a rail
    assert '"A"' not in text.split("(nets")[1]


def test_kicad_netlist_spare_gate_tieoff():
    nor2 = _nor(gpp=2)
    cells = [cell("g0", nor2, {"A": "a", "B": "b", "Y": "n0"})]
    names = stable_cell_names(netlist("top", cells, inputs=("a", "b"), outputs=("n0",)))
    result = pack(cells, [nor2], stable_names=names)
    assigned = assign_refdes(result.packed)
    text = emit_netlist(netlist("top", cells, inputs=("a", "b"), outputs=("n0",)), assigned, names)
    # the spare gate's inputs tie to GND (rail), its output is a no_connect
    assert "no_connect" in text
    assert '"GND"' in text


def test_kicad_netlist_s_cell_has_no_function():
    s = part("SUPERVISOR", tier="S", function=None, inputs=1, part_suffix="TPS3839", family="-")
    cells = [cell("reset_s", s, {"RESET": "rst_n"})]
    names = stable_cell_names(netlist("top", cells, outputs=("rst_n",)))
    result = pack(cells, [s], stable_names=names)
    assigned = assign_refdes(result.packed)
    text = emit_netlist(netlist("top", cells, outputs=("rst_n",)), assigned, names)
    assert "TPS3839" in text
    # S-cell has a pin table but no boolean function
    assert "function" not in text


def test_kicad_netlist_deterministic():
    nor = _nor()
    cells = [cell(f"g{i}", nor, {"A": "a", "B": "b", "Y": f"n{i}"}) for i in range(3)]
    names = stable_cell_names(netlist("top", cells, inputs=("a", "b"), outputs=tuple(f"n{i}" for i in range(3))))
    result = pack(cells, [nor], stable_names=names)
    assigned = assign_refdes(result.packed)
    t1 = emit_netlist(netlist("top", cells, inputs=("a", "b"), outputs=tuple(f"n{i}" for i in range(3))), assigned, names)
    t2 = emit_netlist(netlist("top", cells, inputs=("a", "b"), outputs=tuple(f"n{i}" for i in range(3))), assigned, names)
    assert t1 == t2


def test_refdes_map_roundtrip():
    nor = _nor()
    cells = [cell(f"g{i}", nor, {"A": "a", "B": "b", "Y": f"n{i}"}) for i in range(2)]
    result = pack(cells, [nor])
    assigned = assign_refdes(result.packed)
    m = refdes_map(assigned)
    assert set(m.values()) == {"U1", "U2"}
    assert all(package_id(g) in m for _, g in assigned)
