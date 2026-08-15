"""S-cell definitions and parameter checks (§9.5).

S-cells appear in the BOM and netlist but carry no logic function.  ``gatepack``
selects them and checks their declared parameters against the design; it never
designs or optimises them (§1.2).

v0.1.0 scope (§23.2): only the ``SUPERVISOR`` (power-on reset).  The two checks
§9.5 says "fall out for free" live here:

* **every flop is reset-connected** — a discrete design has no internal power-on
  reset, so a flop that is not reset-connected comes up undefined and stays
  undefined;
* **asserted reset width exceeds worst-case flop reset recovery** — the
  supervisor must assert reset long enough for the slowest flop to recover.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

from gatepack.parts import Part


@dataclass(frozen=True)
class SupervisorSpec:
    """Declared parameters of the ``SUPERVISOR`` S-cell.

    Every value here is a **candidate requiring datasheet confirmation**
    (§9, R8); ``verified`` is ``False`` until a pinned datasheet backs it.
    """

    cell: str = "SUPERVISOR"
    vcc_min: float = 1.6
    vcc_max: float = 6.0
    reset_assert_min_ns: float = 200_000.0  # candidate; typical supervisor delay
    output: Literal["push_pull", "open_drain"] = "push_pull"
    verified: bool = False

    def vcc_compatible(self, project_vcc: float) -> bool:
        return self.vcc_min <= project_vcc <= self.vcc_max


# Placeholder proxy for a flop's reset recovery time, until parts.csv carries a
# real per-cell recovery column (§10.1 has none yet).  Reset recovery is on the
# order of the cell's propagation delay, so ``max(tpd_ns)`` over F-cells is a
# conservative stand-in.  This is documented as a placeholder, not design data.
def worst_flop_reset_recovery_ns(parts: Sequence[Part]) -> float | None:
    flop_tpds = [p.tpd_ns for p in parts if p.tier == "F" and p.tpd_ns is not None]
    return max(flop_tpds) if flop_tpds else None


def check_supervisor_vcc(spec: SupervisorSpec, project_vcc: float) -> str | None:
    if not spec.vcc_compatible(project_vcc):
        return (
            f"SUPERVISOR supply {spec.vcc_min}..{spec.vcc_max} V does not include "
            f"project VCC {project_vcc} V"
        )
    return None


def check_supervisor_reset_width(
    spec: SupervisorSpec, flop_recovery_ns: float | None
) -> str | None:
    """Return an error if the supervisor's assert width cannot cover the flops.

    When ``flop_recovery_ns`` is unknown (no F-cell timing data) this returns an
    explicit *unchecked* finding rather than silently passing — a check that
    cannot run must not read as a green pass (§21.5).
    """
    if flop_recovery_ns is None:
        return (
            "SUPERVISOR reset width cannot be checked: no F-cell reset-recovery "
            "timing in the library"
        )
    if spec.reset_assert_min_ns < flop_recovery_ns:
        return (
            f"SUPERVISOR asserted reset width {spec.reset_assert_min_ns:g} ns is "
            f"shorter than worst-case flop reset recovery {flop_recovery_ns:g} ns"
        )
    return None


def check_supervisor(
    spec: SupervisorSpec,
    project_vcc: float,
    flop_recovery_ns: float | None,
) -> list[str]:
    """Aggregate the SUPERVISOR parameter checks into a list of findings."""
    findings: list[str] = []
    for check in (
        check_supervisor_vcc(spec, project_vcc),
        check_supervisor_reset_width(spec, flop_recovery_ns),
    ):
        if check is not None:
            findings.append(check)
    return findings
