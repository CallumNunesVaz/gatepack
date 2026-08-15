"""C7 power analysis (§13.3).

Static current is summed **broken out by tier** (G/F/M/S separately) because a
single M- or S-cell can dominate a sub-µA design (§19 R9).  Spare-gate leakage
is a separate line item (§9.7).  Dynamic current is an estimate that is *always*
flagged as excluding inter-package routing capacitance — which will dominate —
and is never presented as a budget.

Electrical values (``iq_ua``) are the placeholder quantities in ``parts.csv``
and carry no temperature derating: the data model has no derating curve, so no
derating is invented here.  ``derating`` is exposed so a datasheet-derived
multiplier can be applied later without a code change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from gatepack.netlist import MappedCell, MappedNetlist
from gatepack.pack.packer import PackageGroup

_TIERS = ("G", "F", "M", "S")

# Dynamic-current assumptions.  These are explicit placeholders: the data model
# carries no output capacitance or switching-activity data, and inter-package
# routing capacitance (which dominates a discrete build) is by definition not in
# the netlist.  See the note on :func:`dynamic_current_ua`.
ASSUMED_LOAD_PF = 2.0
ASSUMED_ACTIVITY = 0.1


@dataclass(frozen=True)
class StaticCurrent:
    g_ua: float
    f_ua: float
    m_ua: float
    s_ua: float

    @property
    def by_tier(self) -> dict[str, float]:
        return {"G": self.g_ua, "F": self.f_ua, "M": self.m_ua, "S": self.s_ua}

    @property
    def total_ua(self) -> float:
        return self.g_ua + self.f_ua + self.m_ua + self.s_ua


@dataclass(frozen=True)
class DynamicCurrent:
    ua: float
    excludes_routing_capacitance: bool
    note: str


def _iq(part) -> float:
    return part.iq_ua if part.iq_ua is not None else 0.0


def static_current_by_tier(
    cells: Sequence[MappedCell], derating: float = 1.0
) -> StaticCurrent:
    """Sum datasheet ``iq_ua`` per tier, scaled by ``derating``.

    Cells with no ``iq_ua`` contribute 0 and are not a hard error (the value is
    "unknown", not "zero"); a full accounting needs every cell cited, which the
    ``lib check`` gate enforces separately.
    """
    totals = {tier: 0.0 for tier in _TIERS}
    for cell in cells:
        if cell.part is None:
            continue
        tier = cell.tier if cell.tier in _TIERS else "S"
        totals[tier] += _iq(cell.part)
    return StaticCurrent(
        g_ua=totals["G"] * derating,
        f_ua=totals["F"] * derating,
        m_ua=totals["M"] * derating,
        s_ua=totals["S"] * derating,
    )


def spare_leakage_ua(packages: Sequence[PackageGroup]) -> float:
    """Estimated spare-gate leakage penalty (§9.7): each spare slot's idle ``iq``.

    This is a coarse estimate (a floating spare gate's crowbar current is analog
    and temperature-dependent, not a fixed IQ) and is reported as a line item,
    not folded into a single number.
    """
    total = 0.0
    for group in packages:
        if group.spare > 0:
            total += group.spare * _iq(group.part)
    return total


def dynamic_current_ua(
    netlist: MappedNetlist,
    freq_hz: float,
    vcc: float,
    load_pf: float = ASSUMED_LOAD_PF,
    activity: float = ASSUMED_ACTIVITY,
) -> DynamicCurrent:
    """A *nominal* dynamic-current estimate, flagged as incomplete.

    ``I = C * V * f * activity`` summed over cells, using an assumed per-gate
    output capacitance and switching activity.  This number **excludes**
    inter-package routing capacitance, which dominates a discrete build, so it
    is an assumption, not a budget (§13.3).  It has never been validated against
    a real build.
    """
    n = len(netlist.cells)
    ua = n * (load_pf * 1e-12) * vcc * freq_hz * activity * 1e6
    note = (
        f"nominal only: assumes {load_pf:g} pF/gate output, {activity:g} activity; "
        f"excludes inter-package routing capacitance, which will dominate — not a budget"
    )
    return DynamicCurrent(ua=ua, excludes_routing_capacitance=True, note=note)
