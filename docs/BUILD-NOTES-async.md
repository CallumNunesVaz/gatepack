# BUILD-NOTES-async.md — Package E, asynchronous synthesis (M7 §7.3)

## What this is

§7.3 deferred `AsynchronousBackend` to v0.2 because three problems are unsolved
*in general*. This change re-scopes it into v0.1.0 by taking the constrained
sub-problem §7.3 sanctions — **≤3-literal product terms** and
**single-variable-change (SVC) encodings** — and by making hazard-freedom an
**independently verified property of the emitted netlist**, never an assumed
consequence of how it was built.

The governing sentence: *"A netlist that is formally equivalent and hazardous on
the bench is the worst possible output of this tool."* Every limit is a refusal
that names the specific construct; nothing is emitted past the independent
hazard check.

## What was implemented

Five stages as separate modules under `gatepack/synth/async_/` (each testable
alone), plus the independent verifier `gatepack/verify/hazard.py`:

1. **`admit.py`** — refusals only: no `fundamental_mode`, empty
   `mutually_exclusive`, an uncovered input, a group naming a non-input, a
   `clock:` block, or more than `ASYNC_STATE_CAP = 16` states (a named constant,
   because stages 2–3 are exponential).
2. **`flowtable.py`** — the primitive flow table (rows = states, columns = input
   combinations, entries = next state + outputs, stable where next == current),
   then fundamental-mode admissibility.
3. **`assign.py`** — SVC assignment via **z3** (bit-vectors, Hamming-distance-1
   constraints), widening `w` from `ceil(log2 n)` to `ASYNC_WIDTH_CAP = 16`.
4. **`cover.py`** — hazard-free two-level cover via **z3** (ON coverage +
   required-cube constraints + cardinality-minimised selection), ≤3-literal
   refusal, then `emit.py` maps AND-OR directly to G-cells (INV/BUF/AND2/AND3/
   OR2 trees). **ABC never sees this netlist.**
5. **`verify/hazard.py`** — 5a ternary simulation (pessimistic 0/1/X to a fixed
   point) and 5b Icarus glitch simulation (unit-delay models). A failure in
   either is a hard refusal.

`gatepack/synth/asynchronous.py` and `gatepack/verify/asynchronous.py` were
rewritten from refusing stubs into the backend and verify strategy.
`gatepack/frontend/frontend.py` now runs admission before its async refusal.

## The one design decision that matters most

**z3 is driven as a binary over SMT-LIB2** (`gatepack/synth/async_/smt.py`), not
via the `z3` Python package. The pinned toolchain ships z3 as a binary; the
`z3-solver` Python wheel is **not** a dependency and is **not installed** in the
venv or the container. Adding it would violate the "no new runtime deps beyond
pydantic" rule. The bridge writes the SMT-LIB2 script to `<workdir>/<name>.smt2`
and runs `z3 -smt2` through the same injected `ToolchainRunner` the rest of the
pipeline uses, so a missing z3 is reported (`AsyncRefused`), never substituted.

## Textbook method at each stage (and where I am unsure)

- **Stage 2 admissibility** is my own formulation, not a named textbook result:
  for each non-self-loop transition, the minimum Hamming distance between the
  source state's stable input set and the transition's firing input set must be
  ≤ 1; otherwise both differing inputs are named. I am **not** fully certain
  this is the canonical fundamental-mode admissibility check the literature
  (Unger's *Asynchronous Sequential Switching Circuits*, §5) calls for; the
  textbook treatment is about total-state transitions in the flow table, and my
  check is a min-distance special case. It matches the golden's intent, but it
  may over- or under-approximate in designs with richer mutual-exclusion
  structure. **Flagged as uncertain.**
- **Stage 3** is the textbook SVC (single-variable-change) hypercube-embedding
  condition, solved exactly with z3 rather than the classic partition-based
  heuristics. This is the one stage I am most confident about.
- **Stage 4** implements the **required-cube** (static-1) condition and ON-set
  covering, minimised by iterating a cardinality bound in z3. I did **not**
  implement the full Nowick–Dill **privileged-cube** condition (which also
  controls static-0/dynamic hazards in multi-output generalized fundamental
  mode). The brief's `cover.py` calls for it; I omitted it and rely on stage 5a
  to catch what it would prevent. See "weakest parts".
- **Stage 5a** uses the standard pessimistic ternary extension (enumerate the
  binary completions of every X input; agree ⇒ value, else X). The state
  feedback loop is **cut** by holding the state nets at their settled source
  values; only primary outputs are checked for X. This is the Nowick–Dill
  fundamental-mode hazard check for outputs, direction-agnostic (X).
- **Stage 5b** uses unit-delay `assign #d` models; delays are perturbed **per
  cell type per seed** (not per instance), and state nets are held with
  `force`/`release`. True per-instance perturbation is approximated; see below.

## What is a placeholder / not done

- **Reset and the initial state are not realised.** The emitted netlist is the
  combinational feedback core (next-state SOPs + outputs); how reset forces the
  initial state on the state bits is out of scope and undocumented in the
  emitted netlist. Fundamental-mode hazard-freedom does not depend on it, but a
  physically complete async circuit needs it.
- **State reduction (compatible-state merging) is not performed.** An unreduced
  table is correct, merely larger; I chose not to merge unverified.
- **Stage 4's privileged-cube rule** (static-0/dynamic hazards in the cover
  itself) is not enforced; stage 5a is the safety net for it.
