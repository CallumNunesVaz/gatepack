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
| M9 | `pack_cost`; spare avoidance; deterministic; override works | **met, but inert** |
| M10 | KiCad import clean; SCOAP delta; stuck-at classification | **NOT MET** |
| M11a | Two clean builds hash-identical | **met** (2026-08-16) |
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

## M9 — met, but structurally inert with the shipped library

The packer works and is deterministic. It also cannot ever save anything,
because **every part in `libraries/74aup.csv` is one gate per package**:

```
gates_per_pkg distribution: {1: 16}
multi-gate parts: NONE
```

So `packed == unpacked == 23` on the showcase and always will be, `pack_cost`
equals the package count by construction, and the per-package rationale table
is 23 rows each saying "holds 1 gate(s)". "Spare avoidance" has never been
exercised because a spare gate cannot exist: a single-gate package has no
second slot to leave empty.

This is a **library gap, not a packer bug**. Real dual- and triple-gate 74AUP
parts exist (`74AUP2G00`, `74AUP2G08`, `74AUP3G04` …) in SOT-363/SOT-363-6 and
similar. Until at least one is added with its datasheet citation, C5 is dead
weight in every build and its exit criterion is unfalsifiable.

Two honest options, and the choice should be deliberate rather than drift:
add multi-gate parts and let the packer earn its place, or state in §12 C5 that
packing is inert for v0.1.0's library and defer it.

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

**The report's "worst path" is unreadable**, which is a user-facing symptom of
the same provenance gap as M11b. From the showcase build:

```
worst path: $abc$148$auto$blifparse.cc:386:parse_blif$149 ->
            $abc$148$auto$blifparse.cc:386:parse_blif$150 -> ...
```

Those are ABC's internal node names. The reader wants refdes (`U6 -> U19 ->
U2`) or source signals. The data to do it exists — `refdes.json` maps cells to
designators — so this is a rendering fix, not new analysis.

## M11a — met, after being extended

It was partial: `scripts/repro_check.py` compared the **C1 outputs only** and
said so in its own docstring, so the netlist and BOM — the things a "build"
actually is — were outside the comparison.

The reason it could not have covered them is worth recording: it drove
`gatepack estimate`, and **`estimate` invokes Yosys but never persists the
netlist**. The check looked for `mapped.json` after an estimate and could never
have found it, whatever was installed.

It now runs a full `build` as a second phase and compares the netlist too.
Measured in the toolchain container:

```
10 artefact(s) byte-identical, including the mapped netlist and BOM
(mapped.json, bom.csv, netlist.net, netlist.unpacked.net, refdes.json)
```

So Yosys 0.23's output is deterministic here, which was assumed and is now
measured. Without Yosys the script still runs but reports explicitly that the
criterion is **not** fully exercised, so a partial run cannot be mistaken for a
full one. Wired into the CI `toolchain` job.

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
