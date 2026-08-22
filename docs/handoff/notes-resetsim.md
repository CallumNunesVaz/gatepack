# Handoff notes — resetsim: the exhaustive simulation never looked at the reset

The exhaustive simulation treated reset as a §9.6 *setup step*: it asserted
reset, released it, flushed three clock edges, and only then compared outputs —
at transition edges only. **No output was ever compared while reset was
asserted**, so a reset that failed to clear the state was invisible to it.
This run closes that gap.

## What the emitter says the outputs are during reset

Derived from `gatepack/frontend/verilog.py`, not guessed, and not from memory.
The two encoding paths genuinely differ, and I treat them differently.

### one-hot (`_emit_one_hot_state`)

The reset branch clears *every* state bit:

```verilog
if (!rst_n) begin
  state_S0 <= 1'b0; state_S1 <= 1'b0; ...   // every state bit
end
```

So **while reset is asserted no state is active** — every `state == S`
predicate is false. The initial state is *not* loaded until the third clock
edge after release (set-via-feedback, M0-FINDINGS §6 option 2). So "during
reset" and "in the initial state" are different conditions with different
outputs. For `sequence_detector`, `match = (state == S3)` reads **0** during
reset (that is why the mutated design reading 1 is a genuine mismatch).

### binary / gray (`_emit_encoded_state`)

The reset branch loads the initial code:

```verilog
if (!rst_n) state <= STATE_<initial>;
```

so the state vector *is* a real state during reset (the all-zero code may well
be a real state here). The reset value is `state == initial`, not "no state".
`_reset_state` returns `None` for one-hot and `compiled.design.initial` for
binary/gray; `_eval_with_state` treats a `None` state as "every `StateEq` is
false". This is covered by a unit test but has no bundled example to exercise
it end-to-end (all six examples are one-hot).

### input synchronisers (§9.3)

Every `sync` input's two-flop synchroniser is in the reset branch and clears on
the reset edge, so its effective value during reset is **0**. A non-`sync`
input has no synchroniser and passes through combinationally, keeping whatever
the testbench drives. `sequence_detector`'s `din` is `sync: false`, so it is
the second case; `_reset_outputs` forces sync inputs to 0 and leaves non-sync
inputs at the driven value.

## What I built

Two properties, both now checked by the simulation:

1. **Reset assertion drives the specified outputs.** From every reachable state
   (not only power-on), assert reset and compare every output against
   `_reset_outputs` — the emitter's reset value.
2. **The reset is asynchronous.** Reset is asserted while the clock is *low* and
   outputs are compared *before* the next rising edge. A synchronous reset
   would still show the pre-reset output here and fail the check.

Implementation (all in `gatepack/verify/simulation.py`):

- `_reset_state` / `_reset_outputs` — the reset-phase expected value.
- `_outputs_reference_state` — gate on emitting probes at all.
- `_ReferenceDesign.reset_outputs` — the reference model's reset phase.
- `_path_to_state` — one shortest drive path per reachable state.
- `_stimulus` now appends a `reset_assert` step per reachable state; the
  testbench emits it as: drive inputs to 0, `#1`, assert reset while the clock
  is low, `#1`, compare every output. The existing transition traces and the
  three-edge flush are untouched.

### Cost and the slip-through shape

I chose **one reset probe per reachable state** (not per state × input pair,
and not per non-sync input assignment). The probe drives inputs to all-zero and
compares against `_reset_outputs(all-zero)`. For a Moore machine (every bundled
example), the reset output is input-independent, so this fully covers the
state-clearing fault: the probe from a state whose pre-reset output differs from
the reset value is exactly the one with teeth. The expected value is the same
for every state, so the probe's bite comes entirely from the pre-reset state.

The cost is one extra trace per reachable state (pelican: 5 extra traces on top
of 20 transition traces). The vvp runtime for the pelican showcase went from
~6 ms to ~7 ms — noise. A fault that could slip past this choice must (a) be a
Mealy output that reads a non-`sync` input *and* (b) only diverge from correct
behaviour during reset at a non-zero input combination; no bundled design has
such an output, so nothing slips today. Enumerating every non-sync assignment
during reset is the obvious extension if a Mealy design is ever added.

### What I deliberately did not do

- **Combinational designs (parity, mux2to1) get no reset probe.** Their outputs
  do not reference state, so a reset fault cannot reach a primary output; a
  probe would be vacuous. `_outputs_reference_state` detects this and skips
  (this also keeps the pre-existing `test_combinational_testbench_exhaustive`
  vector count intact).
