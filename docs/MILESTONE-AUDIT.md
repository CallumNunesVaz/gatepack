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
| M7 | ~~AsynchronousBackend — deferred to v0.2~~ | **met, constrained** (2026-08-24) — §7.3's own ≤3-literal / single-variable-change sub-problem, wired through verify/build/estimate, with an independent hazard verifier and an exhaustive functional check against the flow table. The general problem remains a v0.2 research task |
| M8 | CNT4 + SUPERVISOR + tie-off; shared behavioural models | **met** (2026-08-16) — a wrong M-cell model now fails equivalence |
| M9 | `pack_cost`; spare avoidance; deterministic; override works | **met** (2026-08-16) |
| M10 | ~~KiCad import clean~~; SCOAP delta; stuck-at classification | **met** (2026-08-16) for the analysis half; KiCad import **descoped**, and the descope re-confirmed by measurement 2026-08-23 — KiCad exposes no headless reader |
| M11a | Two clean builds hash-identical | **met** (2026-08-16) |
| M11b | Provenance coverage measured and reported on every golden | **met** (2026-08-16) |
| M12 | Project opens; core invoked; §5.2 posture verified | **met** |
| M13 | C10 spec editor — three-way sync, positions in sidecar | **met** (sidecar is localStorage, not `design.layout.json`) |
| M14 | C11 truth table — divergence highlighting | **met** (2026-08-16, was NOT met) |
| M15 | C12 schematic — all layers | **met** (2026-08-16) — packed and overlay layers render from `out/packed.json` |
| M16 | Linked selection — §15.2 cross-highlights | **met** (2026-08-16) — package and property selections resolve |
| M17 | C13 packing override, C14 dashboard, C15 tri-state | **met** (2026-08-16) |
| M12–M17 (sweep) | The whole journey, per example, through the real app | **met [GUI-1]** (2026-08-25) — all thirteen bundled examples, and a design created from nothing, complete New/open → compile → estimate → verify → build, every post-build view, and reveal/export of the artefacts. Both boundaries recorded on 2026-08-24 are now closed. |
| M18 | ~~Signed installers~~ **[M18-4]**; worked example; CI green | **met** (2026-08-23) — core and Linux toolchain ship; installers are unsigned by decision, not by omission |

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

## M8 — met (2026-08-16), after being the most serious defect in the project

The M-cell path was **unverified in the way that matters**. Two defects, both
measured 2026-08-16 and both now closed:

- The front end emitted a macro as a dangling `(* gp_src *)` attribute rather
  than an instantiation, so `gatepack verify` on a macro design failed at C3
  with `syntax error, unexpected TOK_ENDMODULE` and never reached C4.
- More seriously: with a hand-built netlist that *did* instantiate `CNT4`, a
  deliberately wrong model (`Q <= Q + 4'd2`) was **not caught**. Equivalence
  read `cells_sim.v` on both sides, so mutating the model changed both sides
  identically and Yosys still reported "Equivalence successfully proven!".

§19 R25 requires one shared model file so that equivalence and simulation
cannot drift. That control was satisfied — but only its trivial half. Sharing
the file is precisely what made a macro model **unable to be checked against
anything**: for a black box, the specification side had no independent
definition of the macro's behaviour, so the model was compared with itself.

This was the eighth piece of machinery in this project to report a status while
measuring nothing, and the most serious, because the status it reports is the
central claim: formal equivalence.

**The fix.** `gatepack/macros/specs.py` states each M-cell's required behaviour
as data — width, step, reset contract, enable — and generates `cells_spec.v`
from it. C4's golden side reads that; the gate side keeps reading
`cells_sim.v`. The two files are produced by different paths, so mutating the
implementation model moves only the gate side. `cells_sim.v` remains the single
implementation model shared with exhaustive simulation, so R25 is unweakened.

Measured directly against Yosys 0.23, not merely asserted by a test:

```
correct model (Q <= Q + 4'd1)   Equivalence successfully proven!            exit 0
mutated model (Q <= Q + 4'd2)   ERROR: Found 4 unproven $equiv cells        exit 1
```

The Yosys log confirms the two sides read different files:
`$add$cells_spec.v:16$80_gold` against `$add$cells_sim.v:4$92_gate`.

