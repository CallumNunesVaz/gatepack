"""`estimate`'s package count vs. `build`'s actual package count (§6, §C5).

The §6 viability verdict is only as good as the number it classifies.

``estimate``'s ``packageCount`` used to be the *mapped cell* count (one per
gate) while ``build``'s was the *packed* package count, so the two diverged the
moment the library offered a multi-gate part — a verdict of "green, ~18
packages" for a design that builds to 30 is worse than no verdict, because
someone will plan a board around it.

``estimate`` now runs the same packer ``build`` does, so these tests are the
agreement check they were always meant to be.  The gate count is still exposed
as ``_count_mapped_cells``; the point of the first test is that the two are
*different numbers* and the metric reports the packed one.
"""

from __future__ import annotations

import json
from pathlib import Path

from gatepack.estimate import _count_mapped_cells, _count_packages
from gatepack.netlist import parse_mapped_json, resolve_parts
from gatepack.pack.packer import pack

from .cells import part


def _mapped_json(path: Path) -> Path:
    data = {
        "modules": {
            "t": {
                "ports": {
                    "a": {"direction": "input", "bits": [2]},
                    "b": {"direction": "input", "bits": [3]},
                    "y0": {"direction": "output", "bits": [10]},
                    "y1": {"direction": "output", "bits": [11]},
                    "y2": {"direction": "output", "bits": [12]},
                },
                "cells": {
                    "$1": {"type": "NOR2", "port_directions": {"A": "input", "B": "input", "Y": "output"},
                           "connections": {"A": [2], "B": [3], "Y": [10]}},
                    "$2": {"type": "NOR2", "port_directions": {"A": "input", "B": "input", "Y": "output"},
                           "connections": {"A": [2], "B": [3], "Y": [11]}},
                    "$3": {"type": "NOR2", "port_directions": {"A": "input", "B": "input", "Y": "output"},
                           "connections": {"A": [2], "B": [3], "Y": [12]}},
                },
                "netnames": {
                    "a": {"bits": [2]},
                    "b": {"bits": [3]},
                    "y0": {"bits": [10]},
                    "y1": {"bits": [11]},
                    "y2": {"bits": [12]},
                },
            }
        }
    }
    path.write_text(json.dumps(data))
    return path


def test_estimate_reports_packages_not_gates(tmp_path):
    """Three NOR2 gates pack to two packages of a 2-gate part — estimate says 2.

    This is the test that fails if `estimate` reverts to counting cells: the
    gate count (3) and the package count (2) are deliberately different here.
    """
    mapped = _mapped_json(tmp_path / "mapped.json")
    nor2 = part("NOR2", function="!(A|B)", inputs=2, gates_per_pkg=2, part_suffix="2G02")

    cell_count = _count_mapped_cells(mapped)
    assert cell_count == 3  # the gate count, still available and still meaningful

    netlist = resolve_parts(parse_mapped_json(mapped.read_text()), [nor2])
    build_count = pack(netlist.cells, [nor2]).packed_stats.package_count
    assert build_count == 2  # what `build --json` reports as packageCount

    # What `estimate --json` reports must be build's number, not the gate count.
    assert _count_packages(mapped, [nor2]) == build_count
    assert _count_packages(mapped, [nor2]) != cell_count


def test_estimate_and_build_agree_for_single_gate_parts(tmp_path):
    """With a one-gate-per-package library all three counts coincide — which is
    why the divergence stayed hidden until M9."""
    mapped = _mapped_json(tmp_path / "mapped.json")
    nor2 = part("NOR2", function="!(A|B)", inputs=2, gates_per_pkg=1)

    netlist = resolve_parts(parse_mapped_json(mapped.read_text()), [nor2])
    build_count = pack(netlist.cells, [nor2]).packed_stats.package_count

    assert _count_mapped_cells(mapped) == 3
    assert build_count == 3
    assert _count_packages(mapped, [nor2]) == 3


def test_estimate_package_count_is_unknown_not_wrong_when_packing_fails(tmp_path):
    """An unpackable netlist reports ``None`` (the §6 "unknown" band).

    Falling back to the gate count here would be the wrong number wearing the
    right label — precisely the failure this whole module exists to prevent.
    """
    mapped = _mapped_json(tmp_path / "mapped.json")
    # A library with no NOR2 in it: nothing in the netlist can be resolved.
    other = part("AND2", function="A&B", inputs=2, gates_per_pkg=1)

    assert _count_packages(mapped, [other]) is None