- **No power-on-only probe.** The brief asked for reachable states; the initial
  state is itself reachable and is probed like any other.
- **The three-edge flush is untouched**, including the long comment explaining
  why a fourth edge is a real mismatch.

## The before/after mutation verdict (real toolchain)

```
docker run --rm -u "$(id -u):$(id -g)" -v "$PWD:/repo" -w /repo \
  gatepack-toolchain:m6 python3 -m gatepack verify \
  examples/sequence_detector/design.yaml \
  --library examples/sequence_detector/parts.csv
```

Before (baseline, this run):

```
  mutation nand_to_and:      caught by equivalence only
  mutation flop_d_invert:    detected
  mutation reset_polarity_flip: caught by equivalence only
```

After:

```
verification: passed
  equivalence:               passed
  exhaustive simulation:     passed
  mutation:                  passed
      all applicable mutations detected or caught by equivalence alone
  flop reset connectivity:   passed
  supervisor parameters:     passed
  mutation nand_to_and:      caught by equivalence only
  mutation flop_d_invert:    detected
  mutation reset_polarity_flip: detected
```

`reset_polarity_flip` moved **caught by equivalence only → detected**. The
verdict changed because the exhaustive simulation genuinely started failing on
the mutated design — I did not touch `mutation.py`, `base.py` or `synchronous.py`.

`nand_to_and` stayed `caught by equivalence only`, which is correct: that fault
cannot reach `match` in any reachable state (the notes-pins reachability
argument). My stimulus did not flip it, so it is not checking something the
specification does not require.

## The falsification (a check that can fail, shown failing)

A toolchain test (`tests/toolchain/test_reset_simulation.py`) builds the mapped
netlist, hand-mutates `cells_sim.v` with the `reset_polarity_flip` transform,
regenerates the testbench, and runs Icarus. Output:

```
FAIL: match during reset
EXHAUSTIVE_SIM_FAIL (1)
```

The `reset_assert` probe fails precisely because, from `S3`, the mutated flop
does not clear on reset and `match` stays high while the reference model (from
the emitter, not the mutated model) expects 0.

## Per-example verification (all six, no acknowledgement flag)

Each with its own `parts.csv` (the app path) and, separately, with the full
`libraries/74aup.csv` (the toolchain-test path). All exit 0.

```
pelican            verification: passed
debounce           verification: passed
sequence_detector  verification: passed
mux2to1            verification: passed
parity             verification: passed
power_sequencer    verification: passed
```

`pelican`'s mutation panel (for the record): `nand_to_and: detected`,
`flop_d_invert: detected`, `reset_polarity_flip: detected` — all three reach a
primary output there, unlike sequence_detector.

## Test counts and runtime

```
.venv/bin/python -m pytest tests -q
# before: 706 passed, 5 skipped
# after:  715 passed, 5 skipped   (7 unit + 2 toolchain tests added)
```

Exhaustive-simulation runtime for the pelican showcase (5 states), measured as
the `vvp` run of the generated testbench:

- before: `real 0m0.006s`
- after:  `real 0m0.007s` (and the testbench grew from 2011 to 2361 lines)

## What I could not settle / suspicions

- **The pelican `safe_state` says `traffic_red: 1` but the emitter produces
  `traffic_red = 0` during reset.** This is not a bug in my check — it is the
  one-hot "during reset ≠ initial state" distinction made literal: while reset
  is asserted every state bit is 0, so no traffic aspect is lit; `traffic_red`
  becomes 1 only after the initial STOP state loads (three edges later). The
  `safe_state` field is *not* consulted by verification anywhere (grep confirms
  it is schema-only). If the intended meaning of `safe_state` is "the outputs
  while reset is asserted", then the emitter and the schema disagree, and that
  is a front-end defect **outside my scope** — I report it rather than fix it.
- **No bundled example uses `binary`/`gray` encoding**, so `_reset_state`'s
  encoded branch is unit-tested but not exercised by a real toolchain run.
- **`sync_deassert: false` is never exercised either.** The pre-existing
  three-edge flush already assumes the de-assert synchroniser; a design that
  turns it off would load the initial state on the first edge, and both the old
  flush and the surrounding comment would be wrong. That predates this run and
  I left it alone (all examples default `sync_deassert: true`).
- **The reset probe drives inputs to all-zero.** As noted above, a Mealy
  output that depends on a non-`sync` input and only diverges during reset at a
  non-zero input combination would slip past. No bundled design has one; the
  extension (cycle every non-sync assignment during the held reset) is
  straightforward and cheap if one appears.
