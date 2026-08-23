# DFF_SR set-path mutation family — handoff notes

Closes the set-path mutation gap deliberately left open by `resetmut`. Extends
`gatepack/verify/mutation.py` with three set-path mutations and adds the first
bundled example that instantiates `DFF_SR`, so those mutations are real checks
on a real design rather than a `not_applicable`-everywhere null.

## Why this is only now possible

`resetmut` rejected a set-path mutation because no bundled example
instantiated `DFF_SR` — a check that reports `not_applicable` on every design
is indistinguishable from one that does not exist. What changed: an example
with a `binary`/`gray` encoding and a **non-zero initial code** resets its
state vector to that code, so at least one state bit presets to 1 on reset.
The set-only `DFF_S` is single-sourced and excluded from the shipped Liberty,
so the only legalised flop that can preset is `DFF_SR` (`$_DFFSR_PNN_`).
`down_counter` exercises that path and Yosys reaches for `DFF_SR`.

## Files changed

- `examples/down_counter/` — new example (`design.yaml` + a byte-identical
  copy of the shared `parts.csv`/`parts.refs.md`, like every other example).
- `gatepack/verify/mutation.py` — three new `Mutation` entries plus the shared
  `_DFF_SR_FF`/`_DFF_SR_ALWAYS` anchors.
- `tests/unit/test_mutation_dffsr.py` — eight unit tests for the set family.
- `tests/toolchain/test_reset_simulation.py` — three new toolchain tests
  (`detected`, `not_applicable`, distinctness).
- `tests/unit/test_verify.py` — one fixture netlist in
  `test_run_mutation_suite_applicable_undetected_is_a_failure` gained a
  `DFF_SR` instance so that test's `all(o.applicable)` premise still holds now
  that set mutations exist. This is the only edit outside my file scope, made
  because adding the set family broke that test's assumption.

## The example

