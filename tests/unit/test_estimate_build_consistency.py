"""`estimate`'s package count vs. `build`'s actual package count (§6, §C5).

The §6 viability verdict is only as good as the number it classifies.
``estimate``'s ``packageCount`` is the *mapped cell* count (one per gate), while
``build``'s is the *packed* package count.  The two diverge the moment the
library offers a multi-gate part, because ``estimate`` never runs the packer.

The task's failure mode: a verdict that says "green, ~18 packages" for a design
that builds to 30 is worse than no verdict, because someone will plan a board
around it.  These tests pin the divergence so a future ``estimate`` that models
multi-gate packing flips them (and then they become the agreement check they
were meant to be).
"""

from __future__ import annotations

import json
from pathlib import Path

from gatepack.estimate import _count_mapped_cells
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


def test_estimate_package_count_counts_cells_not_packages(tmp_path):
    """Three NOR2 gates pack to two packages of a 2-gate part — estimate says 3."""
    mapped = _mapped_json(tmp_path / "mapped.json")
    nor2 = part("NOR2", function="!(A|B)", inputs=2, gates_per_pkg=2, part_suffix="2G02")

    cell_count = _count_mapped_cells(mapped)
    assert cell_count == 3  # what `estimate --json` reports as packageCount

    netlist = resolve_parts(parse_mapped_json(mapped.read_text()), [nor2])
    packed = pack(netlist.cells, [nor2]).packed_stats.package_count
    assert packed == 2  # what `build --json` reports as packageCount

    # The finding: estimate's "package count" is the gate count, so it over-reports
    # once any part holds more than one gate.  This is not a hypothetical: the
    # showcase maps 23 cells that pack to 20 packages.
    assert cell_count != packed


def test_estimate_package_count_equals_packages_only_for_single_gate_parts(tmp_path):
    """With a one-gate-per-package library the two counts coincide (and always
    did — which is why the divergence stayed hidden until M9)."""
    mapped = _mapped_json(tmp_path / "mapped.json")
    nor2 = part("NOR2", function="!(A|B)", inputs=2, gates_per_pkg=1)

    cell_count = _count_mapped_cells(mapped)
    netlist = resolve_parts(parse_mapped_json(mapped.read_text()), [nor2])
    packed = pack(netlist.cells, [nor2]).packed_stats.package_count

    assert cell_count == 3
    assert packed == 3
    assert cell_count == packed
