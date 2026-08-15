"""C7 analysis — power (§13.3) and clock/timing (§9.6).

SCOAP testability (§13.1) and stuck-at fault analysis (§13.2) are **not** here:
they depend on C4's vector infrastructure (another milestone) and are left as a
seam in ``gatepack/analysis`` (see ``__init__.py``).  This package only delivers
the parts of C7 that do not need C4: static current by tier, spare-gate leakage,
dynamic current (flagged), combinational depth and cumulative tPD.
"""

from gatepack.analysis.clock import (
    TimingReport,
    clock_fanout,
    combinational_depth,
    cumulative_tpd_ns,
    flop_count,
    timing_analysis,
)
from gatepack.analysis.cpld import (
    blockers_summary,
    cpld_alternative_flow,
    lint_cpld,
    lint_netlist,
    lint_verilog,
)
from gatepack.analysis.power import (
    DynamicCurrent,
    StaticCurrent,
    dynamic_current_ua,
    spare_leakage_ua,
    static_current_by_tier,
)

__all__ = [
    "DynamicCurrent",
    "StaticCurrent",
    "TimingReport",
    "blockers_summary",
    "clock_fanout",
    "combinational_depth",
    "cpld_alternative_flow",
    "cumulative_tpd_ns",
    "dynamic_current_ua",
    "flop_count",
    "lint_cpld",
    "lint_netlist",
    "lint_verilog",
    "spare_leakage_ua",
    "static_current_by_tier",
    "timing_analysis",
]