**What this does not establish.** The specification model and the
implementation model can still both be wrong in the same way, because a human
wrote both. The spec side is derived from the cell's declared semantics rather
than from the other file, which is the strongest available control short of a
second independent source; it is not a proof that the declared semantics are
what the datasheet part does.

`CNT4` is also the *only* M-cell in the library, so "a wrong M-cell model is
caught" is established on a sample of one. (`SUPERVISOR` is a tier-S supply
supervisor, not a synthesised macro, and has no behavioural model by design.)
The failure mode to watch is a macro added without a specification model:
`get_spec` raises rather than silently falling back to the implementation
model, so it fails loudly — but nothing yet *requires* a spec model to exist
before a macro can be used, and that check is worth adding when the second
M-cell arrives.

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

## M10 — met for v0.1.0, with the KiCad import criterion descoped

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

**"KiCad import clean" is descoped from v0.1.0** (decision 2026-08-16).

It has never been tested by importing anything into KiCad, and it cannot be
tested here: it needs a human with KiCad installed, opening the emitted netlist
and confirming that power symbols and no-connects survive. Rather than carry a
milestone open indefinitely on a criterion no automated check can close, the
criterion is removed from the v0.1.0 exit set and the emitter ships with its
status stated.

What this does **not** mean: it is not a claim that the import works. The
emitter is exercised by unit and golden tests against its own output format,
which establishes that it emits what it intends to emit, and nothing more.
Whether KiCad accepts it is unverified, and the release documentation says so
in those words.

The check to reinstate when someone has KiCad: import
`out/netlist.net` from a showcase build, confirm every component lands with its
footprint, confirm power symbols and no-connect flags survive, and diff the
resulting refdes set against `out/refdes.json`.
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

## M13–M16 — audited 2026-08-16, three of four not met

Full detail in `docs/GUI-AUDIT.md`, produced by driving the real application.
The headline: **three bridge methods call CLI subcommands that do not exist.**
`app/main/session.cts` invokes `mapped-netlist`, `provenance` and `analyse`;
none of them are in `cli.py`. So `mappedNetlist()`, `provenance()` and
`analyse()` have never returned data, which is why M15's layers and M16's
cross-highlights cannot work at all.

**The missing subcommands are now added** (`provenance`, `mapped-netlist`,
and `analyse` from the same round), so all three bridge methods return real
data and the audit's two intentionally-failing e2e specs now pass — 12 of 12.

That fixed the **data paths**, not the rendering, and the distinction matters:

- **M15 is partial, not met.** The netlistsvg layer can now obtain its input,
  and the test-point/unobservable overlay can now reach `analyse()`. But the
  **packed-netlist layer is not in the IPC contract at all** —
  `mappedNetlist()` returns the logical netlist only — so it remains a text
  notice rather than a render. "netlistsvg rendering all layers" needs the
  packed netlist exposed and drawn.
- **M16 is partial, not met.** `provenance()` now reaches the renderer, which
  is what the cross-highlights consume. Package and property selections still
  map to nothing.

**M14 was the worst and is now fixed.** `simulate()` returned `actual: "x"` for
every output of every design — including a two-input XOR — so `diverges` was
permanently false and C11's divergence column *could never fire*. Cause:
`simulate.load_mapped` never called `resolve_parts`, and Yosys's post-ABC
`write_json` carries no `port_directions`, so the evaluator could not tell an
input pin from an output pin.

The unit test covering it **fabricated a netlist with `port_directions`**,
which real Yosys output never has. It passed throughout. That is the seventh
piece of machinery in this project to report a status while measuring nothing,
and the fourth whose test could not have failed.

Now measured against a real netlist: correct netlist agrees on all four
minterms; `XOR2` swapped for `AND2` diverges on exactly the three minterms
where AND and XOR differ (`tests/toolchain/test_simulate_divergence.py`).

## M17 — met (2026-08-16, after being wrongly marked met, then partial)

The drag-to-regroup persisted **instance** names into `packing.force_groups`
while the packer resolves that field against **stable** names, so every
override was refused on the next build. Now translated through
`BuildResult.stableCellNames`, and the test asserts the stable name is in the
YAML rather than merely asserting *something* is — the previous assertion
passed either way because the fixture's name map was empty.

