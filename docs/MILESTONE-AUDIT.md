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
| M8 | CNT4 + SUPERVISOR + tie-off; shared behavioural models | **met**, depth unverified |
| M9 | `pack_cost`; spare avoidance; deterministic; override works | **met** (2026-08-16) |
| M10 | KiCad import clean; SCOAP delta; stuck-at classification | **partial** — analysis met, KiCad import unverified |
| M11a | Two clean builds hash-identical | **met** (2026-08-16) |
| M11b | Provenance coverage measured and reported on every golden | **met** (2026-08-16) |
| M12 | Project opens; core invoked; §5.2 posture verified | **met** |
| M13–M16 | Spec editor, truth table, schematic, linked selection | **unaudited** |
| M17 | C13 packing override, C14 dashboard, C15 tri-state | **partial** — override does not round-trip |
| M18 | Signed installers; worked example; CI green | **partial** — packaging builds, licence defects open, core does not ship |

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

## M9 — met (2026-08-16), after the library gained multi-gate parts

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

**Resolved by adding the parts.** `74AUP2G00/2G02/2G04/2G08/2G32` and
`74AUP3G04` are now in the library, and the packer immediately earns its place
on the showcase:

```
before   23 package(s), 0 spare gate(s), pack_cost 23
after    20 package(s), 3 spare gate(s), pack_cost 32
```

Spare gates can now exist, so "spare avoidance" is falsifiable and `pack_cost`
is no longer just the package count. Every golden still verifies and the build
is still byte-reproducible (10 artefacts).

Two defects surfaced the moment a function was offered by more than one
package, both the same shape and neither reachable before:

- the Liberty generator emitted **one block per part**, so a second `NAND2`
  row produced two `cell (NAND2)` groups — malformed in exactly the way R1
  warns about, since it parses and silently keeps the last;
- `cells_sim.v` emitted duplicate module definitions, which Icarus rejects
  outright — equivalence and exhaustive simulation both failed instantly.

Both now go through one shared `parts.representative_parts`, because the whole
point of generating the two artefacts from the same source is that they cannot
drift.

The electrical values, the packages and the gate counts are all placeholders
pending citation, marked as such in `74aup.refs.md` — a wrong `gates_per_pkg`
yields a netlist that cannot be built, which is a worse failure than a wrong
tPD, so it is called out separately there.

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

## M11b — met (2026-08-16)

The report now carries a measured provenance section. On the showcase:

```
kind            total  exact  inferred  absent
states            1      1       0         0
transitions       7      5       0         2
output_logic      4      4       0         0
inputs            2      2       0         0
reset             1      1       0         0

Constructs with no link: transitions[1], transitions[4]
```

The unlinked constructs are **named** rather than hidden behind the 86.7%
aggregate, and the section says so: "the per-kind table is the figure that
matters; the aggregate conceals a weak axis such as transitions at 2/5".

Two name-space mismatches were fixed on the way, and a third was found from
outside its own scope by the same delegation: `map.ts` asked for `states[i]`
while C1 emits the bare token `states`, so **every state selection read "no
link"** despite states having the best provenance of any construct kind. See
the M13–M16 entry — that is a GUI defect that the GUI's own tests did not
catch.

## M13–M16 — unaudited

Merged on their test counts, which is the same evidence that failed on M5, M10
and M9. Never driven as a real application. The `states[i]` defect above is one
already-known example of what that misses: it was found by a core agent reading
the renderer, not by the renderer's 147 passing tests.

Being audited now (`deepseek/gui2`).

## M17 — partial

**Corrected the same day it was marked met, which was premature.** The
drag-to-regroup persists **instance** names into `packing.force_groups`, and
the packer resolves that field against **stable** names — so every override the
view writes is refused on the next build with "unknown cell".

I added `BuildResult.stableCellNames` to the contract precisely so the renderer
could translate, then marked the milestone met without checking that the
renderer used it. It does not: `stableCellNames` appears nowhere in
`app/renderer/` except a test fixture. Adding the mechanism is not the same as
closing the loop, and that is the identical mistake this audit exists to catch
in others.

The delegation that built the view said as much in its own notes — "the cell
list and grouping cards have only ever rendered against a hand-written
`write_json` fixture, never a real `mapped.json` with the actual instance names
the packer's `force_groups` would need". It was right, and I marked it met
anyway.

What *is* done:

C13 renders package cards with drag-to-regroup persisting to
`packing.force_groups` in `design.yaml`; C14 renders metrics against the
constraints block, red on `Metric.violated` (taken from the core, never
recomputed in the renderer); C15 already used the four-state badge.

Two things had to be fixed for it to be true rather than merely present:

- the "grouping is inert" note was **hardcoded**, and became a false statement
  about the user's design an hour later when the library gained multi-gate
  parts. `BomLine.gatesPerPackage` now carries the fact and the view derives
  the claim. The test checks both directions.
- `force_groups` had never worked at all (see M9), so the override the view
  persists would have been refused on every rebuild.

## M18 — partial

`electron-builder` config exists and `--linux dir` builds an app that launches.
`scripts/version_check.py` prevents pyproject/package.json drift. The licence
audit now walks the full installed npm tree instead of a 16-entry manifest, and
immediately found two real §4 defects:

- **`spdx-exceptions` (CC-BY-3.0) ships in the asar**, via netlistsvg's `yargs`
  CLI subtree. Not GPL-compatible. The audit fails on it, exit 1.
- **The shipped `elkjs` is EPL-1.0, not the EPL-2.0 §4 records.** netlistsvg
  bundles its own `elkjs@0.3.0`. §4's argument for accepting elkjs rests on
  EPL-2.0's secondary-licence provision, which EPL-1.0 does not have.

CI's `desktop-packaging` job is expected red until both are remediated
(`deepseek/licence2`).

**The Python core does not ship inside the app.** `resources/bin/` is empty and
bundling Python plus yosys/sby/espresso/iverilog per platform is a separate
milestone. Stated in `docs/RELEASING.md` rather than papered over — but it
means "signed installers" cannot be claimed as met.

## What changed as a result

- `Dockerfile.probe` now carries pydantic, so the CLI runs inside the image.
- CI gained a `toolchain` job that builds that image, runs
  `tests/toolchain`, verifies three goldens against real binaries, and fails if
  a toolchain test *skips* — a skip being indistinguishable from the test not
  existing.

That job is expected to fail until the M5 repair lands. That is the point of
adding it before the fix rather than after.