`down_counter` is a 2-bit **binary** down-counter: `D3 -> D2 -> D1 -> D0 ->
D3`, guarded by `en`, with `initial: D3`. `D3`'s binary code is `2'b11`, so
both state bits preset on reset. It is deliberately a teaching artefact, not a
test fixture: the header explains that "reset" here means "return to the top
of the count", not "clear to zero", and that this is the one example where
the set path (not the clear path) is what reset exercises. It carries the
§1.3 declaration exactly as the other examples do.

Measured through the real container — the mapped netlist instantiates two
`DFF_SR`, each with the clear tied off and the set driven by the synchronised
reset:

```
  DFF_SR _09_ (
    .CK(clk), .D(_02_[0]), .Q(state[0]),
    .RST_N(1'h1), .SET_N(rst_n_s2)
  );
  DFF_SR _10_ (
    .CK(clk), .D(_02_[1]), .Q(state[1]),
    .RST_N(1'h1), .SET_N(rst_n_s2)
  );
```

Full verify (green) through the container:

```
docker run --rm -u "$(id -u):$(id -g)" -v "$PWD:/repo" -w /repo \
  gatepack-toolchain:m6 python3 -m gatepack verify \
  examples/down_counter/design.yaml --library libraries/74aup.csv \
  --build .gpout/dc/notes
```

```
verification: passed
  equivalence:               passed
  exhaustive simulation:     passed
  mutation:                  passed
      all applicable mutations detected or caught by equivalence alone
  flop reset connectivity:   passed
  supervisor parameters:     passed
  mutation nand_to_and:      not applicable
  mutation flop_d_invert:    detected
  mutation reset_polarity_flip: detected
  mutation reset_never_asserts: detected
  mutation reset_becomes_synchronous: detected
  mutation reset_value_flips: detected
  mutation set_never_asserts: detected
  mutation set_becomes_synchronous: detected
  mutation set_value_flips:  detected
```

The reset-family mutations are also `detected` here (the reset de-assert
synchroniser still uses `DFF_R`), and `nand_to_and` is `not applicable`
because the design maps to no `NAND2`.

## Mutations added

Each mirrors a reset-family fault. The shared anchors capture the `DFF_SR` ff
block and always-block once; each mutation supplies its own "after" text, so
the three share the anchor but cannot drift.

| mutation | what it changes | the implementation error it models |
| --- | --- | --- |
| `set_never_asserts` | drops the `preset` line and the `negedge SET_N` event; the cell degrades to clear-only | **the set was never wired** — the set pin is in the netlist but does nothing. Mirror of `reset_never_asserts`. |
| `set_becomes_synchronous` | folds the set into `next_state : "(!SET_N \| D)"` and drops `negedge SET_N`; clear stays async | **async vs sync set mix-up** — §9.3 promises async-assert / sync-de-assert. Mirror of `reset_becomes_synchronous`. |
| `set_value_flips` | `preset : "!SET_N"` -> `clear : "!SET_N"` in the `.lib`, `1'b1` -> `1'b0` in the sim | **wrong set value** (a set-clear confusion). Mirror of `reset_value_flips`. |

The `cells_sim.v` diffs each produces (before = C2-emitted `DFF_SR` model):

```
set_never_asserts
-  always @(posedge CK or negedge RST_N or negedge SET_N) begin
-    if (!RST_N) Q <= 1'b0;
-    else if (!SET_N) Q <= 1'b1;
-    else Q <= D;
+  always @(posedge CK or negedge RST_N) begin
+    if (!RST_N) Q <= 1'b0;
+    else Q <= D;

set_becomes_synchronous
-  always @(posedge CK or negedge RST_N or negedge SET_N) begin
+  always @(posedge CK or negedge RST_N) begin

set_value_flips
-    else if (!SET_N) Q <= 1'b1;
+    else if (!SET_N) Q <= 1'b0;
```

The `.lib` changes: `set_never_asserts` deletes `preset` (and the now-orphaned
`clear_preset_var1`/`var2`); `set_becomes_synchronous` rewrites `next_state`
and deletes `preset`; `set_value_flips` swaps `preset` for `clear` on the set
pin. In every case only the `DFF_SR` entry changes.

### Anchors must not perturb `DFF_R` — and don't

`_DFF_SR_FF`/`_DFF_SR_ALWAYS` contain the `preset`, `clear_preset_var1/var2`
and `else if (!SET_N)` lines that `DFF_R` has none of, so neither collides with
the reset family's anchors. Proven two ways:

- `test_set_family_mutations_leave_dff_r_only_artefacts_byte_identical` builds
  `cells.lib`/`cells_sim.v` from the parts with `DFF_SR` removed and asserts
  every set mutation returns both artefacts **byte-identical**.
- `test_set_family_mutations_target_only_dff_sr` asserts each mutation's
  `targets == ("DFF_SR",)` and that `_DFF_R_FF` survives verbatim.

## Distinctness — three faults, not one spelled three ways

Runs each set mutation against `down_counter`, recompiles with Icarus, and
compares the set of `FAIL:` lines (`test_the_set_family_are_three_distinct_faults`).

| mutation | failure signature (FAIL lines) |
| --- | --- |
| `set_never_asserts` | `c1/c0 at step x` (state stuck at `x`), `during reset`, `held in reset` |
| `set_becomes_synchronous` | `during reset` **only** |
| `set_value_flips` | `c1/c0 at step 0`/`1` (wrong *determinate* code), `during reset`, `held in reset` |

The separating line for each pair:

- **`set_never_asserts` vs `set_becomes_synchronous`** — `held in reset`. A
  synchronous set *does* preset on the held edge (the testbench clocks one edge
  with reset asserted), so only the truly-absent set fails the held check.
- **`set_becomes_synchronous` vs `set_value_flips`** — again `held in reset`
  (present only for the value flip), and the value flip also fails `at step`
  with numeric values.
- **`set_never_asserts` vs `set_value_flips`** — the step value is `x` for the
  former (no set at all leaves the state undefined) and numeric (`0`/`1`) for
  the latter (a set that drives the wrong determinate code). The `at step x`
  line appears in exactly one of the two.

The design that separates all three is `down_counter` itself: its binary
encoding and non-zero reset code make the reset *load a code via the set
path*, so every set fault is observable in a different phase of the reset
assertion.

## Falsification

Each mutation was applied and reverted, in both directions:

- applied -> `detected` (equivalence and exhaustive simulation both fail) —
  the `set_*: detected` lines in the transcript above.
- reverted (unmutated `cells_sim.v`) -> the design verifies green, so the
  `detected` verdict comes from the injected fault, not a pre-broken design.

No mutation is caught "by equivalence only"; all three are `detected`, so
`simulation_was_exercised` is satisfied without relying on any other mutation.

## `not_applicable` is rendered `not_applicable`, never "NOT DETECTED"

`test_set_mutations_not_applicable_on_dff_r_only_design` runs `verify` on
`sequence_detector` (one-hot, `DFF_R` only) and asserts each set mutation
renders as `not applicable`, and that the string `NOT DETECTED` is absent
(M5, defect 3). The CLI path was unchanged; this re-checks it for the new
family.

## Library check

`gatepack lib check libraries/74aup.csv` still reports
`citations: all 26 cells have a 74aup.refs.md entry` (exit 0). No library row
was added or changed — `DFF_SR` was already present.

## Tests

- Before: `778 passed, 5 skipped`.
- After: **`792 passed, 5 skipped`** (+8 unit, +3 toolchain set-family, +3
  toolchain example parameterisations for `down_counter`).

## Three things I am least confident about

1. **The `set_value_flips` Liberty representation.** It produces a `DFF_SR` ff
   group with two `clear` lines (`!RST_N` and `!SET_N`), which is invalid
   Liberty. It is the honest literal mirror of `reset_value_flips` and nothing
   re-reads a mutated `.lib`, but a reviewer (or a future `lib check` that
   starts validating mutated artefacts) may want it expressed differently.
2. **Why the set mutations are `detected` rather than "equivalence only".**
   Measured and solid — the reset-assert probe compares outputs during reset,
   and all three faults change the during-reset output. I am confident the
   simulation catches them; I have not separately proved that equivalence also
   fails for the *structural* reason I would write down (the mutated
   `cells_sim.v` changes the reset state) rather than some coincidence of the
   DFF_SR clear being tied off.
3. **The `set_becomes_synchronous` `next_state : "(!SET_N | D)"` string.** It
   mirrors `"(RST_N & D)"`, and no Liberty consumer in this repo ever reads a
   mutated `.lib`, so the exact boolean is unverified against anything real —
   the same caveat `resetmut` already recorded for the reset sibling.
