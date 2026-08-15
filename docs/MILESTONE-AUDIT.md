# Milestone audit — exit criteria vs. reality

**Date:** 2026-08-16. Checked against the §20 exit criteria, by running things
rather than by counting tests.

The reason for auditing this way: every milestone below was merged with a full
green suite, and three of them were not actually met. A passing test count says
what the tests exercise, not what the tool does. Where a criterion says a real
tool closes, the only evidence that counts is that tool closing.

| ID | Exit criterion | Status |
|---|---|---|
| M1 | Liberty gen + `cells_sim.v`; degenerate library fails | **met** |
| M2 | `design.yaml` → reviewable Verilog with provenance; SAT guard-overlap | **met** |
| M3 | Mapped netlist; no `$_`, latch or `$mem`; `estimate` delivered | **met** |
| M4 | Sync path through the interface; async refuses cleanly | **met** |
| M5 | Equivalence closes on all goldens; exhaustive sim; mutation | **NOT MET** |
| M6 | sby discharges invariants/reachability/liveness; covers guard vacuity | **partial** |
| M8 | CNT4 + SUPERVISOR + tie-off; shared behavioural models | **met** |
| M9 | `pack_cost`; spare avoidance; deterministic; override works | **met** |
| M10 | KiCad import clean; SCOAP delta; stuck-at classification | **NOT MET** |
| M11a | Two clean builds hash-identical | **partial** |
| M11b | Provenance coverage measured and reported on every golden | **NOT MET** |
| M12 | Project opens; core invoked; §5.2 posture verified | **met** |

## M5 — not met

Running `gatepack verify` under a container with real Yosys, Icarus and sby:

```
xor2               equivalence: failed   ERROR: Can't find gold module golden.
decoder_3to8       equivalence: failed   ERROR: Can't find gold module golden.
traffic_light      equivalence: failed   +  exhaustive simulation: failed
property_violating equivalence: failed
```

Equivalence has never closed on any design — it errors out before comparing
anything. Cause and measured fix are in `M0-FINDINGS.md` §6. Three separate
defects: the `design -stash` misuse, a `traffic_light` simulation mismatch, and
mutation reporting flop mutations as "NOT DETECTED" on combinational designs
where they cannot apply (a category error that buries the one mutation that
does apply). Delegated as `deepseek/m5fix`.

`cells_sim.v` **is** generated correctly (by `liberty/sim.py`, not a static
file) — an earlier concern of mine that was unfounded.

## M6 — partial

Properties genuinely discharge: the traffic-light mutex proves under real sby
with both basecase and induction, and `property_violating` fails. But the
vacuity guard covers the property *body* rather than its antecedent, and a
mutex body is satisfied by the all-zero state — so reaching the cover proves
much less than it appears to. Liveness is still emitted as a comment rather
than a bounded check. Delegated as `deepseek/props`.

## M10 — not met

`gatepack/analysis/` contains `clock.py`, `power.py` and `cpld.py`. There is no
`scoap.py` and no `faults.py`, so §13.1 testability and §13.2 stuck-at analysis
do not exist. `api.py` emits `"scoap": []` with zeroed fault counts and an
honest comment saying so, and the report claims nothing — it under-claims
rather than fabricating, which is the right failure mode, but the criterion is
unmet. Delegated as `deepseek/analysis`.

"KiCad import clean" has never been tested by importing anything into KiCad.
That needs a human with KiCad in front of them, and should be recorded as an
unverified claim until someone does it.

## M11a — partial, and honestly scoped

`scripts/repro_check.py` passes: 5 artefacts byte-identical across two clean
builds. But it covers the **C1 outputs only** (`generated.v`, `properties.sv`,
`cells.lib`, `yosys.ys`, `manifest.json`). The mapped netlist and the BOM are
not in the comparison, and the script says so in its own docstring. The
criterion says "two clean builds", which should include the netlist.

Now tractable: the CI `toolchain` job has a container with a pinned Yosys, so
the check can be extended to `mapped.json` and `bom.csv`.

## M11b — not met

The machinery exists — `provenance/match.py` computes `coverage_by_carrier` —
but nothing reports it. No golden test measures coverage, and the generated
report has no provenance section at all. The criterion is explicitly "coverage
measured and **reported** on every golden; partial links explicit".

This matters more than a missing report section: M11b is what M16's linked
selection consumes, and the measured coverage is uneven in a way a user must be
told about — 16/22 nets on the traffic light, but only **2 of 5 transitions**
(M0-FINDINGS §4a). A UI that silently highlights nothing for 3 of 5 transitions
reads as a bug.

**Not yet delegated.** It is the obvious next piece of work.

## What changed as a result

- `Dockerfile.probe` now carries pydantic, so the CLI runs inside the image.
- CI gained a `toolchain` job that builds that image, runs
  `tests/toolchain`, verifies three goldens against real binaries, and fails if
  a toolchain test *skips* — a skip being indistinguishable from the test not
  existing.

That job is expected to fail until the M5 repair lands. That is the point of
adding it before the fix rather than after.
