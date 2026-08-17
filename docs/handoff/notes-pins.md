# Handoff notes — pins: the masked-mutation question

This run finished the pin-fit work and resolved the one thing the previous run
stopped in the middle of: why `gatepack verify` on the `sequence_detector`
example reported two planted mutations as NOT detected.

Everything the previous run did in `libraries/74aup.csv` + `74aup.refs.md`
stands and was left alone: `NAND3`/`NOR3` cleared (no AUP single 3-input
NAND/NOR exists), `AND3` -> `SOT-363`, `DFF_R` -> `SOT-363`, `DFF_SR` ->
`VSSOP-8`, plus the "Package pin counts" table and `test_package_pin_fit.py`.

## Masked or insensitive — the determination and the evidence

The failing example was `sequence_detector`:

```
failed   mutation   one or more mutations NOT detected: nand_to_and, reset_polarity_flip
```

The brief asked: are those faults **masked** (provably unobservable at an
output) or is the verification **insensitive** (the fault reaches an output but
the checks do not look there)? I determined it from the actual netlist and the
actual mutations; the answer is **not the same for the two mutations**.

The mapped netlist (`build/mapped.v`) for `sequence_detector` has two `NAND2`
instances (`_10_` and `_15_`), six `DFF_R` flops, and a single primary output
`match = state_S3` (Moore). The `nand_to_and` mutation turns **both** `NAND2`s
into `AND2`s; the `reset_polarity_flip` mutation rewrites the `DFF_R` reset
condition.

### `nand_to_and` is genuinely masked

The two corrupted gates feed only the *next-state* logic for `S0` and `S1`:

- `_10_` computes `_03_`, which feeds `next_S1` (via `AND2 _11_`);
- `_15_` computes `_06_`, which feeds `next_S0` (via `AND2 _16_`).

`match` depends only on `state_S3`; `next_S3 = din & state_S2` and
`next_S2 = ~(din | ~(S1|S3))` are **not** touched by the mutation, and the
corrupted `S1` is OR-ed with a correctly-set `S3` inside `next_S2`, so it is
masked there too. The fault changes the *state encoding* (`S0`, `S1`) but can
never change the output.

Two independent pieces of evidence:

1. **Exhaustive reachable-state analysis** (a BFS over the exact next-state
   functions of the golden and mutated machines, starting from reset) showed
   `match` is identical in every reachable state:

   ```
   golden reachable states: 5  [(0,0,0,0),(0,0,0,1),(0,0,1,0),(0,1,0,0),(1,0,0,0)]
   mutated reachable states: 5 [(0,0,0,0),(0,0,1,0),(0,1,0,0),(1,0,0,0),(1,1,0,1)]
   matching-state match differences: []      # match never differs
   ```

2. **`equiv_induct`** proves `match` (and `state_S1`, `state_S2`, `next_S2`,
   `next_S3`) equivalent and fails only on the unobservable state bits:

   ```
   Trying to prove $equiv for \match: success!
   Trying to prove $equiv for \state_S2: success!
   Trying to prove $equiv for \next_S2: success!
   Trying to prove $equiv for \next_S1: failed.
   Trying to prove $equiv for \state_S0: failed.
   ...
   ERROR: Found 2 unproven $equiv cells in 'equiv_status -assert'.
   ```

So the equivalence check **does** catch the fault (full-state divergence); the
exhaustive simulation honestly passes because the output never changes. The
check that was wrong is the mutation *verdict*, which required **both** checks
to fail and therefore called this "NOT DETECTED".

### `reset_polarity_flip` is caught by equivalence; the simulation does not look at the reset phase

The mutation leaves `negedge RST_N` in the sensitivity list but flips the
condition to `if (RST_N)`, producing a `DFF_R` whose async reset no longer
clears. The equivalence check catches it immediately — `async2sync` refuses to
model the contradictory reset:

```
ERROR: Async reset \RST_N yields non-constant value 1'm for signal \Q.
```

The exhaustive simulation passes for a *scope* reason, not a vacuity reason:
§9.6 makes the reset a **setup step** (assert, release, flush three edges) and
only checks outputs at *transition* edges, never while reset is asserted. A
probe confirms the fault really is observable at the output during reset —
asserting reset while the machine is in `S3` leaves `match` stuck high:

```
=== RESET MUTATED ===
in S3:                     ... S3=1 match=1
during reset assert:       ... S3=1 match=1     <- fault: reset did not clear
after second flush:        ... S1=1 ... match=0  <- wrong state (S1, not S0)
```

So this is not "provably cannot propagate"; it is "the simulation does not
check the reset assertion path". The reset is independently verified by the
equivalence check and by the `flop reset connectivity` property check, so the
fault is caught — just not by the exhaustive simulation.

### The fix

The mutation checker's rule "detected only when **both** checks fail" was the
bug. It reports a fault that equivalence alone catches — but which does not
change a primary output — as if no check had caught it, and the example failed.

