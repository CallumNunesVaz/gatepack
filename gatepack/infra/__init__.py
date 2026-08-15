"""S-cells and infrastructure (§9.5, §9.7) — definitions and parameter checks.

* :mod:`gatepack.infra.supervisor` — the ``SUPERVISOR`` S-cell and its checks.
* :mod:`gatepack.infra.reset` — "every flop is reset-connected".
* :mod:`gatepack.infra.tieoff` — tie-off identity values.
"""

from gatepack.infra.reset import check_all_flops_reset_connected, find_unreset_flops
from gatepack.infra.supervisor import (
    SupervisorSpec,
    check_supervisor,
    check_supervisor_reset_width,
    check_supervisor_vcc,
    worst_flop_reset_recovery_ns,
)
from gatepack.infra.tieoff import identity_value, identity_values

__all__ = [
    "SupervisorSpec",
    "check_all_flops_reset_connected",
    "check_supervisor",
    "check_supervisor_reset_width",
    "check_supervisor_vcc",
    "find_unreset_flops",
    "identity_value",
    "identity_values",
    "worst_flop_reset_recovery_ns",
]
