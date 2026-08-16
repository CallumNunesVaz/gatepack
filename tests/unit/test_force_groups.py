"""§C13 packing overrides — `packing.force_groups` end to end.

`force_groups` had never worked. `_collect_forced` validated a group against
the **stable** cell names but looked the members up in a dict keyed by the
mapped-netlist **instance** name, so every override passed validation and then
raised `KeyError`. M9's "override works" exit criterion had never been
exercised, and the packing view built on top of it would have persisted
overrides that always failed on rebuild.

The two names are not interchangeable and the distinction matters beyond this
bug: instance names come from ABC (`$abc$148$...$154`) and are renumbered by
every synthesis, so one written into `design.yaml` would point at a different
gate the next time the design was built.
"""

from __future__ import annotations

import pytest

from gatepack.netlist import CellNames
from gatepack.pack.packer import PackerConfig, PackError, pack

from .cells import cell, part  # hand-written synthetic netlist helpers

# A dual-gate OR2 part, so a forced group of two has somewhere to go.
OR2_DUAL = part("OR2", function="A | B", gates_per_pkg=2, part_suffix="2G32")
AND2_ONE = part("AND2", function="A & B", gates_per_pkg=1, part_suffix="1G08")
PARTS = [OR2_DUAL, AND2_ONE]


def _cells():
    return [
        cell("$abc$1$inst$100", OR2_DUAL),
        cell("$abc$1$inst$101", OR2_DUAL),
        cell("$abc$1$inst$102", AND2_ONE),
    ]


def _stable():
    return CellNames({
        "$abc$1$inst$100": "OR2__aaaa",
        "$abc$1$inst$101": "OR2__bbbb",
        "$abc$1$inst$102": "AND2__cccc",
    })


def test_force_group_of_stable_names_is_honoured():
    result = pack(
        _cells(),
        PARTS,
        PackerConfig(force_groups=(("OR2__aaaa", "OR2__bbbb"),)),
        stable_names=_stable(),
    )
    # the two forced OR2 cells must land in one package
    groups = [tuple(sorted(g.cells)) for g in result.packed]
    assert ("OR2__aaaa", "OR2__bbbb") in groups, groups


def test_instance_names_are_refused_because_they_are_not_stable():
    # The renderer only sees these from `mappedNetlist()`. Accepting one would
    # silently point at a different gate after the next synthesis.
    with pytest.raises(PackError, match="unknown cell"):
        pack(
            _cells(),
            PARTS,
            PackerConfig(force_groups=(("$abc$1$inst$100", "$abc$1$inst$101"),)),
            stable_names=_stable(),
        )


def test_mixing_functions_in_one_group_is_refused():
    with pytest.raises(PackError, match="mixes functions"):
        pack(
            _cells(),
            PARTS,
            PackerConfig(force_groups=(("OR2__aaaa", "AND2__cccc"),)),
            stable_names=_stable(),
        )


def test_forced_cells_are_not_also_packed_as_free():
    # The `free` bucket used to filter with `c.name` (an INSTANCE name) against
    # a set of STABLE names, so a forced cell was always "free" and got packed
    # twice: once on its own and once as the forced group. `package_count` must
    # be 2 (one OR2 dual + one AND2), not 3.
    result = pack(
        _cells(),
        PARTS,
        PackerConfig(force_groups=(("OR2__aaaa", "OR2__bbbb"),)),
        stable_names=_stable(),
    )
    assert result.packed_stats.package_count == 2
    every = [c for g in result.packed for c in g.cells]
    assert sorted(every) == ["AND2__cccc", "OR2__aaaa", "OR2__bbbb"]
