# BUILD-NOTES-asyncfunc.md — Package L: the asynchronous path gets a functional check

## What this package closes

The async `verify` report had three checks and not one of them asked whether the
netlist implements the design: equivalence was `not applicable` (defensibly — no
synchronous golden), and the two hazard checks asked only whether outputs glitch.
The injection probe in `tests/toolchain/_async_hazard_injection.py` measured the
gap: drop one z3-selected product term from the cover (a stage-4 bug's
fingerprint) and the result was

```
cover cubes, clean run   [1, 2]
cover cubes, faulty run  [1, 1]      <- the injection fired
hazard (ternary)         passed
hazard (glitch sim)      passed
netlist accessor         RETURNED A NETLIST
```

A netlist that no longer implemented the specified machine, reported green. This
package adds the missing piece: **exhaustive fundamental-mode simulation of the
mapped netlist against the flow table**, as a third, first-class check.

## What was implemented

* **`gatepack/verify/asynchronous.py`** — `run_functional_check`, plus
  `enumerate_functional_pairs`, `FUNCTIONAL_CHECK_NAME` and `ASYNC_FUNC_ENUM_CAP`.
  For every **stable total state** (a state/input combination the flow table
  marks stable) and every **single-input change**, the netlist is evaluated to a
  fixed point with the state feedback held at the source state's code and the
  inputs at the post-change combination; the settled next-state code and the
  outputs are compared against what the flow table says they must be.  A mismatch
  is a **`failed`** check naming the total state, the changing input, and the
  expected/actual values — never a warning.  Wired into `verify_netlist` as the
  third check (after the two hazard checks).
* **`gatepack/verify/hazard.py`** — one pure helper, `driven_values`, which reads
  the value a feedback net's SOP is *driving* while that net is held (the
  loop-cut next-state value).  It imports nothing from `gatepack/synth/async_`;
  the existing AST-parsing independence test still passes unmodified.
* **`gatepack/async_pipeline.py`** — `hazard_passed` changed from `report.ok` to
  "every check `PASSED`", so a `not applicable` functional check no longer lets a
  netlist be emitted.  This is the one line that makes `not applicable` gate the
  netlist, not merely decorate it.
* **`gatepack/report/report.py`** — the async report states what the functional
  check is and that its scope is exactly fundamental mode.

## What the check enumerates — and what it cannot reach

The domain is `stable_total_states × n_inputs` pairs, enumerated exhaustively
(never sampled).  For the latch that is 8 pairs; a future change that quietly
reduces coverage fails `test_enumerate_is_exhaustive_not_sampled` because the
passed detail carries the pair count.

The check verifies the **one-step next-state/output function** — the netlist,
with the state held at the source total state, must drive exactly the flow
table's next state and outputs.  It does **not** do full feedback settling
through transient unstable states, and it should not: the flow table *is* the
specification of that function, and fundamental-mode traversal through transient
states is what the hazard checks (5a pessimistic, 5b Icarus with full settling)
are for.  It cannot reach concurrent input changes (fundamental mode), which is
why the report says so every time.

## On re-deriving the assignment (the circularity question)

`run_functional_check` re-derives both the flow table and the SVC assignment, the
same way the hazard probes already do.  My conclusion: **legitimate, not
circular in any harmful way**, because the *function under test is the cover*
(stage 4) and its emission, not the assignment:

* the **flow table** is derived from the spec's own semantics (no solver) — it is
  the specification, not a synthesis artefact;
* the **assignment** is re-derived deterministically (z3 runs with a fixed seed,
  `smt.RANDOM_SEED = 0`), so the verifier and the synthesiser agree by
  construction, exactly as the pre-existing determinism test pins;
* the **netlist** is evaluated by `hazard.py`'s evaluator, which imports nothing
  from `gatepack/synth/async_` — the independent half of the comparison.

