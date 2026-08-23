# Package K — the asynchronous backend becomes reachable

Read `docs/handoff/delegation-rules.md` first. Every rule there applies.

## The state of play

`gatepack/synth/async_/` implements §7.3's constrained asynchronous synthesis in
five stages, and `gatepack/verify/hazard.py` verifies hazard-freedom
independently of it (see `docs/BUILD-NOTES-async.md` and `[M7-1]` in the design
doc). It is tested — 40 tests, three of them against real z3 and Icarus.

**And it is unreachable.** `gatepack/frontend/frontend.py` still raises
`AsyncRefused` for every asynchronous design, now after running stage-1
admission so the message names the construct at fault. So a user running
`gatepack verify` on an async design gets a refusal, and the backend delivers
nothing. M7 is recorded as **partial** for exactly this reason.

Your job is to wire it, without weakening the one rule the component has.

## The rule that outranks the task

> "A netlist that is formally equivalent and hazardous on the bench is the worst
> possible output of this tool — worse than no output, because it survives
> review." (§7.3)

Concretely, and this is the whole package:

**No asynchronous netlist may be written to disk, returned to a caller, or
reported as a result unless stage 5 has run on it and passed.** Not "should
not". The binding must be structural — it must not be possible to obtain an
async netlist through a public entry point without the hazard checks having run.

Today that binding is a convention: `AsynchronousBackend.synthesize()` returns a
netlist and `AsynchronousVerify` is a separate strategy, so a future caller can
use the first without the second and nothing stops them. Fix that as part of
this work — a single pipeline entry point that runs stages 1–4 then stage 5 and
**raises** on failure, with `synthesize()` demoted to internal. Beware the import
cycle: `gatepack/verify/asynchronous.py` already imports from
`gatepack/synth/async_/`, so the pipeline probably belongs in a third module
rather than inside either one.

## What to wire

Work out from the code which of these the CLI actually needs; do not assume the
list is complete or that every item is appropriate:

* `gatepack verify` — the async path runs equivalence where it is meaningful,
  the hazard checks always, and reports each as its own check with its own
  status. A hazard failure is a **failed verification**, never a warning.
* `gatepack build` — emits the netlist, BOM and KiCad netlist only past a passed
  hazard check. If the packer, emitters or report make synchronous assumptions
  (a clock net, flop counts, §9.3 reset structure), find out rather than guess,
  and **refuse with the reason** where an assumption does not hold. A BOM built
  on a synchronous assumption from an asynchronous netlist is a wrong BOM.
* `gatepack estimate` — decide whether it can answer for an async design at all.
  "It cannot, and here is why" is an acceptable and useful answer.
* The report (§C8) must state, every time: fundamental mode assumed, which
  inputs were declared mutually exclusive, the assignment width and whether
  spares were added, the maximum product-term literal count, and both hazard
  checks per transition. Also that the guarantee does **not** extend to
  concurrent input changes, and that the privileged-cube condition is not
  enforced, so dynamic hazards are not covered by construction.

## The refusals are half the deliverable

Every stage that can refuse already does, naming the construct at fault. Those
messages must reach the CLI user intact — not flattened into "asynchronous
synthesis failed". Test that the specific text survives the whole path from
stage to terminal.

## An end-to-end example

`tests/golden/designs/async_latch.yaml` synthesises and passes both hazard
checks. Add a **bundled example** under `examples/` for it, to the standard the
others meet — read `examples/parity/design.yaml` for the bar — carrying the §1.3
synthetic declaration, and make it verify green through the container. The
existing `tests/toolchain/test_examples.py` parameterises over every directory it
discovers, so it will hold you to that automatically.

This is the acceptance test that matters: **an asynchronous design in
`examples/` that a user can run `gatepack verify` on and get a real verdict.**

## Your file scope — nothing outside it

* `gatepack/frontend/frontend.py`, `gatepack/cli.py`
* `gatepack/synth/asynchronous.py`, `gatepack/synth/async_/**`
* `gatepack/verify/asynchronous.py`, `gatepack/verify/run.py`
* `gatepack/async_pipeline.py` (new, or wherever the cycle analysis puts it)
* `gatepack/build.py`, `gatepack/report/**` — **only** to add async handling or a
  refusal; do not change synchronous behaviour
* `examples/<your async example>/**`
* `tests/unit/test_async_*.py`, `tests/toolchain/test_async_*.py`,
  `tests/contract/**`
* `docs/BUILD-NOTES-asyncwire.md`, `docs/handoff/notes-asyncwire.md`

**Off-limits**: `gatepack/verify/hazard.py` — it is the independent verifier and
must stay independent; if it needs a change, say so in the notes and explain why
rather than editing it. Also `gatepack/synth/synchronous.py`, `gatepack/pack/**`,
`libraries/**`, `app/**`, and as always `gatepack-design.md`,
`docs/*-FINDINGS.md`, `docs/MILESTONE-AUDIT.md`, `docs/GUI-AUDIT.md`,
`app/shared/api.ts`.

## Acceptance

1. `.venv/bin/python -m pytest -q` — measure the baseline yourself before you
   start; every existing test still passes plus yours. **The synchronous path
   must be untouched**, and those tests are your evidence.
2. A test that the async pipeline **cannot** yield a netlist without the hazard
   checks having run — construct the attempt and assert it raises.
3. A test that a hazard-failing design produces a *failed verification* through
   the CLI, and that no netlist file is written.
4. A test per refusal that the specific construct name reaches the CLI output.
5. Your async example verifies green through the container, transcript in the
   notes:
   ```
   docker run --rm -u "$(id -u):$(id -g)" -v "$PWD:/repo" -w /repo \
     gatepack-toolchain:m6 bash -c \
     'python3 -m gatepack verify examples/<name>/design.yaml \
        --library libraries/74aup.csv --build /tmp/b'
   ```
6. Two clean builds of it are byte-identical (`scripts/repro_check.py`, §5.5).

## The failure mode to avoid

The version here is a wired-up path that emits a netlist when the hazard check
was skipped, errored, or was never reachable for that design — and reports
`verification: passed` beside it. That is the ninth failure this project has
already had, with a glitch on a bench at the end of it. **If you cannot make the
binding structural, wire nothing and say so.**

## Output

`docs/BUILD-NOTES-asyncwire.md` and `docs/handoff/notes-asyncwire.md`: what you
wired, what you refused to wire and why, where the synchronous assumptions bit,
and the three things you are least confident about.
