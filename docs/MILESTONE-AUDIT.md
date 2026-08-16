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
| M5 | Equivalence closes on all goldens; exhaustive sim; mutation | **met** (2026-08-16) |
| M6 | sby discharges invariants/reachability/liveness; covers guard vacuity | **met** (2026-08-16) |
| M8 | CNT4 + SUPERVISOR + tie-off; shared behavioural models | **met** |
| M9 | `pack_cost`; spare avoidance; deterministic; override works | **met, but inert** |
| M10 | KiCad import clean; SCOAP delta; stuck-at classification | **partial** — analysis met, KiCad import unverified |
| M11a | Two clean builds hash-identical | **met** (2026-08-16) |
| M11b | Provenance coverage measured and reported on every golden | **NOT MET** |
| M12 | Project opens; core invoked; §5.2 posture verified | **met** |

## M5 — met (2026-08-16)

Running `gatepack verify` under a container with real Yosys, Icarus and sby:

```
xor2               equivalence: failed   ERROR: Can't find gold module golden.
decoder_3to8       equivalence: failed   ERROR: Can't find gold module golden.
traffic_light      equivalence: failed   +  exhaustive simulation: failed
property_violating equivalence: failed
```

Equivalence had never closed on any design — it errored out before comparing
anything. Now measured on the real toolchain:

```
xor2, decoder_3to8, traffic_light   passed (equivalence + sim + mutation)
property_violating                  failed (must-fail golden)
vacuous_mutex                       failed (vacuity guard)
pelican showcase                    passed
```

Negative controls confirm the check can still fail: XOR2 swapped for AND2 in a
mapped netlist yields `Found 1 unproven $equiv cells`.

Four defects, not one:

1. `design -stash` clears the design, so `equiv_make` was given names that no
   longer existed (`M0-FINDINGS.md` §6).
2. The exhaustive testbench flushed reset with **four** clocks where three are
   exact — the fourth advanced the machine one transition past its initial
   state. Masked for a long time because `traffic_light`'s initial state
   self-loops under all-zero inputs; the showcase, whose `STOP` advances
   unconditionally, is what exposed it.
3. Mutation reported flop mutations as "NOT DETECTED" on combinational designs
   where they cannot apply — and `cli.py` then rendered `not_applicable` the
   same way, printing three "NOT DETECTED" lines beside a "passed" summary.
4. `simulate.py` depended on a private `_expected_outputs` that was renamed
   during (2), breaking every caller. Now public.

`cells_sim.v` **is** generated correctly (by `liberty/sim.py`, not a static
file) — an earlier concern of mine that was unfounded.

## M6 — met (2026-08-16)

The vacuity guard now covers the **antecedent**, derived from the expression
AST rather than by string matching: one cover per referenced signal for a
`mutex`, the implication's `p` for an `invariant` of the form `p -> q`.

Verified against real sby, with the control that matters:

```
vacuous_mutex   FAILED — "vacuous pass rejected (signal 'b' asserted): the
                property holds only because its antecedent never occurs"
traffic_light   passed — an honest mutex is not rejected
```

Liveness is emitted as a bounded check reporting `bounded` with its depth,
never `passed`.

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

**The analysis half is now met.** `scoap.py` and `faults.py` exist and run on a
real netlist; the report carries a SCOAP delta table, an unobservable-net list,
and a four-way fault classification with both collapsed and uncollapsed counts.
On the showcase: 59 collapsed faults, 53 detected, 0 undetected, 6 untestable,
against an exhaustive 8192-vector set.

The defect worth recording is one only a real netlist could show. The mapped
JSON parser resolved a bit to a net name last-writer-wins, and C1 deliberately
emits `<out>_int` intermediates to carry provenance — so an output bit is named
both `walk` and `walk_int`. Cell connections resolved to the alias while
`netlist.outputs` held the port name, and nothing matched: **SCOAP reported
every output-driving net as unobservable**, telling the reader that all four of
the showcase's outputs were untestable. Port names now win the bit resolution,
which fixes it at source for any consumer comparing a cell connection to a
port. Unobservable nets went from 24 (including every output) to 1
(`rst_n_s1`, correct under the combinational cut).

The delegated agent stated plainly that it had never run against a real
netlist. It was right to, and that is exactly where the defect was.

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