Consequence: a bug in stage 4 (a dropped or wrong cube) changes the netlist and
is caught; a hypothetical bug in stage 3 (a wrong assignment) would **not** be
caught, because the check would compare the netlist against the same wrong
assignment.  That is the pre-existing SVC gap inherited from Package E, not one
this check claims to close; the assignment's SVC property is enforced by stage
3's own z3 constraints and has never been re-verified by stage 5.

## What it found in stage 4

Nothing.  On the unpatched pipeline the clean cover realises the flow table
exactly, and the functional check passes for every committed design that can be
synthesised.  The only failing case is the **injected** fault (the dropped cube),
which is artificial by construction — stage 4 as shipped does not drop cubes.

## What I verified against the real toolchain

All of the following close inside `gatepack-toolchain:m6` (z3 4.8.12, Icarus 11),
run with `-u "$(id -u):$(id -g)"`.

`gatepack verify examples/async_latch/design.yaml`:

```
verification: passed
  equivalence:               not applicable
  hazard (ternary):          passed
      8 fundamental-mode transition(s) checked, no potential static hazard
  hazard (glitch sim):       passed
      no output glitch observed across 3 delay-perturbation seeds
  functional (fundamental mode): passed
      8 total-state/input-change pairs checked; netlist matches the flow table
```

The injection probe (`tests/toolchain/_async_hazard_injection.py`) now produces:

```
cover cubes clean [1, 2] / faulty [1, 1]     <- injection still fires
functional (fundamental mode)  clean: passed, faulty: failed
netlist accessor              HazardFailed
netlist_reason  ... expected next IDLE outputs q=0, got next BUSY outputs q=0 ...
```

`tests/toolchain/test_async_injection.py` pins this (real z3 + Icarus): the
faulty run reports a **failed** functional check and `faulty.netlist()` raises
`HazardFailed`, while the clean run passes.  This is the acceptance criterion.

## Test counts

* Baseline (measured, this checkout): **873 passed, 5 skipped**.
* After this change: **882 passed, 5 skipped** — 9 new: 8 unit
  `test_async_functional.py` + 1 toolchain `test_async_injection.py`; plus one
  assertion added to `test_async_wire.py` (the check reported by name).

## What is weakest / residual

* **`not applicable` and the top-level verdict.** `hazard_passed` now gates the
  netlist on `not applicable`, but the *overall* `verification:` line is computed
  in `gatepack/verify/run.py` from `report.ok` (base.py), which still treats
  `not applicable` as a non-blocking non-verdict — the §21.4 convention the
  synchronous path relies on.  A too-large async design would therefore print
  `verification: passed` beside a `functional (fundamental mode): not applicable`
  line while writing **no** netlist.  Fixing that honestly needs a one-line
  change in `run.py`, which is outside this package's file scope.  The check's
  own status never reads `passed` (it is `not applicable`, with reason), and the
  netlist is gated; the top-line string is the only dishonest residue.
* **Multi-bit state codes are unit-pinned, not design-exercised.** The only
  committed synthesizable async design is 2-state (width 1).  The width-2 path
  (`test_functional_check_generalises_to_multi_bit_state_codes`) is hand-built,
  not produced by real z3, because no committed design exercises it.
* **`driven_values` assumes a single driver per feedback net.** True for the
  emitter (each `s_j` is driven by one SOP tail), and `setdefault` takes the
  first driver otherwise; a hand-built or future netlist that wires two gates to
  one state net would silently use one.  Matching the emitter today.

## Three things I am least confident about

1. **The one-step vs full-settling semantics.** I am confident the check is
   correct — the flow table is the spec of the next-state function — but a reader
   could expect "settled next-state" to mean full feedback traversal, which the
   check deliberately does not do.  Full traversal is 5a/5b's job; I have argued
   the split but not re-derived the hazard-check side.
2. **The `not applicable` top-line residue** above.  It is recorded, not closed;
   the netlist is gated, but `verify` still prints `passed` for a too-large
   design because the fix is out of scope.
3. **`driven_values`'s single-driver assumption**, which is structural truth
   today but un-enforced, as above.
