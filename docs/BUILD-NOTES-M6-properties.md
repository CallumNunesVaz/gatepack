# BUILD NOTES — M6 property verification (vacuity guard + liveness)

Scope: two known weaknesses in M6, on branch `deepseek/props`. Confined to
`gatepack/frontend/verilog.py` (only `emit_properties` and its helpers),
`gatepack/verify/properties.py`, the property golden designs, and the property
test files. Nothing else touched.

## Test status

```
.venv/bin/python -m pytest tests -q   # 423 passed, 2 skipped  (baseline 403, 2)
npx vitest run                        # 98 passed (unchanged)
npx tsc --noEmit -p tsconfig.json     # pre-existing errors, unrelated to this work
```

The two skips are unchanged (property-discharge and latch-inferring goldens).
`tests/toolchain/` tests **run** here (docker + `gatepack-toolchain:m6` are
present) rather than skipping; they now include a real end-to-end sby
discharge.

`tsc` reports errors about `FakeGatepack` missing a `simulate` member —
pre-existing, in `app/`, owned by another agent. Not touched, not mine.

---

## 1. Vacuity guard now covers the antecedent, not the body

The old code emitted one `gp_cover_N` covering the **property body**. For a
mutex `!(a & b) & !(b & c)` that body is satisfied by the all-zero state, so
the cover reached trivially and proved nothing. New behaviour, in
`property_cover_specs()` (`verilog.py`):

- **`mutex`**: one cover per referenced signal (`cover(a)`, `cover(b)`, ...).
  A mutex over a signal that can never go high is vacuous; the cover for that
  signal is unreached and the property is reported FAILED.
- **`invariant` implication form**: `p -> q` spelled `!p | q` (and `q | !p`) or
  `!(p & !q)` (and `!(!q & p)`) → cover `p`. Detected on the AST
  (`gatepack.frontend.expr`), never by string matching.
- **`invariant` with no antecedent**: cover each referenced signal/state, and
  name what was covered in the report.
- **`reachability`/`liveness`**: one cover of the target (unchanged in spirit).

The referenced signals come from `expr_mod.free_vars` / `expr_mod.states_referenced`,
so expression names and `state == NAME` references are handled structurally.

`properties.py` now enumerates **one `mode cover` task per property** (not per
signal) — measured: `mode cover` reaches *every* cover in the design in one run
and reports each one as `Reached ... in step N` / `Unreached ...`. A single run
gives exactly the per-signal reachability the guard needs. `parse_sby` returns a
result per individual cover label; `_combine_property` reports FAILED (vacuous)
if *any* cover is unreached while the assertion passed, and names the offending
signal in the message.

**Measured against real sby**, not reasoned: `tests/fixtures/sby/vacuous_mutex.recorded.log`
is a mutex `!(a & b)` with `b` hardwired low — the assertion proves
(`returned pass for induction` **and** `basecase`), the cover for `a` is
`Reached`, the cover for `b` is `Unreached`, and the whole property is reported
FAILED. That is the exact vacuous-pass failure mode this project exists to stop.

## 2. Liveness is now a bounded check, never a pass

`emit_properties` no longer emits a comment for `kind: liveness`. It emits a
`cover` of the target as **bounded reachability** (§21.5, the review's
"liveness-as-bounded-reachability"), and `_combine_property` reports it
`bounded` with `bound = default_depth(state_count)` (the §21.5 depth), never the
reached step and never `passed`.

Golden designs added: `liveness.yaml` (target reachable → bounded) and
`liveness_violating.yaml` (target unreachable → FAILED), both with recorded sby
logs, plus the end-to-end discharge test in `tests/toolchain/`.

## 3. Two things I found while running real sby (both fixed, both measured)

1. **`mode cover` still checks assertions.** The property-violating golden's
   antecedent cover (`cover(enable)`, which is `state == B`) can only be reached
   through state B, where the assertion `!(enable & fault)` is violated — so the
   cover run reported FAIL for the wrong reason. Fix: asserts are emitted under
   `` `ifdef GP_PROVE `` and covers under `` `ifdef GP_COVER ``; the prove task
   reads `-DGP_PROVE`, the cover task `-DGP_COVER`. Verified: the
   property-violating cover now reaches cleanly while the assertion still fails.

2. **The `.sby` files never actually ran.** The read command used the
   cwd-relative path (`build/generated.v`) inside the `src/` dir where sby
   copies files by basename, so real sby errored `Can't open input file`. Fix:
   read by basename; `[files]` keeps the cwd-relative path. The previous
   `BUILD-NOTES-M6.md` honestly flagged the `.sby` as best-effort/never-run; it
   is now run, and `tests/toolchain/test_real_toolchain.py::test_properties_discharge_end_to_end`
   pins that a correct mutex proves and a vacuous one fails.

## What is guessed / placeholder / weakest

- **Prose liveness (`expr: "all states reach IDLE"`) is a placeholder.** A
  liveness target must be a `to` state or a parseable expression; a prose
  `expr` degenerates to a cover of `1` (trivially bounded). It never reports
  `passed`, but it is not meaningful either. No shipped design uses the prose
  form; flagging for a later milestone rather than silently inventing semantics.
- **Implication detection is conservative.** Only the two-term `!p | q` /
  `!(p & !q)` shapes are recognised. `!a | b | c` is logically `a -> (b | c)`
  but is treated as a general invariant (per-signal covers). This errs toward
  more covers, never toward a silently skipped antecedent.
- **Redundant cover runs.** One cover task per property, but `mode cover`
  reaches every cover in the file, so a 2-mutex design runs the whole cover
  search twice. Correct (per-label matching keeps attribution right) but
  wasteful; a single design-wide cover run is a small future optimisation.
- **An invariant with no referenced signals** (e.g. `expr: "1"`) reports
  `not run` with "no signals; vacuity guard cannot be established" rather than
  `passed`. That is a judgment call: it is trivially true but has no antecedent
  to guard, so I refuse to call it a pass.
- **`parse_vcd` / counterexample pointers** are unchanged from M6 (best-effort;
  multi-bit state vectors stored as bit strings). Not in scope.

## What I could not verify

Nothing in-scope is unverified: every claim above is backed by a real sby run in
`gatepack-toolchain:m6`, recorded into `tests/fixtures/sby/*.recorded.log` and
re-asserted by the parser tests and the end-to-end discharge test.
