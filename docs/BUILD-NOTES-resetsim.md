# BUILD NOTES — resetsim: exhaustive simulation now checks the reset-assertion phase

Full report: `docs/handoff/notes-resetsim.md`.

## What was implemented

`gatepack/verify/simulation.py` now emits, in addition to the unchanged
transition traces, one reset-assertion probe per reachable state: assert reset
while the clock is low and compare every output against the emitter's reset
value before the next rising edge. The reset value is derived from the emitter
(`one-hot` → no state predicate true; `binary`/`gray` → the initial code; every
`sync` input → 0; non-`sync` inputs pass through). Probes are skipped when no
output references state (parity, mux2to1), where a reset fault is unobservable.

## Tests

- `tests/unit/test_simulation_reset.py` (7) — pure-function coverage of
  `_reset_state`, `_reset_outputs`, `_outputs_reference_state`, and the emitted
  stimulus/testbench.
- `tests/toolchain/test_reset_simulation.py` (2) — real Yosys + Icarus: the
  `reset_polarity_flip` verdict is `detected`, and a hand-mutated `cells_sim.v`
  genuinely fails the simulation with `FAIL: match during reset`.

```
.venv/bin/python -m pytest tests -q
# 715 passed, 5 skipped  (baseline 706 passed, 5 skipped)
```

## What I guessed / assumptions

- The probe drives inputs to all-zero. A Mealy output that reads a non-`sync`
  input and only diverges during reset at a non-zero input combination would
  slip past. No bundled design has such an output; documented as the known
  slip-through shape.
- `binary`/`gray` reset behaviour is modelled from the emitter and unit-tested,
  but no example exercises it end-to-end (all six are one-hot).

## What could not be verified / is weakest

- No real-toolchain coverage of `binary`/`gray` or `sync_deassert: false`
  (no example uses them). The pre-existing three-edge flush already assumes the
  de-assert synchroniser; a `sync_deassert: false` design would load the initial
  state on the first edge, but that predates this run.
- **Suspicion (outside scope, not fixed):** the pelican `safe_state` declares
  `traffic_red: 1` while the one-hot emitter produces `traffic_red = 0` during
  reset assertion. If `safe_state` is meant to describe the *during-reset*
  outputs, the emitter and schema disagree — a front-end defect, reported in the
  notes rather than touched.
