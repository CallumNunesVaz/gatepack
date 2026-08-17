# Package: one reset mutation is not a reset mutation suite

You are a verification engineer who treats the mutation suite as the only thing
standing between this project and a proof that proves nothing.

## The project

`gatepack` compiles a truth table or FSM specification into a bill of materials
and a schematic netlist built from discrete 74AUP logic packages, formally
verifying the result on every build. `gatepack/verify/mutation.py` injects
deliberate faults into the generated `cells.lib` and `cells_sim.v` and asserts
that the equivalence and exhaustive-simulation checks **fail**. That suite is
what distinguishes a real proof from a misconfiguration: an equivalence check
that passes vacuously is worse than no check, because it survives review.

Read the `mutation.py` docstring first. It is long and it is the specification
for this package — particularly the three verdicts (*detected*, *caught by
equivalence only*, *undetected*) and why the middle one is named for what was
observed rather than for a cause.

## The defect

`MUTATIONS` has exactly three entries, and only **one** of them
(`reset_polarity_flip`) touches the reset at all. The reset path is where this
project's worst historical bugs have lived — M6-FINDINGS §2 is a missing reset
assumption that made every property pass vacuously — and it is covered by a
single fault injection.

A one-fault family cannot distinguish "the checks catch reset faults" from "the
checks catch *this* reset fault".

## What to build

Extend the reset mutation family. Each new mutation must be a fault that a
plausibly-wrong implementation would actually have, must be a pure text
transform on the generated `cells.lib` / `cells_sim.v` (that is the existing
mechanism — do not invent a second one), and must declare `targets` honestly so
it reports `not_applicable` on designs that do not instantiate the cell.

Candidates worth your judgement, not a checklist to implement blindly:

- **The reset never asserts** — drop the clear entirely, so the flop is a plain
  `DFF`. This is the "somebody forgot to wire the reset" fault, and it is
  distinct from flipping its polarity.
- **The reset becomes synchronous** — move the clear inside the clock edge.
  `gatepack` promises async-assert / sync-de-assert (§9.3); a synchronous reset
  is a real and common implementation error, and a check suite that cannot tell
  the two apart is not verifying the promise.
- **The reset value flips** — clear to 1 instead of 0. On the one-hot path
  (`gatepack/frontend/verilog.py::_emit_one_hot_state`) every state bit clears
  to 0 on reset, so a flop that reset to 1 would leave every state
  simultaneously active. Work out whether that is observable and where.
- **The set/preset path on `DFF_SR`/`DFF_S`**, which no mutation touches today.

Take the ones you can justify. A mutation you cannot explain the physical
meaning of is not worth adding, and **fewer, well-argued mutations beat a long
list**. For each one you add, say in your notes what real implementation error
it stands for.

Consider also whether `MUTATIONS` being a flat module-level tuple is the right
shape now — the suite runs every mutation against every design, and each one
costs a full equivalence run plus a full simulation run. If the cost is
material, measure it and say so; do not restructure on a hunch.

## The verdict each new mutation gets is a finding, not a target

**A second agent is, in parallel, extending the exhaustive simulation to check
the reset-assertion phase** (`gatepack/verify/simulation.py` —
`docs/handoff/prompt-resetsim.md`). Until that work lands, the simulation is
reset-blind by construction, so several of your new mutations will legitimately
come back as **caught by equivalence only**: equivalence sees the fault, the
simulation does not look.

That is the correct result and you must report it as measured. Specifically:

- **Do not weaken anything to turn an "equivalence only" into a "detected".**
  Not the verdict functions, not `simulation_was_exercised`, not a mutation's
  `targets` list, not an assertion in a test.
- If a new mutation comes back **undetected** — equivalence *passed* with the
  fault in place — that is a hard failure and the most valuable thing you could
  find in this package. Do not smooth it over. Investigate it, establish whether
  the fault is genuinely unobservable or the equivalence check is insensitive,
  and write down which and why, with the evidence.
- If a mutation does not change either artefact (the text substitution missed),
  the existing code already reports `applicable=False` with "mutation did not
  change either artefact". Make sure your new mutations actually match the
  generated text — run them and check, because a mutation whose `str.replace`
  silently no-ops is a check that measures nothing while looking green. Add a
  test that would catch that for every mutation in `MUTATIONS`, including the
  three that already exist.

## Prove it

The toolchain is **not on your PATH**; it is in the docker image
`gatepack-toolchain:m6`, already built on this machine. Always pass `-u`:

```
docker run --rm -u "$(id -u):$(id -g)" -v "$PWD:/repo" -w /repo \
  gatepack-toolchain:m6 python3 -m gatepack verify \
  examples/sequence_detector/design.yaml \
  --library examples/sequence_detector/parts.csv
```

Required, with real output quoted in your notes:

1. The full mutation table for at least `sequence_detector` (sequential,
   one-hot, has `DFF_R`) and `pelican` (the five-state showcase) — every
   mutation and its measured verdict.
2. At least one **combinational** example (`parity`, `mux2to1`) showing the new
   reset mutations reporting `not_applicable` rather than failing. A mutation
   that fails on a design with no flops is a category error, and the docstring
   says so.
3. For each new mutation, the diff it produces on the generated `cells_sim.v` —
   the actual before/after lines — proving the substitution fires.
4. `.venv/bin/python -m pytest tests -q` — count before and after.

## Files you own

`gatepack/verify/mutation.py` and `tests/unit/test_verify.py`.

`gatepack/verify/base.py` and `gatepack/verify/synchronous.py` are **read-only
for you**: if you conclude a change is needed there — a new verdict field, a
change to how the check result is summarised — write the argument in your notes
and leave the code alone. Those files carry the verdict logic and the last
package to touch them needed two rounds of correction.

Do **not** touch `gatepack/verify/simulation.py` — the other agent is rewriting
it right now. Do not modify `gatepack/frontend/**`, `libraries/**`,
`examples/**` or `app/**`.

## The rules that govern this repo

Read `docs/handoff/delegation-rules.md` — all of it applies. The two that have
killed previous runs:

- **Never touch any path outside the project directory — reads included.** A
  refusal ends the run mid-task. Use `.gpout/` inside your worktree for scratch.
- **Never fake a tool result, and do not commit.** Leave the work in the tree.

## Report

Write `docs/handoff/notes-resetmut.md`: each mutation you added and the real
implementation error it stands for, each one you considered and rejected and
why, the measured verdict table, the `cells_sim.v` diffs, anything that came
back `undetected` and what you established about it, and the three things you
are least confident about.
