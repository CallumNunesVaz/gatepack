# Handoff notes — Package C (more bundled examples)

Added five examples, no new library parts. See `docs/BUILD-NOTES-examples2.md`
for the full write-up; this is the handoff summary.

## What I added

| example | category | packages |
|---|---|---|
| `full_adder` | combinational, multi-output, tiny (sum + carry) | 6 |
| `seven_segment` | combinational, 7 outputs, 16-row truth table, SOP minterms | 26 |
| `gray_counter` | sequential, `encoding: gray` (only example using it) | 10 |
| `combination_lock` | sequential, non-trivial graph, 3-digit order + relock | 19 |
| `edge_detector` | sequential, tiny, registered pulse | 8 |

Each ships `design.yaml` + `parts.csv` (full 27-row library, verbatim) +
`parts.refs.md` (verbatim), matching the existing non-showcase examples. No
`.gpk`. Each carries the §1.3 synthetic declaration and a real one-line summary.

## Verify transcripts (real toolchain, `gatepack-toolchain:m6`)

All five report `verification: passed` — equivalence, exhaustive simulation and
the mutation suite all pass; none is above the exhaustive-simulation cap (largest
is 4 states × 8 inputs = 32 vectors). Per example, the distinguishing lines:

- `full_adder` / `seven_segment`: combinational, so the four flop/reset
  mutations are `not applicable`; `nand_to_and` is `detected`.
- `gray_counter`, `combination_lock`: all six mutations `detected`.
- `edge_detector`: `nand_to_and` not applicable (no NAND2), the five flop/reset
  mutations `detected`.

Full transcripts and the `docker run` command are in
`docs/BUILD-NOTES-examples2.md`.

## Numbers I could not source, and how I marked them

None added. No new part, no new row in `libraries/74aup.csv`, no new electrical
or packaging value anywhere. The copied `parts.csv` files inherit the library's
existing placeholder status unchanged. Design parameters (clock `freq_hz`,
default `vcc`) are nominal by design, as in every other example.

## Tests

- `tests/unit/test_examples.py`: +2 —
  `test_every_example_library_contains_the_cells_its_design_names` (toolchain-free
  half of the "parts.csv vs design.yaml agree" acceptance) and
  `test_seven_segment_matches_the_reference_glyph_table` (the "check that can
  fail" — proves the decoder matches the textbook glyphs, which the tool itself
  cannot).
- `tests/toolchain/test_examples.py`: unchanged; it parametrises over
  `list_examples()` so the 5 new examples are covered automatically.
- Counts: 723→**740 passed**, 5 skipped.

`gatepack lib check` still reports all 26 cells cited (no missing citations).
No part was added, so the "assert the new row is placeholder" acceptance is N/A
by design.

## Least confident about

1. The seven-segment glyph table is standard to me but has no datasheet
   authority in scope; the unit test catches transcription slips, not a wrong
   table.
2. `encoding: gray` is exercised here for the first time; it verifies green but
   I did not exhaust the encoding's reset-corner cases.
3. `combination_lock`'s "relock is ignored while closed" is a teaching choice,
   not a fact about real locks.
