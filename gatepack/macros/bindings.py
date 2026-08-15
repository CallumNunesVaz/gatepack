"""M-cell physical bindings (§9.4).

Each M-cell has two artefacts: a hand-written behavioural Verilog model (under
``gatepack/macros/models/``) and a physical binding here — part number, package
and pinout — used by C5/C6.  The behavioural model uses logical pin names; this
binding maps them to the candidate package pin.

**All part numbers, packages and pinouts are candidates requiring datasheet
confirmation before entry into the design (§9, R8).**  ``verified`` is ``False``
for every binding in this file and must stay ``False`` until a real, pinned
datasheet document backs each value — exactly the §10.1 [R4-21] rule.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MCellBinding:
    cell: str
    part: str
    package: str
    pins: dict[str, str] = field(default_factory=dict)
    tieoffs: dict[str, str] = field(default_factory=dict)
    verified: bool = False


# CNT4 → 74LVC161.  Pin numbers are candidate values from the (unverified)
# 74xx161 pinout: CLR(1), CLK(2), D0..D3(3..6), ENP(7), LOAD(9), ENT(10),
# Q3..Q0(14..11), RCO(15).  The behavioural model exposes only CLK/RST_N/EN/Q,
# so the parallel-load and ripple-carry pins that the model does not drive are
# declared as tie-offs (tied high to disable load / enable counting).
M_CELL_BINDINGS: dict[str, MCellBinding] = {
    "CNT4": MCellBinding(
        cell="CNT4",
        part="74LVC161",
        package="SO-16",
        pins={
            "CLK": "2",
            "RST_N": "1",
            "EN": "7",
            "Q[0]": "14",
            "Q[1]": "13",
            "Q[2]": "12",
            "Q[3]": "11",
        },
        tieoffs={
            "ENT": "10",   # second count-enable input; tie high
            "LOAD_N": "9",  # synchronous parallel load; tie high (disabled)
        },
        verified=False,
    ),
}


def known_m_cells() -> tuple[str, ...]:
    return tuple(sorted(M_CELL_BINDINGS))


def get_binding(cell: str) -> MCellBinding:
    if cell not in M_CELL_BINDINGS:
        raise KeyError(f"unknown M-cell {cell!r} (known: {sorted(M_CELL_BINDINGS)})")
    return M_CELL_BINDINGS[cell]
