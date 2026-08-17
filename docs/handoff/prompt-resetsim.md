# Package: the exhaustive simulation never looks at the reset

You are a verification engineer who has written self-checking testbenches for
real silicon, and who knows that a reset which is never observed is a reset
which is never verified.

## The project

`gatepack` compiles a truth table or FSM specification into a bill of materials
and a schematic netlist built from discrete 74AUP logic packages, formally
verifying the result on every build. `gatepack/verify/` holds the checks:
formal equivalence (Yosys `equiv_induct`), exhaustive simulation (Icarus, every
reachable state × input transition), a mutation suite that proves those two are
not vacuous, and sby property checks.

## The defect

`gatepack/verify/simulation.py` treats reset as a **setup step**. Read
`build_testbench` and `_stimulus`: each trace asserts reset, releases it, runs
three clock edges to flush the de-assert synchroniser, and only *then* begins
comparing outputs — and it compares them only immediately after a clock edge.
**No output is ever compared while reset is asserted.**

So the simulation cannot see a broken reset. This is not a theory; it is
measured. `docs/handoff/notes-pins.md` records the probe. The
`reset_polarity_flip` mutation rewrites the `DFF_R` clear condition from
`if (!RST_N)` to `if (RST_N)`, and with that mutation in place:

```
=== RESET MUTATED ===
during reset assert:       ... S3=1 match=1     <- fault: reset did not clear
```

`match` is stuck high while reset is asserted — the fault is plainly observable
at a primary output — and the exhaustive simulation passes anyway. It is caught
only by the equivalence check, so the mutation suite reports it as *caught by
equivalence only*, which is an honest description of a real coverage gap.

Close the gap.

## What the design actually says the outputs should be during reset

Do not guess this, and do not invent an expectation to make a test pass. Derive
it from the emitter, which is `gatepack/frontend/verilog.py`. For the one-hot
path (`_emit_one_hot_state`) the reset branch is:

```verilog
if (!rst_n) begin
  state_S0 <= 1'b0; state_S1 <= 1'b0; ...   // every state bit
end
```

Every one-hot bit clears, so **while reset is asserted no state is active** —
`state == S3` is false, and so is every other state predicate. That is why
`sequence_detector`'s `match: "state == S3"` must read 0 during reset, and why
the mutated design reading 1 is a genuine mismatch and not a modelling artefact.
The initial state is not loaded until the third clock edge after release
(set-via-feedback, M0-FINDINGS §6 option 2) — so "during reset" and "in the
initial state" are *different* conditions with potentially different outputs,
and conflating them will produce a testbench that fails on correct designs.

`_emit_encoded_state` (binary encoding) is a separate path and its reset value
is a different thing — an all-zero state code may well *be* a real state there.
Read it and work out what the expected outputs are on that path too. If the two
paths need different treatment, give them different treatment; if you conclude
one of them cannot be checked honestly, say so in your notes and leave it
unchecked rather than asserting something you cannot derive.

Also settle what happens to the **input synchronisers** on reset (§9.3, and
`_ReferenceDesign` in `simulation.py` explicitly says it does not model the
reset path). If they clear asynchronously too, the effective sync-input values
during reset are 0 and an output expression that reads a sync input must be
evaluated accordingly; a non-`sync` input passes through combinationally and
keeps whatever the testbench is driving. `sequence_detector`'s `din` is
`sync: false`, so it is the second case. Get this right from the emitted
Verilog, not from memory.

## What to build

Two properties, both currently unverified by simulation:

1. **Reset assertion drives the specified outputs.** From a *reachable* state —
   not only from power-on — assert reset and compare every output against what
   the specification says it must be while reset is asserted. Driving from a
   reachable state is the whole point: the probe above only shows the fault
   because the machine was in `S3` when reset arrived.

2. **The reset is asynchronous.** It must take effect *without* a clock edge.
   Assert reset while the clock is low and compare outputs **before** the next
   rising edge. A design that implemented a synchronous reset would pass a
   post-edge check and fail this one, which is exactly the distinction worth
   having — `gatepack` promises async-assert / sync-de-assert (§9.3).

