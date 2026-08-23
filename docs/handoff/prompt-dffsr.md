# Package H — close the set-path mutation gap

Read `docs/handoff/delegation-rules.md` first. Every rule there applies.

## The gap, and why it was left open on purpose

`gatepack/verify/mutation.py` carries six mutations. Four of them corrupt the
**reset** path of `DFF_R`, and they were built to be four *distinct* faults —
`reset_polarity_flip`, `reset_never_asserts`, `reset_becomes_synchronous`,
`reset_value_flips` — each detectable, each for a different reason.

There is no mutation of the **set** path. A previous package (`resetmut`)
declined to add one, and the reasoning was right: **no bundled example
instantiates `DFF_SR`**, so a set-path mutation would report `not_applicable`
on every design in the repo. A check that is `not_applicable` everywhere is
indistinguishable from a check that does not exist, and this project has shipped
nine pieces of machinery that reported a status while measuring nothing. Adding
it then would have been the tenth.

**What changed is that there is now a cheap way to make it applicable.**
Measured 2026-08-23: `examples/gray_counter` has initial state `G00`, whose code
is 0, so every state bit resets to 0 and `DFF_R` suffices. A probe with
`initial: G11` — code 3, both bits set — verifies green, and the mapped netlist
shows **Yosys reaching for `DFF_SR`**, which *is* in the shipped library
(`74AUP1G74`, second-sourced; only `DFF_S` is excluded, for being
single-sourced).

So: an example with a `binary` or `gray` encoding and a **non-zero initial
code** instantiates `DFF_SR`, and the set-path mutation becomes a real check on
a real design. That is this package.

## What to build

### 1. An example that instantiates `DFF_SR`

A new example under `examples/`, canonical and worth reading, whose initial
state has a non-zero code under `binary` or `gray` encoding. It must be a
teaching artefact like the others, not a test fixture: read
`examples/gray_counter/design.yaml` and `examples/parity/design.yaml` for the
bar — a header comment saying what the circuit is and why it is worth looking
at, and comments that earn their place.

It must carry the §1.3 declaration the others do:

```
# Synthetic, written for this project (§1.3). Nothing here is derived from any
# real product or datasheet application note.
```

That is a statement of fact you are responsible for keeping true.

**Verify that it actually instantiates `DFF_SR`** — do not assume it from the
encoding. Build it through the container and grep the mapped netlist. If Yosys
does not reach for `DFF_SR`, say so and investigate rather than proceeding on
the assumption; the whole package rests on that one fact.

`examples/` currently holds eleven directories and every one verifies green.
Yours must too, and the existing `tests/toolchain/test_examples.py` will hold
you to it — it parameterises over every directory it discovers.

**Do not add a library part.** `DFF_SR` is already in `libraries/74aup.csv`.
If you believe you need a new part, stop and write it up in the notes instead:
every electrical figure in that library is a marked placeholder, and adding a
row you cannot cite is the one thing this project treats as worse than not
shipping the feature.

### 2. The set-path mutations

Mirror the reset family. `DFF_SR` has both a `clear` and a `preset`, so the set
path admits the same three faults the reset path does:

* **`set_never_asserts`** — drop the preset entirely, so the set pin is present
  in the netlist but does nothing. The "somebody forgot to wire it" fault.
* **`set_becomes_synchronous`** — move the preset inside the clock edge, so an
  async-assert set becomes a set only sampled at `posedge CK`. §9.3 promises
  async-assert/sync-de-assert; a suite that cannot tell those apart is not
  verifying that promise.
* **`set_value_flips`** — the set drives 0 instead of 1.

Follow the existing anchor discipline exactly. `_DFF_R_FF` and `_DFF_R_ALWAYS`
are shared anchor strings chosen so each reset mutation corrupts the reset path
**and nothing else**, and the comment above them records that `DFF_SR` has a
`preset` and an `else if` line so neither anchor collides with it. Your `DFF_SR`
anchors must have the same property in reverse: they must not perturb `DFF_R`.
Prove it — a test that applies each new mutation to a design using only `DFF_R`
and asserts the artefacts come back byte-identical.

Target `("DFF_SR",)` only. Do **not** add `DFF_S`: it is excluded from the
library for being single-sourced, so targeting it would reintroduce exactly the
`not_applicable`-everywhere problem this package exists to fix.

### 3. Prove the faults are distinct

The reset family was accepted only after a probe showed the four mutations were
four *different* faults rather than four spellings of one. Do the same here, and
put the table in your notes:

* each new mutation is **`detected`** on your new example (both equivalence and
  simulation fail);
* they are distinguishable — build the design that separates them, and if two of
  them cannot be told apart on any design you can construct, **say so** rather
  than shipping a mutation that adds nothing. That is a finding, not a failure.
* each is **`not_applicable`** on a design with no `DFF_SR` — and
  `not_applicable` is rendered as `not_applicable`, never as "NOT DETECTED".
  That confusion was a real defect once (`M5`, defect 3) and the rendering path
  is worth re-checking.

### 4. Falsify

For each mutation, show the check can fail *and* can pass:

* the mutation applied → `detected`;
* the mutation reverted → the design verifies green.

A mutation that is "detected" because the design was already broken proves
nothing.

## Your file scope — nothing outside it

* `examples/**` (your new directory only)
* `gatepack/verify/mutation.py`
* `tests/unit/test_mutation*.py`, `tests/toolchain/test_examples.py`,
  `tests/toolchain/test_reset_simulation.py` (add to it; do not rewrite it)
* `docs/BUILD-NOTES-dffsr.md`, `docs/handoff/notes-dffsr.md`

**Off-limits**: `libraries/**`, `gatepack/synth/**`, `gatepack/emit/**`,
`gatepack/verify/simulation.py` and `equivalence.py` (unless you can show a
defect there, in which case report it rather than editing), `app/**`,
`scripts/**`. Also always off-limits: `gatepack-design.md`, `docs/*-FINDINGS.md`,
`docs/MILESTONE-AUDIT.md`, `docs/GUI-AUDIT.md`, `app/shared/api.ts`.

## Acceptance

1. `.venv/bin/python -m pytest -q` — **749 pass, 5 skip** at baseline, all still
   passing plus yours.
2. Your example verifies green through the real container, transcript in your
   notes:
   ```
   docker run --rm -u "$(id -u):$(id -g)" -v "$PWD:/repo" -w /repo \
     gatepack-toolchain:m6 bash -c \
     'python3 -m gatepack verify examples/<name>/design.yaml \
        --library libraries/74aup.csv --build /tmp/b'
   ```
3. Evidence — the actual grep — that the mapped netlist contains `DFF_SR`.
4. A test that each new mutation is `detected` on that example, and
   `not_applicable` on a `DFF_R`-only design.
5. A test that each new mutation leaves a `DFF_R`-only design's artefacts
   byte-identical.
6. The distinctness table in your notes, with the design that separates each
   pair.
7. `gatepack lib check` still reports no missing citations.

## Output

`docs/BUILD-NOTES-dffsr.md` and `docs/handoff/notes-dffsr.md`: the example, the
mutations, the distinctness evidence, anything you could not separate, and the
three things you are least confident about.
