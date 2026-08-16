"""C7 analysis — power (§13.3), clock/timing (§9.6), SCOAP (§13.1) and stuck-at
fault analysis (§13.2).

Every module here is a pure function over the *resolved* mapped netlist (the
Yosys ``write_json`` form, parsed by :mod:`gatepack.netlist` and resolved against
``parts.csv``), so none of it needs Yosys at analysis time.  SCOAP and fault
analysis depend on C4's exhaustive-vector idea but implement their own
enumeration here, so they run from the netlist alone (fault analysis takes the
compiled design for the data-input/state split).
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
from gatepack.analysis.faults import (
    Fault,
    FaultReport,
    VECTOR_CAP,
    analyze_faults,
    enumerate_faults,
)
from gatepack.analysis.power import (
    DynamicCurrent,
    StaticCurrent,
    dynamic_current_ua,
    spare_leakage_ua,
    static_current_by_tier,
)
from gatepack.analysis.scoap import (
    DELTA_LIMIT,
    UNOBSERVABLE,
    ScoapNet,
    ScoapReport,
    analyze_scoap,
)

__all__ = [
    "DELTA_LIMIT",
    "DynamicCurrent",
    "Fault",
    "FaultReport",
    "ScoapNet",
    "ScoapReport",
    "StaticCurrent",
    "TimingReport",
    "UNOBSERVABLE",
    "VECTOR_CAP",
    "analyze_faults",
    "analyze_scoap",
    "blockers_summary",
    "clock_fanout",
    "combinational_depth",
    "cpld_alternative_flow",
    "cumulative_tpd_ns",
    "dynamic_current_ua",
    "enumerate_faults",
    "flop_count",
    "lint_cpld",
    "lint_netlist",
    "lint_verilog",
    "spare_leakage_ua",
    "static_current_by_tier",
    "timing_analysis",
]