A second case fell out of writing that test: before any build there is no
stable-name map at all. The view now **refuses** to record an override then,
saying so, rather than writing an instance name that the packer rejects later
and that would point at a different gate if it did not.

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

## M18 — met for v0.1.0, with the signing criterion descoped

**Updated 2026-08-16: the core ships.** `scripts/bundle_core.py` produces a
self-contained PyInstaller binary at `app/resources/bin/gatepack` (~14.5 MB),
which `app/main/core.cts` already preferred over the host venv. Measured, not
asserted — under `env -i`, with no Python, no venv and no `PATH`:

```
$ env -i app/resources/bin/gatepack examples list
pelican (showcase)
$ env -i app/resources/bin/gatepack examples extract pelican -o <tmp>
wrote design.yaml / parts.csv
```

The acceptance test has both halves: with the bundle present the scrubbed
invocation must succeed, and with the bundle moved aside it must fail — without
the second half a host venv answering the call would prove nothing.

One defect was found in review of the first attempt and sent back. `examples/`
sits *beside* the `gatepack` package rather than inside it, so `--collect-all
gatepack` never collected it and the frozen binary answered `examples list` with
"no bundled examples found" and **exit 0**. The app opens the showcase on
launch, so a packaged app would have started to an empty list. The bundler's own
smoke test had checked two resources, found them present, and declared the
bundle proven. `libraries/74aup.csv` is deliberately *not* bundled: it is passed
as an explicit `--library` path and extracted projects carry their own
`parts.csv`.

`gatepack doctor` reports each external tool as found-with-version or missing,
so a user without yosys gets a named tool and its purpose rather than a stack
trace.

**Corrected 2026-08-23. Four claims in this section had gone stale, in the
direction that overstates the damage.** An audit that overstates is trusted
exactly as little as one that understates, so they are corrected here rather
than left to read as current:

1. ~~"The native toolchain is still not bundled."~~ It is, on Linux.
   `scripts/bundle_toolchain.py` copies yosys, iverilog, vvp, z3 and
   berkeley-abc out of the pinned `gatepack-toolchain:m6` image, freezes the
   Python drivers (sby, yosys-smtbmc, yosys-witness) with PyInstaller, walks
   each binary's `ldd` closure into `resources/bin/lib`, and records provenance
   per binary in `toolchain-manifest.json`. Measured 2026-08-23:
   `app/resources/bin/` holds ten executables plus that manifest, all ELF
   x86-64. **espresso is still not bundled**, on purpose — only the
   not-yet-shipped async backend uses it.
2. ~~"`resources/bin/` is empty."~~ Same measurement; that paragraph predated
   the core bundle and contradicted the top of this very section.
3. ~~"`licence_audit.py` does not see the bundled core."~~ It does:
   `--require-bundle` audits the PyInstaller bundle's contents and
   `--require-node-tree` the installed npm tree, and `desktop-packaging` passes
   both flags so a missing input is a failure rather than a silent skip.
4. ~~"CI's `desktop-packaging` job is expected red."~~ Both §4 defects were
   remediated (`1ea3755`, and the `yargs` exclusion). Run here 2026-08-23:

   ```
   licence audit: 694 dependency(s) GPL-3.0-compatible
                  (16 manifest, installed tree 69 shipped + 609 dev/other)
     elkjs 0.9.3 EPL-2.0 — the npm override holds
     spdx-exceptions CC-BY-3.0 — [excl] not shipped; non-blocking
   ```

**Not stale, and now a scope decision rather than an open item: no signing
credentials exist**, so all three platforms' installers build unsigned and will
trip Gatekeeper and SmartScreen. As of 2026-08-23 that is no longer counted
against M18 — [M18-4] removes "signed installers" from the exit set, because the
credentials cost money, have no bearing on correctness, and §21.6 already said a
FOSS project should not block a release on a certificate. The machinery stays:
signing happens if and only if credentials are supplied, and
`scripts/verify_signing.py` fails the release if a build claims to be signed and
is not. Nothing fabricates an identity.

