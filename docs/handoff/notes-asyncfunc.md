# notes-asyncfunc.md — Package L handoff

## What changed

The asynchronous path now has a **functional** check, not only hazard checks.
`gatepack verify` on an async design reports three checks: the two hazard checks
plus `functional (fundamental mode)`, which exhaustively simulates the mapped
netlist against the flow table.

* `gatepack/verify/asynchronous.py` — `run_functional_check` +
  `enumerate_functional_pairs`; wired into `verify_netlist` as the third check.
* `gatepack/verify/hazard.py` — one pure helper `driven_values` (reads the
  loop-cut next-state value a feedback SOP drives).  Still imports nothing from
  `gatepack/synth/async_`; the AST independence test is unmodified.
* `gatepack/async_pipeline.py` — `hazard_passed` is now "every check `PASSED`",
  so a `not applicable` functional check gates the netlist too.
* `gatepack/report/report.py` — the async report names the functional check and
  its fundamental-mode scope.
* Tests: `tests/unit/test_async_functional.py` (8), `tests/toolchain/
  test_async_injection.py` (1, real z3+Icarus), one assertion added to
  `test_async_wire.py`; `tests/toolchain/_async_hazard_injection.py` turned into
  `run_probe()`/`main()` that returns non-zero if the injection stops failing.

## The acceptance criterion, measured

The injected (dropped-cube) netlist is still hazard-free but no longer implements
the machine.  Before Package L it shipped green; now:

```
cover cubes clean [1, 2] / faulty [1, 1]
functional (fundamental mode)  clean: passed, faulty: failed
netlist accessor  HazardFailed
```

`test_async_injection.py` asserts exactly this under real z3 + Icarus.

## How to run it

```
docker run --rm -u "$(id -u):$(id -g)" -v "$PWD:/repo" -w /repo \
  gatepack-toolchain:m6 bash -c \
  'python3 -m gatepack verify examples/async_latch/design.yaml \
     --library libraries/74aup.csv --build .gpout/b'
```

Local unit tests (no tools needed): `.venv/bin/python -m pytest -q
tests/unit/test_async_functional.py`.

## Files touched outside the listed scope

None.  `gatepack/verify/run.py`, `base.py`, `cli.py` are untouched, deliberately.

## What the next implementer should know

* **The top-level `verification:` string still says `passed` for a too-large
  async design.**  The functional check reports `not applicable` and the netlist
  is gated (via `hazard_passed`), but `run.py`'s `_manifest` computes the overall
  from `report.ok`, which treats `not applicable` as a non-verdict (§21.4, the
  synchronous convention).  A one-line change in `run.py` (treat a
  `not applicable` functional check as non-pass) is the clean fix and is out of
  this package's scope.  Recorded, not closed.
* **The check is one-step, not full-settling.**  It holds the state at the source
  total state and verifies the netlist drives the flow table's next state and
  outputs.  Full fundamental-mode traversal is 5a/5b's job.
* **Re-deriving the assignment is not circular for this check's purpose.**  The
  function under test is the cover (stage 4); the flow table is the spec's own
  semantics and the assignment is deterministic (z3 fixed seed).  A stage-3
  assignment bug would not be caught — that SVC gap is inherited from Package E.

## The three things I am least confident about

1. One-step vs full-settling semantics (argued, not re-derived).
2. The `not applicable` top-line residue in `run.py` (recorded, out of scope).
3. `driven_values`'s single-driver-per-state-net assumption (true of the emitter
   today, un-enforced).
