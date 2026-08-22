# BUILD-NOTES — Package C: more bundled examples (examples2)

Scope: `examples/**`, `libraries/74aup.{csv,refs.md}` (unchanged), `tests/unit/test_examples.py`,
`tests/toolchain/test_examples.py` (unchanged), this file, `docs/handoff/notes-examples2.md`.

## What I did

Added five bundled examples, all landing on the existing cell set — **no new
library part, no new row in `libraries/74aup.csv`, no new electrical number.**
That is the §1.3 outcome the task preferred: the existing cells
(`INV BUF AND2 AND3 NAND2 NAND3 NOR2 NOR3 OR2 XOR2 MUX2`, the `DFF` family,
`CNT4`, `SUPERVISOR`, `OSC`) synthesise every one of them.

| example | category | teaches | packages |
|---|---|---|---|
| `full_adder` | purely combinational, multi-output, tiny | `sum = a ^ b ^ cin`, carry = majority, two outputs sharing an XOR; the smallest example | 6 |
| `seven_segment` | purely combinational, multi-output, wide truth table | 7 outputs, 2^4 = 16 rows, each segment a canonical sum of minterms | 26 |
| `gray_counter` | sequential, `encoding: gray` | the one example that uses the non-default `gray` state encoding: a genuine 2-bit Gray cycle | 10 |
| `combination_lock` | sequential, non-trivial state graph | strict 3-digit order with wrong-digit reset, priority-encoded exhaustive guards, a dedicated `relock` | 19 |
| `edge_detector` | sequential, tiny | why detecting a change needs memory; a one-cycle registered pulse | 8 |

Each directory ships `design.yaml`, `parts.csv` (the full 27-row library, copied
verbatim, matching `parity`/`mux2to1`/etc.) and `parts.refs.md` (the full refs,
copied verbatim). No example ships a `.gpk`. Each `design.yaml` carries the
§1.3 synthetic-declaration comment, and the first non-empty comment line is a
real one-liner that `gatepack examples list` picks up.

## Why no new parts

Every example was written to land on the shipped cells, and each verified green
with the full library. I had no datasheet open (and could not name a document
revision for anything new), so per `libraries/74aup.refs.md` I had no licence to
add a part at all. Adding one would have meant either fabricating a citation
(forbidden) or adding yet another placeholder row — a cost, not an achievement,
when the existing set already covers every design here.

Because I added **no** parts, acceptance #6 ("a test asserting its row is marked
placeholder") is intentionally not met — there is no new row to guard. The
existing guard `test_example_parts_csv_rows_are_verbatim_from_the_library` still
pins that every example's `parts.csv` is a byte-verbatim subset of
`libraries/74aup.csv`, so a future example cannot smuggle in a new cell without
also editing the shared library (and its refs).

## Verification (real toolchain, `gatepack-toolchain:m6`)

Command (one per example, per the task):

```
docker run --rm -u "$(id -u):$(id -g)" -v "$PWD:/repo" -w /repo gatepack-toolchain:m6 \
  bash -c 'python3 -m gatepack verify examples/<name>/design.yaml --library libraries/74aup.csv --build /tmp/b_<name>'
```

Every one reports `verification: passed`, with equivalence, exhaustive
simulation and the mutation suite all passing. Full transcripts:

### full_adder — 6 packages

```
verification: passed
  equivalence:               passed
  exhaustive simulation:     passed
  mutation:                  passed (all applicable mutations detected)
  flop reset connectivity:   passed
  supervisor parameters:     passed
  mutation nand_to_and:      detected
  mutation flop_d_invert:    not applicable
  mutation reset_polarity_flip: not applicable
  mutation reset_never_asserts: not applicable
  mutation reset_becomes_synchronous: not applicable
  mutation reset_value_flips: not applicable
```

Purely combinational, so the four flop/reset mutations are `not applicable`
(category errors kept out of the vacuity verdict); `nand_to_and` is applicable
and detected by both equivalence and simulation.

### seven_segment — 26 packages

```
verification: passed
  equivalence:               passed
  exhaustive simulation:     passed
  mutation:                  passed
  flop reset connectivity:   passed
  supervisor parameters:     passed
  mutation nand_to_and:      detected
  mutation flop_d_invert:    not applicable
  mutation reset_polarity_flip: not applicable
  mutation reset_never_asserts: not applicable
  mutation reset_becomes_synchronous: not applicable
  mutation reset_value_flips: not applicable
```

Same shape as `full_adder` (combinational). 16 input vectors, all exhaustive.

### gray_counter — 10 packages

```
verification: passed
  equivalence:               passed
  exhaustive simulation:     passed
  mutation:                  passed
  flop reset connectivity:   passed
  supervisor parameters:     passed
  mutation nand_to_and:      detected
  mutation flop_d_invert:    detected
  mutation reset_polarity_flip: detected
  mutation reset_never_asserts: detected
  mutation reset_becomes_synchronous: detected
  mutation reset_value_flips: detected
```