`electron-builder` config exists and `--linux dir` builds an app that launches.
`scripts/version_check.py` prevents pyproject/package.json drift.

## What changed as a result

- `Dockerfile.probe` now carries pydantic, so the CLI runs inside the image.
- CI gained a `toolchain` job that builds that image, runs
  `tests/toolchain`, verifies three goldens against real binaries, and fails if
  a toolchain test *skips* — a skip being indistinguishable from the test not
  existing.

That job is expected to fail until the M5 repair lands. That is the point of
adding it before the fix rather than after.


## [GUI-1] What the per-example sweep measured, 2026-08-24

`app/tests/e2e/examples-end-to-end.spec.ts` runs the full journey once per
bundled example, driving the real Electron main process against a real core with
the real toolchain (via a `GATEPACK_CORE` shim into `gatepack-toolchain:m6`).
Milestone-by-milestone auditing had checked each view against *one* design;
sweeping all thirteen found two failures that only appear on a design class the
per-milestone audit never used:

* **The Analysis tab was a dead end for every asynchronous design.** `analyse`
  reads each cell's boolean function out of `out/cells.lib`, and the synchronous
  build wrote that file only incidentally — it needs it on disk to hand to
  Yosys. The asynchronous build hands Yosys nothing, so it never wrote it. Fixed
  in `gatepack/build.py`.
* **The Provenance tab told users to run a build they had just run.** Coverage
  needs a pre-map netlist, and an asynchronous design is synthesised straight
  from its flow table (§7.3), so it has none. Both "not built" and "no pre-map
  stage" returned the same `None`, and the message assumed the first. Fixed in
  `gatepack/provenance/coverage.py`: the second case now says coverage is *not
  measurable* rather than zero, and never instructs a rebuild.

Two boundaries are open, and are the reason the row above says *bounded*:

* ~~**The GUI cannot originate a design.**~~ **Closed 2026-08-24.** `gatepack
  project new` scaffolds a working `design.yaml` + `parts.csv`, and File > New
  Project… (`Mod+N`) runs it and opens the result. The template lives in the
  core so the CLI and the GUI cannot drift. The pinned `test.fail()` has been
  inverted into the positive test it was written as, and the sweep now covers
  creating a design from nothing through to a BOM.
* ~~**The build outputs are written, not offered.**~~ **Closed 2026-08-25.**
  File > Reveal Outputs opens `.gatepack/out`; Export Outputs… copies the BOM,
  netlist and report to a chosen folder. Reveal refuses rather than opening an
  empty directory, and export refuses rather than overwriting — all-or-nothing,
  naming the conflicts.

Closing the first one immediately found a third defect that had nothing to do
with it, and that no bundled example could ever have surfaced:

* **Any project in a path containing a space failed synthesis.** The generated
  Yosys script embedded every path unquoted, and Yosys splits script arguments
  on whitespace — so `/home/me/My Board/generated.v` became two arguments and
  reported `Can't open input file '/home/me/My'`. That surfaced as
  `equivalence: failed` and `exhaustive simulation: failed`: a *verification
  verdict* produced by a path, not by the design. Every bundled example lives at
  a whitespace-free path, so nothing in the suite had ever exercised it — it took
  a New Project dialog, which invites names like "My First Board", to reach it.
  Fixed in `gatepack/yosys/__init__.py` (`script_path`), quoting conditionally so
  §5.5's byte-identical `yosys.ys` is unchanged for ordinary builds.


## [GUI-2] How close you had to click, measured 2026-08-24

The schematic resolves a selection from `event.target` alone, so the clickable
area is exactly the geometry the browser painted. Nothing had ever measured what
that came to. Driving a real 651-element sheet and stepping outward from each
piece of geometry (`app/tests/e2e/schematic-pointer.spec.ts`):

| target | before | after |
|---|---|---|
| wire, perpendicular to the line | **±0.5 px** | ±5 px |
| centre of a 30×53 px gate symbol | **hit nothing** | selects the gate |

Both numbers come from the same cause — SVG hit-testing only what is painted.
netlistsvg draws wires at `stroke-width: 1`, and the skin sets `svg { fill:
none }`, so a gate symbol's interior is unpainted and therefore untouchable: a
click in the middle of one fell through to the bare `<svg>` and selected
nothing. Only the 1 px outline responded. ±0.5 px is about a quarter of the
hand tremor of a mouse user at rest, so selecting a wire was a matter of
patience rather than aim.

