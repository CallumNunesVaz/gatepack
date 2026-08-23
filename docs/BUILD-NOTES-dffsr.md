# BUILD NOTES — dffsr: close the set-path mutation gap

Full report: `docs/handoff/notes-dffsr.md`.

## What was implemented

- `examples/down_counter/` — a new bundled example, a 2-bit binary down-counter
  (divide-by-4 prescaler) that resets to `D3` (code `2'b11`). Its non-zero
  initial code forces both state bits to preset to 1 on reset, which is what
  makes Yosys reach for `DFF_SR` (the set-only `DFF_S` is single-sourced and
  excluded, so `$_DFFSR_PNN_` is the only legal flop that can preset). Verified
  through the real container: the mapped netlist instantiates two `DFF_SR`.
- `gatepack/verify/mutation.py` — three new set-path mutations mirroring the
  reset family, all pure text transforms on `cells.lib` + `cells_sim.v`,
  all targeting `DFF_SR` only: `set_never_asserts`,
  `set_becomes_synchronous`, `set_value_flips`. Anchors (`_DFF_SR_FF`,
  `_DFF_SR_ALWAYS`) are the mirror of the reset anchors and provably do not
  perturb `DFF_R`.

## Tests

- `tests/unit/test_mutation_dffsr.py` (8) — pins the transforms, that each
  changes both artefacts, targets only `DFF_SR`, leaves a `DFF_R`-only library
  byte-identical, and is `not_applicable` without `DFF_SR`.
- `tests/toolchain/test_reset_simulation.py` (+3) — each set mutation is
  `detected` on `down_counter` and `not applicable` on a `DFF_R`-only design
  (rendered as `not applicable`, never "NOT DETECTED"); the three are distinct
  faults with three distinct Icarus failure traces.
- `tests/unit/test_verify.py` — one fixture netlist extended with a `DFF_SR`
  instance so `test_run_mutation_suite_applicable_undetected_is_a_failure`
  still holds now that set mutations exist (see notes).

```
.venv/bin/python -m pytest -q
# 792 passed, 5 skipped  (baseline 778 passed, 5 skipped)
```

## What I guessed / assumptions

- `set_value_flips` is represented in the Liberty file by swapping
  `preset : "!SET_N"` for `clear : "!SET_N"`, which leaves the `DFF_SR` ff
  group with *two* `clear` lines. That is invalid Liberty, but the mutated
  `.lib` is never re-parsed by any check (only `cells_sim.v` is read), and it
  is the honest literal "set now drives 0" mirror of `reset_value_flips`.
- `set_becomes_synchronous` folds the set into `next_state : "(!SET_N | D)"`,
  the same unverified-against-a-Liberty-consumer representation the reset
  family already used.

## What could not be verified / is weakest

- Nothing here re-reads a mutated Liberty file, so the `.lib` half of each
  mutation is exercised only by the "both artefacts change" test, not by any
  check that parses it. That is inherited from the reset family, not new.
- `down_counter` wires `DFF_SR` as `.RST_N(1'h1)` (clear tied off) and
  `.SET_N(rst_n_s2)` (set driven by the synchronised reset). Only the *set*
  path is live; the `DFF_SR` clear path is exercised by no bundled example,
  which is exactly the point of this package and worth remembering if a future
  design drives both pins.