I added a third verdict, **`masked`**, for "equivalence fails, exhaustive
simulation passes". A mutation is now:

- **detected** — equivalence *and* simulation both fail (fault reaches an output);
- **masked** — equivalence fails, simulation passes (caught by the full-state
  check; no primary output differs in the reachable transitions the simulation
  checks) — *not* a vacuity finding;
- **undetected** — equivalence passes (the stronger check missed the fault) —
  still a hard failure (R2/R18).

"Masked" is established by evidence (the equivalence **failure** plus the
simulation's exhaustive pass), never assumed from "the checks passed" — the
both-pass case stays "undetected" and still fails. Files changed:
`gatepack/verify/mutation.py` (`is_masked`, docstring), `verify/base.py`
(`MutationOutcome.masked`, `has_failure`), `verify/synchronous.py`,
`verify/run.py` (manifest carries `masked`), and the `cli.py` mutation line
renders `masked` instead of `NOT DETECTED`.

After the fix the example verifies honestly:

```
verification: passed
  equivalence:               passed
  exhaustive simulation:     passed
  mutation:                  passed  (all applicable mutations detected or masked)
  mutation nand_to_and:      masked
  mutation flop_d_invert:    detected
  mutation reset_polarity_flip: masked
```

## Package counts that moved

Measured against the shipped full library (`libraries/74aup.csv`), which is
what the estimate/build-consistency and bundled-toolchain tests use:

| example | was | now | why |
|---|---|---|---|
| pelican | 20 | **19** | `NAND3`/`NOR3` dropped -> remapped onto the multi-gate 2G00/2G02/2G08/2G32 |
| debounce | 12 | **13** | the `1G27` (3-input NOR) is gone; remapped to more 2-gate parts |
| sequence_detector | 14 | **12** | the two `1G27`s are gone; remapped onto a dual NAND `2G00` |
| mux2to1 | 3 | 3 | unchanged (INV + NAND2 only) |
| parity | 2 | 2 | unchanged (XOR2 only) |
| power_sequencer | 10 | 10 | the `1G27` became a `2G02`, same package count |

Measured BOMs (full library):

- pelican (19): `74AUP1G04` x1, `74AUP1G11` x1, `74AUP1G175` x11, `74AUP2G00` x1, `74AUP2G02` x1, `74AUP2G08` x2, `74AUP2G32` x2.
- debounce (13): `74AUP1G175` x8, `74AUP2G00` x1, `74AUP2G08` x2, `74AUP2G32` x2.
- sequence_detector (12): `74AUP1G04` x1, `74AUP1G175` x6, `74AUP2G00` x1, `74AUP2G02` x1, `74AUP2G08` x2, `74AUP2G32` x1.
- mux2to1 (3): `74AUP1G04` x1, `74AUP2G00` x2.
- parity (2): `74AUP1G86` x2.
- power_sequencer (10): `74AUP1G175` x6, `74AUP2G02` x2, `74AUP2G08` x1, `74AUP2G32` x1.

The `74AUP1G11` (3-input AND) survives in the pelican BOM; it is the one
3-input gate that has a real part. `NAND3`/`NOR3` have no candidate part and
are correctly absent from every BOM.

### Header / test corrections

- `examples/pelican/design.yaml` header: "~20 mapped gates" -> "23 mapped
  cells" and "74AUP single-gate packages" -> "23 single-gate 74AUP packages".
  The showcase ships a *single-gate-only* `parts.csv` (17 rows, all
  `gates_per_pkg: 1`; this is deliberate — see
  `tests/unit/test_examples.py::test_every_example_ships_its_own_library_and_citations`),
  so it maps 23 cells to 23 single-gate packages. The 19-package figure is the
  full-library build used by the consistency tests. Regenerated `pelican.gpk`
  via `project bundle`.
- `mux2to1` header ("three 74AUP packages (a 1G04 and two dual-NAND 2G00s)")
  and `parity` header ("two 74AUP 1G86 gates") were re-checked and are still
  correct; they use no 3-input gate and did not move.
- `tests/toolchain/test_estimate_build_consistency.py`: "23 cells into 20
  packages" -> "23 cells into **19** packages" (comment and docstring).
- `tests/toolchain/test_toolchain_bundle.py`: the hard-coded showcase BOM
  `packageCount == 20` -> `== 19` (assertion, comment, docstring). This is a
  third place the showcase count was pinned; the brief named only the first
  two.

## Proof (real command output)

All run with `docker run --rm -u "$(id -u):$(id -g)" -v "$PWD:/repo" -w /repo
gatepack-toolchain:m6`.

**`gatepack lib check libraries/74aup.csv`** (exit 0):

```
loaded 26 cells from libraries/74aup.csv
dropped 6 cell(s):
  - NAND3: single-sourced — 0 source(s); need >= 2
  - NOR3: single-sourced — 0 source(s); need >= 2
  - MUX2: single-sourced — 1 source(s); need >= 2
  - DFF_S: single-sourced — 0 source(s); need >= 2
  - CNT4: tier — tier 'M' is never an inference target
  - SUPERVISOR: tier — tier 'S' is never an inference target
  summary: single-sourced: 4, tier: 2
citations: all 26 cells have a 74aup.refs.md entry
```

**Every example builds (no acknowledgement flag) and verifies** — all six exit 0.
`sequence_detector` in full:

```
verification: passed
  equivalence:               passed
  exhaustive simulation:     passed
  mutation:                  passed
      all applicable mutations detected or masked
  flop reset connectivity:   passed
  supervisor parameters:     passed
  mutation nand_to_and:      masked
  mutation flop_d_invert:    detected
  mutation reset_polarity_flip: masked
```

**Full test suite**:

```
$ .venv/bin/python -m pytest tests -q
... 705 passed, 5 skipped ...
```

**Falsification of `test_package_pin_fit.py`** — I planted a wrong row (AND3
moved from the 6-pin `SOT-363` to the 5-pin `SOT-353`), and the check caught it:

```
$ .venv/bin/python -m pytest tests/unit/test_package_pin_fit.py -q
...
E   AssertionError: rows that do not fit their package:
E     AND3: 74AUP1G11 needs 6 pins but SOT-353 has 5
FAILED tests/unit/test_package_pin_fit.py::test_every_g_f_cell_fits_its_package
1 failed, 1 passed
```

The bad row was then reverted; the suite is green again (2 passed).

## What I could not settle

- The exhaustive simulation still does not verify the async-reset *assertion*
  (it treats reset as a §9.6 setup step and only checks transition edges). I
  chose **not** to extend it: that is a larger change to the simulation's
  contract, and the reset is already verified by the equivalence check and the
  `flop reset connectivity` property check. The consequence is that
  `reset_polarity_flip` is reported `masked` (caught by equivalence, not by the
  output-only simulation) rather than `detected`, and the honest reason — the
  fault *is* observable during reset, the simulation just does not look there —
  is the probe evidence quoted above. If the simulation is later taught to
  check the reset flush, this mutation should flip to `detected`.
- The `pelican` showcase ships a single-gate-only `parts.csv` (23 single-gate
  packages) while the consistency/bundle tests build it against the full
  library (19 packages). That split predates this work and is deliberate; I
  documented both numbers rather than change the showcase's library, which the
  brief did not ask for.

---

## Maintainer addendum — the verdict was renamed, and a guard added

Two amendments on review, both about the new verdict rather than the analysis
that produced it. The per-mutation determinations above are sound and were
independently re-derived; so were all four datasheet citations.

**1. `masked` → `caught by equivalence only`.** The report itself establishes
that the two mutations are in materially different situations:

- `nand_to_and` genuinely cannot reach a primary output in any reachable state
  (BFS over the next-state functions, plus `equiv_induct` proving `\match`
  equivalent) — classical fault masking;
- `reset_polarity_flip` *can* reach an output — the probe in this document
  shows `match` stuck high when reset is asserted from `S3` — but the
  exhaustive simulation never exercises the reset-assertion phase (§9.6 treats
  reset as a setup step). That is a coverage gap in the simulation, not a
  benign fault.

Both were reported `masked`. The checker cannot tell them apart: it sees two
status values and nothing else, and establishing masking needs a reachability
argument no status code carries. Naming the verdict after a cause it cannot
establish is the failure this project keeps finding, so the verdict now names
what was observed — equivalence caught it, the simulation did not — and the
docstring sets out both possible reasons without asserting either.

**2. All-equivalence-only no longer passes.** `has_failure` excluded the new
verdict unconditionally, so a run in which *every* applicable mutation was
caught by equivalence alone would report the mutation check green. But such a
run has shown nothing about the exhaustive simulation, and is indistinguishable
from one where the simulation passes unconditionally — the exact vacuity this
suite exists to catch, one check over. `simulation_was_exercised` now requires
at least one applicable mutation to have been `detected` (which needs the
simulation to have failed) before the check can pass; a design no mutation
applies to is exempt, because that is a category error rather than a vacuity.

Falsified against all three shapes: all-equivalence-only → FAILED ("simulation
never exercised"); one detected plus one equivalence-only → PASSED; one
genuinely undetected → FAILED. On the real `sequence_detector`, `flop_d_invert`
is `detected`, so the simulation is demonstrably live and the check passes for
a reason rather than by construction.

**Still open (unchanged by this):** the exhaustive simulation does not verify
async-reset *assertion*. `reset_polarity_flip` is caught by equivalence and by
the flop-reset-connectivity check, so nothing is unverified — but the
simulation's coverage gap is real and is now named rather than dressed up.