All six mutations applicable and detected. `encoding: gray` puts the state on
the `gray` path (`_emit_encoded_state`), which none of the other examples
exercises.

### combination_lock — 19 packages

```
verification: passed
  equivalence:               passed
  exhaustive simulation:     passed
  mutation:                  passed
  flop reset connectivity:   passed
  supervisor parameters:     passed
  mutation nand_to_and:      detected
  mutation flop_d_invert:    detected
  mutation reset_polarity_flip: detected
  mutation reset_never_asserts: detected
  mutation reset_becomes_synchronous: detected
  mutation reset_value_flips: detected
```

### edge_detector — 8 packages

```
verification: passed
  equivalence:               passed
  exhaustive simulation:     passed
  mutation:                  passed
  flop reset connectivity:   passed
  supervisor parameters:     passed
  mutation nand_to_and:      not applicable
  mutation flop_d_invert:    detected
  mutation reset_polarity_flip: detected
  mutation reset_never_asserts: detected
  mutation reset_becomes_synchronous: detected
  mutation reset_value_flips: detected
```

`nand_to_and` not applicable (the mapped netlist has no NAND2); the five
flop/reset mutations are detected.

## What I could not source, and how I marked it

Nothing new to mark. No electrical or packaging value was added anywhere. The
`parts.csv` files I copied into the example directories are byte-identical to
`libraries/74aup.csv`, whose every electrical figure is already declared a
placeholder in `74aup.refs.md`; that status is inherited unchanged. The only
numbers I typed into any new file are design parameters (clock `freq_hz`,
`constraints.vcc` defaults) and the seven-segment minterm table — the former are
nominal by design (they already are in every other example), the latter is
logic, not an electrical measurement.

## Tests added

In `tests/unit/test_examples.py` (both iterate, never a hand-written list):

1. `test_every_example_library_contains_the_cells_its_design_names` — the
   toolchain-free half of acceptance #4's "`parts.csv` and `design.yaml` disagree
   about which cells exist". Compiles each design and asserts `reset.source` and
   every `macros[].cell` name a cell present in that example's `parts.csv`. The
   Yosys half of that agreement is already pinned by
   `tests/toolchain/test_examples.py::test_every_example_builds_with_its_own_project_library`,
   which builds each example against its own library (and now covers the 5 new
   ones automatically).
2. `test_seven_segment_matches_the_reference_glyph_table` — the "check that can
   fail" for the decoder. `gatepack verify` proves synthesis matches the spec,
   **not** that the spec matches a human's idea of the digit shapes; a wrong
   minterm verifies as green as a right one. This test evaluates each of the 7
   segment ASTs over all 16 codes against an independent reference written as
   on-segment letter strings (`0x6 -> "acdefg"`), a different representation than
   the minterms in the YAML, so a transcription slip in either shows up.

`tests/toolchain/test_examples.py` is unchanged; it parametrises over
`list_examples()`, so the 5 new examples are exercised by the existing
build / project-library-build / verify tests the moment they land.

## Test counts

- Baseline: **723 passed, 5 skipped**.
- After: **740 passed, 5 skipped** (+2 unit tests, +15 toolchain tests = 5 new
  examples × 3 existing parametrised tests).

`gatepack lib check libraries/74aup.csv` still reports
`citations: all 26 cells have a 74aup.refs.md entry` (exit 0) — no missing
citations, because no cell was added.

## Least confident about

1. **The seven-segment glyph table.** I am confident it is the standard hex
   glyph table, but I could not check it against any datasheet (none was in
   scope, and the environment has no network). The unit test above is what
   makes a *transcription* error in the SOP fail; it cannot distinguish a
   correct transcription of a wrong table. This is a textbook glyph, common
   property, but it is the one place a human could disagree about "is that an
   A or a 9" and I have no external authority to cite.
2. **`encoding: gray` interactions.** `gray_counter` is the first example to
   use the `gray` encoding. It verifies green end-to-end, and the reset value
   (initial state = code 0) matches a reset-to-0 flop, but I have not reasoned
   through every corner (e.g. an initial state whose gray code is non-zero
   would reset to a code the `DFF_R` flops cannot load — see the suspicion
   below).
3. **The `combination_lock` "relock ignored while closed" choice.** This is a
   semantic decision I made to keep the guards exhaustive and clean; a real
   lock would probably cancel a partial entry on relock. It is documented in
   the header, but it is a guess about what a good teaching example should do,
   not a fact.

## Suspicions recorded (not investigated — out of scope)

- `gatepack/frontend/verilog.py::_emit_encoded_state` loads `STATE_initial` on
  reset for binary/gray encodings, but the flops are reset-to-0 `DFF_R` cells.
  An initial state whose encoded code is non-zero would emit a reset value the
  library cannot physically reset to; `gray_counter` happens to use code 0 so it
  is fine, but that looks like a latent gap worth a test of its own.
