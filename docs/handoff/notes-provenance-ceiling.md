# Finding — how well "everything tied together" can actually work

Measured in `gatepack-toolchain:m6` while the two editing packages ran, so it is
an independent baseline for reviewing them.

The §15.2 selection spine is richer than I expected. `resolveSelection` for a
`cell` already returns pointers, nets, minterms, states, transitions *and*
packages — so clicking a gate in the schematic should light the truth table, the
FSM graph and the BOM. Nothing needs adding there.

But all of it routes through the provenance index, and provenance does not cover
every gate. Measured:

| example | coverage | entries | exact | linked cells | linked nets |
|---|---|---|---|---|---|
| sequence_detector | **0.36** | 4 | 4 | 9 | 11 |
| debounce | 0.50 | 6 | 6 | 11 | 14 |
| pelican | 0.87 | 13 | 13 | 15 | 24 |
| power_sequencer | 0.88 | 7 | 7 | 8 | 14 |

Two things to take from it.

**Every link is `exact`.** Not one `inferred` entry across four designs. When a
link exists it is from a surviving `gp_src` attribute, not a structural guess —
so a revealed line is trustworthy.

**Coverage is 36–88%, and the gap is not a defect.** On `sequence_detector` only
9 of 16 cells resolve to a spec construct. The other seven are ABC's own
factoring products (`$abc$133$new_n12_` and friends): they exist because the
optimiser found a shared subexpression, and there is genuinely **no line of
`design.yaml` that produced them**. Inventing a link for those would be
fabricating provenance, which is worse than reporting none.

## What this means for the review

`specAnchor` will return `null` for a large minority of gates — on the showcase
design, closer to half. That is the correct answer, and `prompt-inspedit.md`
already requires it to render as one ("no link", never line 1). This note is the
evidence that the requirement matters in practice rather than in principle: a
reviewer who only tries `pelican` sees 87% and may never hit the case.

So at review, test the null path on **`sequence_detector`**, not on `pelican`.

It also means the honest phrasing in the UI is "this gate came from *no* spec
construct" for an ABC intermediate, distinct from "provenance is unavailable"
when the map itself has not been built. Those are different states and must not
render identically.
