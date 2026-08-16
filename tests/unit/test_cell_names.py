"""The instance/stable name-space boundary (:class:`gatepack.netlist.CellNames`).

A mapped cell has two names and confusing them caused three defects in one day:

1. `pack._collect_forced` validated `force_groups` against STABLE names but
   looked members up in a dict keyed by INSTANCE names, so every override
   raised `KeyError`;
2. the report's `cell_refdes` had to reverse the instance -> stable map by hand
   because `assigned` groups hold STABLE names while the timing path holds
   INSTANCE names;
3. `BuildResult.stable_names` had to be added and exposed as `stableCellNames`
   because the renderer only sees instance names and would otherwise persist an
   override that is refused on rebuild (or points at a different gate).

`CellNames` owns both directions of the mapping and hard-errors on a name from
the wrong space, so a mix-up fails loudly instead of silently producing a wrong
answer. Each test below reproduces one of the three defects at the boundary.
"""

from __future__ import annotations

import pytest

from gatepack.build import AssembleConfig, assemble
from gatepack.netlist import CellNames
from gatepack.pack.packer import PackerConfig, PackError, pack

from .cells import cell, netlist, part

_INSTANCE_A = "$abc$148$auto$blifparse.cc:386:parse_blif$154"
_INSTANCE_B = "$abc$148$auto$blifparse.cc:386:parse_blif$155"
_STABLE_A = "OR2__3cf29954"
_STABLE_B = "INV__deadbeef"


def _names() -> CellNames:
    return CellNames({_INSTANCE_A: _STABLE_A, _INSTANCE_B: _STABLE_B})


# --- the mapping itself ------------------------------------------------------


def test_to_instance_refuses_an_instance_name():
    # Defects 1 & 2: an instance name is not a stable name. A caller that hands
    # `to_instance` an ABC node name must get a loud error, not a wrong answer.
    names = _names()
    with pytest.raises(KeyError, match="not a known stable name"):
        names.to_instance(_INSTANCE_A)


def test_to_stable_refuses_a_stable_name():
    names = _names()
    with pytest.raises(KeyError, match="not a known instance name"):
        names.to_stable(_STABLE_A)


def test_both_directions_exist_on_one_object():
    names = _names()
    assert names.to_stable(_INSTANCE_A) == _STABLE_A
    assert names.to_instance(_STABLE_A) == _INSTANCE_A
    # the instance -> stable direction is the `stableCellNames` IPC shape
    assert dict(names) == {_INSTANCE_A: _STABLE_A, _INSTANCE_B: _STABLE_B}


def test_duplicate_stable_name_is_refused():
    # two instances sharing one stable name would make the reverse lookup
    # ambiguous; refuse to build the mapping rather than pick one silently.
    with pytest.raises(ValueError, match="same stable name"):
        CellNames({"$a": "SAME__0", "$b": "SAME__0"})


# --- defect 1: force_groups resolved against stable names only ----------------


def test_force_group_rejects_instance_name():
    or2 = part("OR2", function="A | B", gates_per_pkg=2, part_suffix="2G32")
    cells = [cell(_INSTANCE_A, or2), cell(_INSTANCE_B, or2)]
    names = CellNames({_INSTANCE_A: _STABLE_A, _INSTANCE_B: _STABLE_B})
    # an instance name passed where a stable one belongs must fail loudly
    with pytest.raises(PackError, match="unknown cell"):
        pack(
            cells,
            [or2],
            PackerConfig(force_groups=((_INSTANCE_A, _INSTANCE_B),)),
            stable_names=names,
        )


# --- defect 2: the report crosses back to instance names exactly once ---------


def test_assemble_renders_worst_path_as_refdes_not_instance_names():
    # The report's timing section is built from INSTANCE names; the packing
    # groups hold STABLE names. `build.py` crosses that boundary via
    # `names.to_instance`, so the worst path renders `U1 -> U2`, not `$abc$...`.
    inv = part("INV", function="!A", inputs=1)
    cells = [
        cell(_INSTANCE_A, inv, {"A": "a", "Y": "n1"}),
        cell(_INSTANCE_B, inv, {"A": "n1", "Y": "y"}),
    ]
    nl = netlist("top", cells, inputs=("a",), outputs=("y",))
    result = assemble(nl, [inv], AssembleConfig(design_name="demo"))
    worst = [l for l in result.report.splitlines() if l.startswith("- worst path:")]
    assert worst, result.report
    assert "$abc$" not in worst[0]
    assert "U1" in worst[0] and "U2" in worst[0]


# --- defect 3: stableCellNames is instance -> stable ---------------------------


def test_build_result_stable_names_is_instance_to_stable():
    # If `stable_names` were reversed (stable -> instance), the renderer would
    # persist an override keyed by a stable name it can never see, or worse, a
    # wrong gate. The exposed map must be instance -> stable.
    inv = part("INV", function="!A", inputs=1)
    nl = netlist("top", [cell(_INSTANCE_A, inv, {"A": "a", "Y": "y"})],
                 inputs=("a",), outputs=("y",))
    result = assemble(nl, [inv], AssembleConfig(design_name="demo"))
    wire = dict(result.stable_names)
    assert set(wire) == {_INSTANCE_A}
    assert wire[_INSTANCE_A].startswith("INV__")
