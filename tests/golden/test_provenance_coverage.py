"""Provenance coverage on every passing golden (§18, M11b).

The criterion is "coverage measured and reported on every golden", and §20 M11b
is explicit that the number is **a floor, not a pass/fail**.  This test measures
coverage for each golden that actually synthesises and pins a floor that catches
regression, not one that certifies quality.

Why these floors (measured on the real toolchain, Yosys 0.23, and committed as
fixtures under ``tests/fixtures/provenance/``):

* **net carrier exact >= 50%.**  The measured values are 73% (traffic_light),
  83% (pelican), 100% (xor2, decoder_3to8).  The floor is deliberately well
  below the weakest real value so it does not encode "the current toolchain is
  good"; it encodes "the net-attribute spine has not collapsed".  The failure it
  catches is a change to C1 or the synthesis passes that stops net ``gp_src``
  surviving ``abc`` — the exact failure M0 §3 measured the design around.
* **output logic is fully exact.**  Every ``<name>_int`` output net survives
  ``abc`` and ``opt_clean`` on all four designs.  This is the most robust signal
  in the whole spine; 0/0 is treated as "not applicable" only for a design with
  no outputs, which none of these are.
* **at least one exact transition** on any multi-transition design, and the
  traffic-light figure is pinned exactly (2 exact, 3 absent, named) because that
  specific unevenness is the M0 §4a finding the report must surface.

The fixture netlists are real ``write_json`` output from the pinned container,
not hand-written JSON (the hand-written cases live in
``tests/unit/test_provenance_coverage.py``).  ``tests/toolchain`` regenerates
them from a live run so the reported figure cannot drift from the real one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gatepack.provenance.capture import read_netlist_json
from gatepack.provenance.coverage import measure_coverage

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "provenance"

# The net-carrier floor, documented above.  Not the quality bar — the floor.
NET_EXACT_FLOOR = 0.50

PASSING_GOLDENS = ("traffic_light", "xor2", "decoder_3to8", "pelican")


def _measure(name: str, *, post_abc: bool):
    premap = read_netlist_json(FIXTURES / name / "premap.json")
    mapped = read_netlist_json(FIXTURES / name / "mapped.json")
    pa = (
        read_netlist_json(FIXTURES / name / "post_abc.json") if post_abc else None
    )
    return measure_coverage(premap, mapped, post_abc=pa)


@pytest.mark.parametrize("name", PASSING_GOLDENS)
def test_net_carrier_exact_meets_floor(name):
    report = _measure(name, post_abc=False)
    assert report.net.total > 0, (name, "no net-carrier constructs captured")
    ratio = report.net.exact / report.net.total
    assert ratio >= NET_EXACT_FLOOR, (
        f"{name}: net exact coverage {ratio:.0%} is below the "
        f"{NET_EXACT_FLOOR:.0%} floor"
    )


@pytest.mark.parametrize("name", PASSING_GOLDENS)
def test_output_logic_is_fully_exact(name):
    report = _measure(name, post_abc=False)
    kind = report.by_kind.get("output_logic")
    if kind is None or kind.total == 0:
        pytest.skip(f"{name}: no output logic (constant-folded?)")
    assert kind.exact == kind.total, (
        f"{name}: {kind.total - kind.exact} output(s) lost exact provenance: "
        f"{kind.unlinked}"
    )
    assert kind.absent == 0


@pytest.mark.parametrize("name", PASSING_GOLDENS)
def test_at_least_one_exact_transition(name):
    report = _measure(name, post_abc=False)
    kind = report.by_kind.get("transitions")
    if kind is None or kind.total == 0:
        pytest.skip(f"{name}: transitions constant-folded before capture")
    assert kind.exact >= 1, f"{name}: no transition has an exact link"


def test_traffic_light_transitions_finding_is_pinned():
    # The M0 §4a finding the whole milestone exists to surface: 16 of 22 nets
    # carry exact provenance, but only 2 of 5 transitions; three are named.
    report = _measure("traffic_light", post_abc=False)
    assert report.net.total == 22
    assert report.net.exact == 16
    kind = report.by_kind["transitions"]
    assert kind.total == 5
    assert kind.exact == 2
    assert kind.absent == 3
    assert kind.unlinked == (
        "transitions[0]",
        "transitions[1]",
        "transitions[3]",
    )


def test_post_abc_capture_recovers_dropped_nets_as_inferred():
    # With the post-abc capture, the six opt_clean-dropped nets are recovered as
    # *inferred* (attribute survived abc, dropped by opt_clean) — never promoted
    # to exact.
    report = _measure("traffic_light", post_abc=True)
    assert report.net.exact == 16
    assert report.net.inferred == 6
    assert report.net.absent == 0
    kind = report.by_kind["transitions"]
    assert kind.exact == 2
    assert kind.inferred == 3
    assert kind.absent == 0
    # every entry is exact or inferred, and no entry is present-but-empty
    for entry in report.entries:
        assert entry.confidence in ("exact", "inferred")
        assert entry.nets or entry.cells
