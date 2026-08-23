# notes-asyncwire.md — Package K handoff

## What changed

The async backend (`gatepack/synth/async_/` + `gatepack/verify/hazard.py`) is
now reachable from the CLI.  The pieces:

* `gatepack/async_pipeline.py` — the single public entry point.  `_synthesize`
  (stages 1–4) is now private; `run_async_pipeline` runs stages 1–4 then stage 5
  and hands back an `AsyncPipelineResult` whose netlist is only obtainable
  through accessors that raise `HazardFailed` unless stage 5 passed.
* `frontend.py` compiles admitted async designs (model only, empty verilog).
* `verify/run.py` — `_run_async_verify` reports equivalence as `not applicable`
  and each hazard check as its own check; a hazard failure is a failed
  verification; netlist written only past a pass.
* `build.py` — `_run_async_build`/`_assemble_async` build BOM/KiCad/report only
  past a passed stage 5; synchronous analyses skipped with a stated reason.
* `estimate.py` refuses async with the reason (the §6 verdict has no async
  analogue).
* `report/report.py` — `emit_async_report` states the §7.3 guarantee and limits
  every time.
* `examples/async_latch/` — bundled async example (synthetic handshake latch).

## How to run it

Real toolchain (z3 + Icarus, `gatepack-toolchain:m6`):

```
docker run --rm -u "$(id -u):$(id -g)" -v "$PWD:/repo" -w /repo \
  gatepack-toolchain:m6 bash -c \
  'python3 -m gatepack verify examples/async_latch/design.yaml \
     --library libraries/74aup.csv --build /tmp/b'
```

```
verification: passed
  equivalence:               not applicable
  hazard (ternary):          passed
      8 fundamental-mode transition(s) checked, no potential static hazard
  hazard (glitch sim):       passed
      no output glitch observed across 3 delay-perturbation seeds
```

Local (no z3/iverilog) — the pipeline refuses, naming the tool:

```
error: asynchronous design 'async_latch' refused: z3 not found: ...
```

New tests: `tests/unit/test_async_pipeline.py`,
`tests/contract/test_async_cli_contract.py`,
`tests/toolchain/test_async_wire.py`.

## Files touched outside the listed scope

* `tests/golden/test_golden_designs.py` — `async_handshake.yaml` now fails with
  `CompileError` (non-exhaustive transitions) instead of `AsyncRefused`.
* `tests/toolchain/test_examples.py` — verification assertions made
  timing-model aware so the async example can verify green.

## The three things I am least confident about

1. The binding is structural over the *public* API (guarded accessors + private
   `_synthesize`) but not enforceable against direct `._emitted` access.
2. No real synthesized hazardous design was driven through the CLI — the failure
   path is pinned with a scripted failed report + the hand-built-netlist 5a/5b
   probe, not an end-to-end stage-4-emits-hazard stage-5-refuses run.
3. The F-cell `IQ`/`IQN` filter in `cell_functions_from_liberty` is tied to the
   current Liberty generator's exact F-cell `Q`-pin string, and stage 2
   admissibility / the omitted privileged-cube condition are inherited
   unexamined from Package E.