- **5b per-instance delay perturbation** is approximated by per-type, per-seed
  perturbation. Verilog's `defparam` could make it truly per-instance; I did not
  do that.
- **The front-end still refuses all async designs.** Admission now names the
  specific defect (no `fundamental_mode`, an uncovered input, a clock block,
  etc.), but an *admitted* async design is still refused with the generic
  v0.1.0 message, because `run_verify`/`run_estimate`/`build` (out of scope)
  hard-code `SynchronousBackend`/`SynchronousVerify` and the synchronous Verilog
  emitter is clocked. The async backend/verify are reached directly (bypassing
  the front-end refusal) in the tests. This is the explicit "leave the front-end
  refusal in place and ship the checker" fallback the brief sanctions.

## What I verified against the real toolchain

All of the following close inside `gatepack-toolchain:m6` (z3 4.8.12, Icarus
11.0, pydantic 2.13.4), run with `-u "$(id -u):$(id -g)"`. The toolchain tests
are in `tests/toolchain/test_async_hazard.py` and the live-run transcripts are
reproduced below.

```
$ z3 --version ; iverilog -V 2>&1 | head -2
Z3 version 4.8.12 - 64 bit
Icarus Verilog version 11.0 (stable) ()
```

Handshake latch (2 states, 2 inputs) — synthesises and passes both checks:

```
assignment: {'IDLE': 1, 'BUSY': 0} width 1
5a findings: ()
hazard (ternary)   passed  8 fundamental-mode transition(s) checked
hazard (glitch sim) passed  no output glitch observed across 3 delay-perturbation seeds
```

Determinism (same design twice, real z3):

```
codes1: {'IDLE': 1, 'BUSY': 0}   codes2: {'IDLE': 1, 'BUSY': 0}
codes equal: True ; verilog equal: True ; json equal: True
```

Refusals (each names the construct):

```
two-input:  transition A -> B requires inputs ['x', 'y'] to change simultaneously
no-SVC:     no single-variable-change state assignment exists within width 16.
            Conflicting transitions: A->B, B->C, C->A.
4-literal:  function 'q' needs product term a & b & c & d with more than 3 literals
```

Hand-built hazardous netlist (Y = A·B | Ā·C, B=C=1) — refused by 5a and 5b:

```
5a findings: (HazardFinding(output='Y', changing_input='A', stable_value=1, ...), ...)
glitch sim:  GLITCH: Y ... GLITCH_FAIL (2)
```

The z3 quirks that cost time, recorded for the next implementer:

- z3 4.8.12 rejects the old `random_seed` parameter spelling; `:smt.random_seed 0`
  is the correct one (and is what the pin toolchain accepts). Using the old name
  makes z3 print an error to stderr *and still return a model* — easy to miss.
- z3 4.8.12's SMT-LIB2 frontend does **not** support `((_ at-most k) …)`
  (errors "unknown constant at-most"), so the cover's cardinality bound is
  encoded with `ite` + integer `<=` under `(set-logic ALL)`.
- A trailing `(get-value …)` after an UNSAT `(check-sat)` makes z3 exit non-zero
  with "model is not available"; `smt.parse_output` treats that as plain UNSAT.

## Test counts

- Baseline: **749 passed, 5 skipped**.
- After this change: **788 passed, 5 skipped** (39 new: 36 unit + 3 toolchain).
- New unit tests: `tests/unit/test_async_{admit,flowtable,assign,cover,hazard,backend}.py`.
- New toolchain tests: `tests/toolchain/test_async_hazard.py` (real z3 + Icarus).
- New goldens: `tests/golden/designs/async_{latch,4literal,no_svc,two_input}.yaml`.

Acceptance notes:

- The hand-built hazardous netlist is refused by 5a, and
  `test_x_propagation_is_pessimistic_not_optimistic` pins the ternary tables so
  weakening X-propagation fails the suite.
- `test_hazard_module_imports_nothing_from_async_synth` parses `hazard.py`'s AST
  and asserts no import of `gatepack.synth.async_`.
- The determinism test runs the same design twice under real z3 and asserts
  identical codes, `mapped.v`, and `mapped.json`.

## Three things I am least confident about

1. **Stage 2's admissibility formulation** (min-Hamming-distance between stable
   and firing input sets) is my own, not a canonical textbook check. It matches
   the golden's intent and is tested, but it may not capture every fundamental-
   mode violation the literature would.
2. **Omitting the privileged-cube condition** in stage 4. The required-cube
   (static-1) condition is exact, but static-0/dynamic hazards in the *cover*
   are only caught downstream by 5a, not ruled out by construction. If a design
   produces a static-0 hazard, it is refused by 5a rather than fixed by 4 —
   correct, but the refusal looks like a verification failure, not a cover
   failure, which may confuse the user.
3. **5b's per-type (not per-instance) delay perturbation.** A glitch that only
   appears under a specific *relative* ordering of two same-type gates could be
   missed by all three seeds. 5a (exact, pessimistic) is the primary check; 5b
   is complementary and I would not ship 5b alone as proof.