The fixes are separate because the causes are:

* **Gates** — `pointer-events: all` on the body shapes hit-tests the fill region
  whether or not anything is painted into it. One CSS rule; nothing drawn
  changes.
* **Wires** — a stroke's hit region *is* the painted stroke, and no CSS widens
  one without widening the other, so each wire gets an invisible 10 px-wide
  copy in a layer above the sheet (`applyHitTargets`). The copies carry the
  wire's `net_<bits>` class, so every handler resolves through them unchanged.

The first attempt at the wires silently did nothing, and the reason is worth
recording: the copies carry the net class, so `applyNetValues` stamps them too,
and `[data-gp-value='0'] { stroke-width: 1 }` out-ranks a presentation attribute
— every target was quietly shrunk back to 1 px while the DOM still said
`stroke-width="10"`. `[data-gp-value='x']` would have been worse, dashing the
target so that a click landed or missed depending on where along the wire it
fell. The width is now pinned in the stylesheet with the decoration reset.

### Wheel zoom

Added at the same time, and it exposed two things about the zoom that were
already wrong:

* The zoom host is `transform: scale()`, which scales what is drawn but **not
  the layout box** — so the scroll container sized itself to the *unzoomed*
  sheet, and zooming in pushed the right-hand side of a schematic somewhere no
  scrollbar could reach. It now reserves the scaled size.
* Anchoring the zoom under the pointer needs the scroll offset written *after*
  the host has been resized. Doing it in `requestAnimationFrame` was not late
  enough: the assignment was clamped to the old scroll area (it wanted
  `scrollLeft` 312 and got 55, the old maximum), so the sheet anchored correctly
  in Y and drifted 257 px in X. It is applied in a layout effect keyed on zoom.


## [GUI-3] The command palette was advertising four lies, 2026-08-25

Pressing each advertised shortcut in the running application:

```
Ctrl+B        -> "Build" is not wired yet
Ctrl+E        -> "Estimate viability" is not wired yet
Ctrl+Shift+C  -> "Compile" is not wired yet
Ctrl+Shift+V  -> "Verify" is not wired yet
```

The features worked — the views call `api.verify()` and friends through
`useRevisionedTask` — so nothing was broken except the route a user is told to
take. `commands.tsx` states the rule: *a reachable command that does nothing is
a lie; a reachable command that says so is a promise.* The toast kept the second
half, which is why this was a gap rather than a disaster.

`run.compile` was worse than unwired: **nothing in the renderer called
`api.compile` at all**, so there was no code path to connect. Its registry hint
promises a front-end-only check, which is a genuinely useful thing, so it now
runs from the shell and reports the state/flop counts through a toast.

`run.simulate` produced the one defect worth recording. The brief said to
trigger "TruthTable's task"; the truth table's only revisioned task is the
`estimate`-backed cover preview, and its divergence column comes from
`simulate()` through the linked-selection spine, which read it once on mount with
no refresh path. The literal mapping therefore made "Simulate truth table" run
*estimate* — a command reporting success having run something else. The spine now
has a reload signal. The error was in the brief, not the implementation, and the
delegated model flagged it as its own weakest point before it was found here.

## [GUI-4] Editing the graph deleted what the example was teaching, 2026-08-25

`applyTopLevelEdit` re-serialised a whole top-level block from the parsed model.
Adding one transition to `examples/edge_detector/design.yaml` deleted both
per-transition comments, unquoted `when: "din"`, and collapsed the hand-aligned
columns. Those comments are where that example explains what each state means, so
dragging one edge destroyed the thing the user was reading — silently, and behind
a debounced write with no obvious moment to undo.

Adding and removing list items are now line splices, alongside the field splices
the rename work already had. `setInputSync` had recorded the identical finding on
the `inputs:` block a milestone earlier: *toggling input `b` deleted `# MUST stay
synchronised — metastability` from input `a`*. The same defect, found twice, on
two different blocks, because the first fix was applied to one field rather than
to the pattern.