Extend `_ReferenceDesign` so it models the reset phase, and extend `_stimulus`
and `build_testbench` to emit and check these. Keep the existing stimulus
working: the reset flush is exactly three edges and the comment above it
explains, at length, why a fourth edge is a real mismatch rather than harmless
margin. Read that comment before you touch the flush.

Consider cost. `_stimulus` already emits a trace per reachable (state, settled
input) pair; adding a full reset probe to *every* trace may blow the runtime
cap. One reset probe per reachable state is likely enough to catch a reset
fault — decide, implement, and say in your notes what you chose, what it costs,
and what a fault would have to look like to slip past your choice.

## The acceptance criterion

This one is objective, so there is no room to declare success by narration:

```
docker run --rm -u "$(id -u):$(id -g)" -v "$PWD:/repo" -w /repo \
  gatepack-toolchain:m6 python3 -m gatepack verify \
  examples/sequence_detector/design.yaml \
  --library examples/sequence_detector/parts.csv
```

`reset_polarity_flip` must move from **caught by equivalence only** to
**detected**. Quote the real before and after.

**You may not reach that by touching the verdict logic.** `mutation.py`,
`base.py` and `synchronous.py` are out of scope for this package (another agent
owns `mutation.py` right now). The verdict must change because the simulation
genuinely started failing on the mutated design — nothing else counts. If you
find yourself wanting to edit how a verdict is computed, stop and write it in
your notes instead.

Equally: `nand_to_and` on this design is a *different* case. The notes argue it
is genuinely unobservable — the mutated gate's output cannot differ at a primary
output in any reachable state. If your change also flips that one to `detected`,
that is very interesting and you must investigate rather than celebrate: either
the notes' reachability argument is wrong, or your new stimulus is checking
something the specification does not actually require.

## Prove it

The toolchain is **not on your PATH**; it is in `gatepack-toolchain:m6`, already
built on this machine. `tests/toolchain/docker_runner.py` builds the command
with `-u` for you — use it in tests.

Required, with real output quoted in your notes:

1. The before/after mutation verdict above.
2. **Every** bundled example under `examples/` still verifies — all checks pass,
   no acknowledgement flag. A new testbench that fails on a *correct* design is
   the obvious way to get this wrong, and six examples is the sample that
   catches it. Quote the per-example result.
3. A unit test that fails without your change. Build the mutated `cells_sim.v`
   by hand if you must, but demonstrate the new stimulus catching a reset fault,
   and quote the failure output. **A check you have not falsified is not
   evidence** — this project has shipped nine pieces of machinery that reported
   a status while measuring nothing.
4. `.venv/bin/python -m pytest tests -q` — count before and after.
5. The exhaustive-simulation runtime for the showcase (`pelican`, 5 states)
   before and after, so the cost of the extra stimulus is on the record.

## Files you own

`gatepack/verify/simulation.py`, and tests under `tests/unit/` and
`tests/toolchain/`.

Do **not** touch `gatepack/verify/mutation.py`, `gatepack/verify/base.py` or
`tests/unit/test_verify.py` — another agent is editing those right now. Do not
modify `gatepack/frontend/**` (read it, that is where your answers are),
`libraries/**`, `examples/**` or `app/**`. If you find a defect outside your
scope, report it in your notes rather than fixing it.

## The rules that govern this repo

Read `docs/handoff/delegation-rules.md` — all of it applies. The two that have
killed previous runs:

- **Never touch any path outside the project directory — reads included.** A
  refusal ends the run mid-task. Use `.gpout/` inside your worktree for scratch.
- **Never fake a tool result, and do not commit.** Leave the work in the tree.

## Report

Write `docs/handoff/notes-resetsim.md`: what the emitter says the outputs are
during reset and on which path, what you modelled and what you deliberately did
not, the before/after mutation verdict, the falsification, the runtime cost, the
per-example results, and anything you could not settle.
