# notes-async.md — Package E handoff

## Which stages are complete

All five stages are implemented and tested; the full pipeline (admit → flow
table → SVC assignment → hazard-free cover → mapped netlist) plus the
independent hazard verifier (5a ternary + 5b Icarus) close under the real
toolchain (`gatepack-toolchain:m6`, z3 4.8.12 + Icarus 11.0).

| Stage | Module | Status |
|---|---|---|
| 1 admission | `gatepack/synth/async_/admit.py` | done, refusal-only |
| 2 flow table + admissibility | `gatepack/synth/async_/flowtable.py` | done (no state reduction) |
| 3 SVC assignment | `gatepack/synth/async_/assign.py` (+ `smt.py`) | done, z3 |
| 4 hazard-free cover | `gatepack/synth/async_/cover.py` (+ `emit.py`) | done, z3; privileged-cube rule omitted |
| 5 independent hazard check | `gatepack/verify/hazard.py` | done (5a ternary + 5b Icarus) |

## What I guessed / left as a judgment call

- **z3 is driven as a binary over SMT-LIB2**, not the Python `z3-solver` wheel.
  The wheel is not a dependency and not installed anywhere; the bridge
  (`async_/smt.py`) writes SMT-LIB2 and shells out to `z3` through the injected
  runner. If a future stage wants richer solver features (Optimize, unsat cores
  natively), either add `z3-solver` with a written justification, or extend the
  SMT-LIB2 bridge.
- **Stage 2 admissibility** is a min-Hamming-distance check (stable input set vs
  firing input set of each non-self-loop transition). This is my formulation;
  I did not port a specific textbook algorithm. If you have Unger's book handy,
  verify this is equivalent to the fundamental-mode admissibility condition.
- **Stage 4 omits the Nowick–Dill privileged-cube condition.** Required cubes
  (static-1) and ON coverage are exact; static-0/dynamic hazards are left to 5a
  to catch. This is the weakest part of the synthesis and the first thing I
  would tighten if re-approached.
- **State nets are named `s_0..s_{w-1}` by convention**, shared between the
  emitter and the verifier's probe builder. Both live in my files; if you change
  the naming in `emit.py`, `verify/asynchronous.py::build_transition_probes`
  must change in lockstep (there is no shared constant, on purpose — the checker
  must not import the synthesiser).

## What I could not verify

- **Reset / initial-state realisation.** The emitted netlist is the combinational
  feedback core only; nothing here forces the initial state on the state bits.
  I did not verify a physical reset path.
- **True per-instance delay perturbation in 5b.** Delays are perturbed per cell
  type per seed, not per instance. I could not verify that 5b would catch a
  glitch that depends on the relative delay of two instances of the *same* cell.
- **The async path is not wired into the CLI.** `run_verify`/`run_estimate`/
  `build` are out of scope and still call the synchronous backend, so the
  front-end still refuses every async design (admission only refines *why*).
  To exercise the real pipeline, the tests call `model_mod.compile_design`
  directly, bypassing `compile_design_file`.

## How to run what I did

Unit (no z3 needed — fake runner):

```
.venv/bin/python -m pytest -q tests/unit/test_async_*.py
```

Real toolchain (needs `gatepack-toolchain:m6`):

```
.venv/bin/python -m pytest -q tests/toolchain/test_async_hazard.py
```

Full suite:

```
.venv/bin/python -m pytest -q
```

## Three things I am least confident about

1. The stage-2 admissibility formulation (min Hamming distance) is not a cited
   textbook result.
2. Omitting the privileged-cube condition in stage 4: static-0 hazards are
   caught by 5a, not prevented by 4.
3. 5b's per-type delay perturbation may miss a same-type-gate relative-ordering
   glitch.
