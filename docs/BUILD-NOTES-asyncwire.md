# BUILD-NOTES-asyncwire.md — Package K: the asynchronous backend becomes reachable

## What this package does

`gatepack/synth/async_/` + `gatepack/verify/hazard.py` implemented §7.3's
constrained asynchronous synthesis (five stages) and verified it against real z3
and Icarus, but the CLI still refused every async design — M7 was "partial"
because the backend was unreachable.  This package wires it in **without
weakening the one rule the component has**: no async netlist may be written to
disk, returned to a caller, or reported unless stage 5 (the independent hazard
checks) has run and passed.

## What I wired

* **`gatepack/async_pipeline.py` (new)** — the single public entry point.
  `run_async_pipeline(compiled, runner, workdir, cell_functions)` runs stages
  1–4 (`AsynchronousBackend._synthesize`) then stage 5
  (`AsynchronousVerify.verify_netlist`), and returns an `AsyncPipelineResult`
  whose `report` is always available but whose netlist is only reachable through
  `netlist()` / `mapped_verilog()` / `mapped_json()` / `write_artefacts()`,
  every one of which raises `HazardFailed` (a subclass of `AsyncRefused`) unless
  stage 5 passed.  `HazardFailed` names the failing check and its detail, so the
  specific text reaches the CLI.  It lives in a third module (not
  `verify/asynchronous.py`, which imports `synth/async_`) to dodge the import
  cycle the brief named.

* **`AsynchronousBackend.synthesize` demoted to `_synthesize`** — the stages 1–4
  half (which already contains a netlist) is no longer a public method.

* **`frontend.py`** — an *admitted* async design now compiles (model-only; empty
  `verilog`/`properties`) instead of being refused.  Admission still refuses and
  names the construct, so the "async-refused" exit code survives for designs that
  cannot be attempted.

* **`verify/run.py`** — `run_verify` dispatches async to `_run_async_verify`,
  which runs the pipeline, reports `equivalence` as `not applicable` (no
  synchronous golden netlist) and the two hazard checks each as its own check.
  A hazard failure is a **failed verification** (exit 1).  `mapped.json`/
  `mapped.v` are written only past a passed stage 5.  `--properties-only` is
  refused (sby properties are synchronous).

* **`build.py`** — `run_build` dispatches async to `_run_async_build` /
  `_assemble_async`, which obtain the netlist only via `pipeline.netlist()`
  (raising on hazard failure), then pack + BOM + KiCad netlist + an async report.
  The synchronous analyses (timing/SCOAP/stuck-at) are deliberately **not** run —
  each assumes a clocked combinational cut — and the report says so.  `--mapped`
  is refused for async (it would inject a raw netlist past the hazard check).

* **`estimate.py`** — refuses an async design with the reason: the §6 verdict is
  defined over flop/clock/package/depth metrics an async design has no analogue
  of ("it cannot, and here is why").

* **`report/report.py`** — `emit_async_report` states, every time: fundamental
  mode assumed, the declared mutually-exclusive inputs, the assignment width and
  whether spares were added, the max product-term literal count, both hazard
  checks, and that the guarantee does **not** extend to concurrent input changes
  and that the privileged-cube condition is not enforced (dynamic hazards not
  covered by construction).

* **`api.py`** — `build_async_payload` for the async `build --json` payload,
  dropping the synchronous-only metrics (flop count, combinational depth, SCOAP,
  stuck-at) rather than emitting numbers an async netlist does not support.

* **`examples/async_latch/`** — a bundled async example (the §1.3 synthetic
  handshake latch), `design.yaml` + single-gate-only `parts.csv`.

## What I changed that was not strictly in my file list

* `tests/golden/test_golden_designs.py` — one entry: `async_handshake.yaml` was
  pinned as `AsyncRefused`; it is now *admitted* and fails C1 as any FSM does
  (non-exhaustive transition set), so the expected exception is `CompileError`.
* `tests/toolchain/test_examples.py` — `test_every_example_verifies` asserted
  `"equivalence: passed"` for every example; the assertion is now timing-model
  aware (async examples assert the two hazard checks instead).

Both are behaviour the wiring itself makes true; leaving them untouched would
have broken the suite.

## What I could not verify

* **A real synthesised *hazardous* design through the CLI.**  Stage 4's
  required-cube (static-1) condition rules out static-1 hazards by construction,
  and I could not reliably produce a static-0/dynamic hazard (the privileged-cube
  condition is omitted) through a real design.  The CLI hazard-failure path is
  therefore tested with a scripted `FAILED` report
  (`tests/contract/test_async_cli_contract.py::test_hazard_failing_verify_is_failed_and_writes_no_netlist`),
  and the real 5a/5b *detection* is pinned by the pre-existing
  `tests/toolchain/test_async_hazard.py` hand-built-netlist probe.  The two
  halves together cover the rule but not the seam between them.
* **The F-cell function filter** (`cell_functions_from_liberty` now skips
  `IQ`/`IQN`) is verified against the *current* Liberty generator's output only.
  If the F-cell `Q`-pin function string ever changes, the filter breaks or leaks.

## What I guessed / judgment calls

* **Equivalence is "not applicable", not implemented.**  The brief said "runs
  equivalence where it is meaningful".  I judged it not meaningful for async (the
  netlist is constructed to realise the flow table exactly; there is no
  synchronous golden), and reported it as `not applicable` with that reason.
  A flow-table-vs-netlist functional-equivalence check would be a stronger
  statement and I did not build it.
* **`compile`/`simulate`/`analyse` are not async-aware.**  They now compile an
  async design (instead of refusing) but carry synchronous payloads
  (`compile --json` reports `flopCount`, `simulate` reports a spec-only table).
  They degrade gracefully (no crash) but are not honest about the async case.
  The brief scoped verify/build/estimate; these three are a known gap.
* **The scratch files land in the build dir.**  Stage 3/4 write `*.smt2` and
  stage 5b writes `async_glitch_mapped.v`/`async_unit_delay_cells.v`/`*.vvp`
  into the work directory (the `--out`/`--build` dir).  They are solver inputs /
  simulation scratch, not the deliverable netlist, and the deliverable artefacts
  (`mapped.json`, `mapped.v`, `bom.csv`, …) are never written on a failed or
  unrun stage 5.  I did not clean them up.

## Test counts

* Baseline (measured, this checkout): **845 passed, 5 skipped**.
* After this change: **864 passed, 5 skipped** (19 new: 6 unit
  `test_async_pipeline.py`, 6 contract `test_async_cli_contract.py`, 4 toolchain
  `test_async_wire.py`, 3 example tests the new example surfaces through
  `test_examples.py`).

## The three things I am least confident about

1. **The binding is structural but not total.**  Every *public* path to an async
   netlist goes through `run_async_pipeline` and its guarded accessors, and
   `_synthesize` is private — but Python cannot prevent `._emitted` being read or
   `_synthesize` being called by a determined future author.  It relies on the
   underscore convention for the last inch.
2. **No real synthesized hazardous design was driven through the CLI.**  The
   failure path is pinned with a scripted failed report + the pre-existing
   hand-built-netlist detection; the seam (stage 4 emitting something 5a/5b then
   refuse) is not exercised end-to-end.
3. **Stage 2 admissibility and the omitted privileged-cube condition are
   inherited unexamined.**  The synthesis is only as sound as the previous
   package's min-Hamming-distance admissibility and required-cube-only cover;
   my report states the limits honestly, but I did not re-derive either.
