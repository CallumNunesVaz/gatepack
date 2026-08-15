"""Tests for the C5 packer (gatepack.pack.packer)."""

from __future__ import annotations

import pytest

from gatepack.pack.packer import (
    DEFAULT_SPARE_LEAKAGE_WEIGHT,
    PackError,
    PackerConfig,
    pack,
)
from gatepack.parts import Part

from .cells import cell, part


def _nor(gpp: int, area: float = 1.0, suffix: str | None = None) -> Part:
    return part(
        "NOR2" if gpp == 1 else "NOR2x2",
        function="!(A|B)",
        inputs=2,
        gates_per_pkg=gpp,
        area=area,
        part_suffix=suffix,
    )


def test_groups_by_function_not_mixed():
    nor2 = _nor(1)
    nor2x2 = _nor(2)
    nand2 = part("NAND2", function="!(A&B)", inputs=2, gates_per_pkg=2)
    cells = [
        cell("g0", nor2, {"A": "a", "B": "b", "Y": "n0"}),
        cell("g1", nor2, {"A": "a", "B": "c", "Y": "n1"}),
        cell("g2", nand2, {"A": "a", "B": "b", "Y": "n2"}),
    ]
    result = pack(cells, [nor2, nor2x2, nand2])
    assert result.packed_stats.package_count == 2
    # the two NOR2 gates share a 2G package; the NAND2 is separate
    nor_pkgs = [g for g in result.packed if g.part.tier == "G" and g.part.function == "!(A|B)"]
    nand_pkgs = [g for g in result.packed if g.part.function == "!(A&B)"]
    assert len(nor_pkgs) == 1
    assert sorted(nor_pkgs[0].cells) == ["g0", "g1"]
    assert len(nand_pkgs) == 1
    assert nand_pkgs[0].cells == ("g2",)


def test_pack_cost_formula():
    nor2 = _nor(1)
    cells = [cell(f"g{i}", nor2, {"A": "a", "B": "b", "Y": f"n{i}"}) for i in range(3)]
    result = pack(cells, [nor2], PackerConfig(spare_leakage_weight=2.0))
    s = result.packed_stats
    assert s.package_cost == 3 * 1.0
    assert s.pack_cost == s.package_cost + s.spare_count * 2.0
    # no multi-gate option -> 3 packages, 0 spares
    assert s.package_count == 3
    assert s.spare_count == 0


def test_spare_is_a_cost_not_free():
    # 2 gates: 1 x 3-slot package leaves 1 spare (cost 1.0 + 1*2.0 = 3.0);
    # 2 x 1G packages (area 0.9 each) avoid the spare (cost 1.8).
    small = _nor(1, area=0.9)
    big = part("NOR3", function="!(A|B)", inputs=2, gates_per_pkg=3, area=1.0)
    cells = [cell(f"g{i}", small, {"A": "a", "B": "b", "Y": f"n{i}"}) for i in range(2)]
    result = pack(cells, [small, big], PackerConfig(spare_leakage_weight=2.0))
    assert result.packed_stats.package_count == 2
    assert result.packed_stats.spare_count == 0
    assert result.packed_stats.pack_cost == 1.8


def test_more_packages_to_avoid_spare():
    small = _nor(1, area=0.9)
    big = part("NOR3", function="!(A|B)", inputs=2, gates_per_pkg=3, area=1.0)
    cells = [cell(f"g{i}", small, {"A": "a", "B": "b", "Y": f"n{i}"}) for i in range(2)]
    packed = pack(cells, [small, big], PackerConfig(spare_leakage_weight=2.0))
    assert packed.packed_stats.package_count == 2

    free = pack(cells, [small, big], PackerConfig(spare_leakage_weight=0.0))
    # with spares free, the single 3G package (1 spare) is chosen
    assert free.packed_stats.package_count == 1
    assert free.packed_stats.spare_count == 1


def test_reports_package_and_spare_count_separately():
    nor2 = _nor(1)
    cells = [cell(f"g{i}", nor2, {"A": "a", "B": "b", "Y": f"n{i}"}) for i in range(3)]
    s = pack(cells, [nor2]).packed_stats
    assert hasattr(s, "package_count")
    assert hasattr(s, "spare_count")
    assert hasattr(s, "pack_cost")
    assert hasattr(s, "package_cost")


def test_deterministic():
    nor2 = _nor(1)
    nor2x2 = _nor(2)
    cells = [cell(f"g{i}", nor2, {"A": "a", "B": "b", "Y": f"n{i}"}) for i in range(5)]
    r1 = pack(cells, [nor2, nor2x2])
    r2 = pack(cells, [nor2, nor2x2])
    assert r1 == r2


def test_unpacked_is_one_package_per_cell():
    nor2 = _nor(1)
    cells = [cell(f"g{i}", nor2, {"A": "a", "B": "b", "Y": f"n{i}"}) for i in range(3)]
    result = pack(cells, [nor2])
    assert result.unpacked_stats.package_count == 3
    assert all(len(g.cells) == 1 for g in result.unpacked)


def test_force_groups():
    nor2 = _nor(1)
    nor2x2 = _nor(2)
    cells = [cell(f"g{i}", nor2, {"A": "a", "B": "b", "Y": f"n{i}"}) for i in range(2)]
    result = pack(
        cells,
        [nor2, nor2x2],
        PackerConfig(force_groups=(("g0", "g1"),)),
    )
    # forced together into one 2G package, zero spares
    assert result.packed_stats.package_count == 1
    assert sorted(result.packed[0].cells) == ["g0", "g1"]


def test_force_groups_mixed_function_errors():
    nor2 = _nor(1)
    nand2 = part("NAND2", function="!(A&B)", inputs=2)
    cells = [
        cell("g0", nor2, {"A": "a", "B": "b", "Y": "n0"}),
        cell("g1", nand2, {"A": "a", "B": "b", "Y": "n1"}),
    ]
    with pytest.raises(PackError, match="mixes functions"):
        pack(cells, [nor2, nand2], PackerConfig(force_groups=(("g0", "g1"),)))


def test_force_groups_unknown_cell_errors():
    nor2 = _nor(1)
    cells = [cell("g0", nor2, {"A": "a", "B": "b", "Y": "n0"})]
    with pytest.raises(PackError, match="unknown cell"):
        pack(cells, [nor2], PackerConfig(force_groups=(("ghost",),)))


def test_unresolved_part_errors():
    from gatepack.netlist import MappedCell

    raw = MappedCell(name="g0", cell="UNKNOWN", tier="")
    with pytest.raises(PackError, match="no resolved part"):
        pack([raw], [])


def test_default_spare_weight_positive():
    assert DEFAULT_SPARE_LEAKAGE_WEIGHT > 0
