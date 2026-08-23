# Package E — asynchronous synthesis, constrained and verified (M7, §7.3)

Read `docs/handoff/delegation-rules.md` first. Every rule there applies.

## What this is

§7.3 deferred `AsynchronousBackend` to v0.2 because three problems are unsolved
*in general*. It is being re-scoped into v0.1.0 — but **not** by solving them in
general. It is re-scoped by taking the constrained sub-problem §7.3 itself
sanctions:

> "If async synthesis is later re-scoped into v0.1.0, it is constrained to
> ≤3-literal product terms and single-variable-change encodings, with both
> limits stated in the report."

and making hazard-freedom an **independently verified property of the emitted
netlist**, never an assumed consequence of how it was built.

## The principle that outranks the task

> "A netlist that is formally equivalent and hazardous on the bench is the worst
> possible output of this tool — worse than no output, because it survives
> review." (§7.3)

Everything below follows from that sentence. Concretely:

* **Every limit is a refusal, not a best effort.** A design that needs a
  4-literal product term is refused, naming the term. A design with no
  single-variable-change assignment is refused, naming the transition pair that
  forced it. A design that fails the hazard check is refused, naming the
  transition and the output. Refusals are the deliverable as much as the
  synthesis is.
* **Never emit a netlist that has not passed the independent hazard check.**
  This is the one hard rule of the package. If you run out of time, ship the
  checker without the synthesis — never the synthesis without the checker.
* The guarantee you are building is **fundamental mode only**: one input changes
  at a time, and the circuit settles before the next change. Say so everywhere
  it is reported. A user who reads "hazard-free" and applies it to concurrent
  input changes has been misled by this tool.

## What already exists — check before you build

* `gatepack/frontend/schema.py` already has `timing_model: asynchronous` and
  `FundamentalMode.mutually_exclusive: list[list[str]]`. The spec language is
  there; nothing consumes it.
* `gatepack/frontend/frontend.py:75` refuses async outright, with a good message
  (`_async_refusal`). That refusal becomes conditional, not deleted.
* `gatepack/synth/base.py` defines the `SynthesisBackend` interface;
  `synchronous.py` is the working implementation and your model for structure.
* `gatepack/synth/asynchronous.py` and `gatepack/verify/asynchronous.py` are
  the two refusing stubs you are replacing.
* **z3 is already in the pinned toolchain** (`gatepack-toolchain:m6`) and is
  already a `doctor` tool. Two stages below want a solver; use it rather than
  writing a search by hand.
* `gatepack/liberty/`, `gatepack/netlist.py`, `gatepack/pack/` are all
  synthesis-independent and are reused unchanged.

## The architecture

Five stages. Implement them as separate modules under a new
`gatepack/synth/async_/` package so each is testable alone — that separability
is the point, because stage 5 must not be able to reuse stage 3's data
structures.

### Stage 1 — admission (`admit.py`)

Refuse before doing any work:

* `fundamental_mode` absent or `mutually_exclusive` empty → refuse. §7.2 already
  requires the designer to declare which inputs cannot change together; without
  it the whole method is unsound and there is nothing to fall back on.
* Any input not covered by a mutual-exclusion group → refuse, naming it.
* A `clock:` block on an asynchronous design → refuse.
* State count above a stated cap (start at 16; make it a constant with a comment
  saying why, not a magic number) → refuse, because stages 2 and 3 are
  exponential and a tool that hangs is worse than one that declines.

### Stage 2 — flow table (`flowtable.py`)

Build the primitive flow table from the FSM spec: rows are states, columns are
input combinations reachable under the declared mutual exclusion, entries are
(next state, output) marked **stable** where next == current.

Then check **fundamental-mode admissibility**: for every transition the spec
declares, exactly one input differs between the source and destination columns.
A transition requiring two simultaneous input changes is refused, naming both
inputs — that is a specification error, and saying so is more useful than
synthesising something for it.

Reduce the table by standard compatible-state merging **only if** you can test
the reduction; an unreduced table is correct, merely larger. Do not merge
unverified — a wrong merge is a silent behaviour change.

### Stage 3 — race-free state assignment (`assign.py`)

Find a **single-variable-change (SVC)** assignment: a map from states to bit
vectors such that every flow-table transition changes exactly one bit. This is a
hypercube embedding problem, and it is a **z3 problem**, not a heuristic:

* variables: one bit-vector per state, width `w`;
* constraints: all assignments distinct; for every transition (s → t), the
  Hamming distance between `code(s)` and `code(t)` is exactly 1;
* start at `w = ceil(log2(n))`, increment on UNSAT up to a stated cap.

Widening `w` is the textbook way to buy race-freedom (spare rows), so a design
that needs 4 bits for 5 states is a normal outcome, not a failure — but the
report must state the width used and why it exceeded the minimum.

If UNSAT at the cap, **refuse**, and use z3's unsat core (or a minimal
falsifying subset you compute yourself) to name the transitions that conflict.
"No assignment exists" is unhelpful; "S2→S4 and S2→S5 both need to be one bit
from S2 and one from each other" is actionable.

Determinism matters (§5.5, byte-identical builds): fix the z3 seed and sort
inputs, and add a test that the same design assigns the same codes twice.

### Stage 4 — hazard-free cover (`cover.py`)

**Do not ask Espresso for this.** §7.3's third problem is precisely that neither
Espresso's heuristic nor `-Dso` guarantees the adjacency condition. Construct
the cover under the standard Nowick–Dill conditions and solve the covering
problem with z3:

* enumerate prime implicants of each output/next-state function over the
  care set;
* for each specified input transition cube `T` (source minterm → destination
  minterm under one input change), where the function is 1 at both ends, `T` is
  a **required cube**: at least one selected product term must contain all of
  `T`. This is what prevents a static-1 hazard;
* a product term that intersects a **privileged cube** without containing it is
  forbidden;
* minimise the number of selected terms subject to those constraints
  (z3 `Optimize`, or iterate a cardinality bound).

Then apply the **≤3-literal constraint**: the G-cell inventory tops out at
fan-in 3, and multi-level factoring of a hazard-free cover is not
hazard-preserving. So a product term with more than three literals is **refused**,
naming the term and the function — it is not decomposed. This converts §7.3's
first unsolved problem into a stated limit with an honest refusal, which is the
whole trick of this package.

Map the resulting AND-OR form directly with a custom `techmap` file rather than
letting ABC restructure it. **ABC must not see this netlist.** If you cannot
prevent that within the existing Yosys script builder, say so plainly in the
notes rather than hoping ABC preserves the structure — it will not.

### Stage 5 — independent hazard verification (`gatepack/verify/hazard.py`)

The safety net, and the reason any of the above is allowed to ship. It reads the
**mapped netlist** — the actual output — and must not import from
`gatepack/synth/async_/`. Enforce that with a test that fails if it does; a
verifier that shares the synthesiser's assumptions verifies nothing.

Two independent checks:

**5a. Ternary (three-valued) simulation.** For every specified single-input
transition: set the changing input to `X`, all others to their stable values,
propagate `X` through the mapped gates with standard 0/1/X truth tables to a
fixed point. Any output whose value is stable across the transition (0→0 or
1→1) but evaluates to `X` has a **potential static hazard** → refuse, naming the
output and the transition. This is decidable, runs on the real netlist, and
catches exactly the damage that factoring or an unexpected mapping would do.

**5b. Icarus glitch simulation.** Drive the same transitions through
`cells_sim.v` under a unit-delay model with per-instance delays perturbed across
several seeds, and assert that a stable output never changes value. Empirical
and complementary — 5a can be conservative, 5b can miss cases, and disagreement
between them is a finding worth reporting rather than smoothing over.

Both run inside `gatepack verify`. A failure in either is a **hard refusal**:
the netlist is not written. Report which check failed and on which transition.

### Reporting

The verdict and `docs/` report must state, every time, in the output itself:

* fundamental mode assumed, and which inputs were declared mutually exclusive;
* the SVC assignment width and whether spares were added;
* the maximum product-term literal count actually used;
* both hazard checks, per transition, pass/fail;
* that the hazard guarantee does **not** extend to concurrent input changes.

## Order of work, and what to do if you run out of time

1, 2, 3 and **5** first. Then 4.

Stage 5 is useful on its own — it can verify any netlist — and stages 1–3 either
produce a valid assignment or a good refusal. Stage 4 without stage 5 is the one
combination this package must never leave behind: synthesis that emits without
independent verification. **If you are running out of time, leave the front-end
refusal in place and ship the checker.** Say so in your notes; that is a good
outcome, not a failure.

## Golden designs

Add async goldens under `tests/golden/designs/` — at minimum:

* one that synthesises cleanly (a two-input, two-state handshake latch or a
  pulse-catcher is the right size);
* one refused for needing a 4-literal term;
* one refused for having no SVC assignment;
* one refused for a two-input simultaneous change;
* one whose cover is *deliberately* hazardous — build it by hand, feed it to
  stage 5 directly, and prove the checker refuses it. **This is the most
  important test in the package.** A hazard checker that has never rejected a
  hazard is the tenth piece of machinery that reports a status while measuring
  nothing.

## Your file scope — nothing outside it

* `gatepack/synth/asynchronous.py`, `gatepack/synth/async_/**` (new)
* `gatepack/verify/asynchronous.py`, `gatepack/verify/hazard.py` (new)
* `gatepack/frontend/frontend.py` (the refusal becomes conditional — nothing else)
* `gatepack/cli.py` (wiring only)
* `tests/unit/test_async_*.py`, `tests/toolchain/test_async_*.py`,
  `tests/golden/designs/*.yaml` (new async goldens only)
* `docs/BUILD-NOTES-async.md`, `docs/handoff/notes-async.md`

**Off-limits**: `gatepack/synth/synchronous.py`, `gatepack/verify/simulation.py`,
`gatepack/verify/equivalence.py`, `gatepack/pack/**`, `gatepack/emit/**`,
`libraries/**`, `examples/**`, `app/**`. Also always off-limits:
`gatepack-design.md`, `docs/*-FINDINGS.md`, `docs/MILESTONE-AUDIT.md`,
`docs/GUI-AUDIT.md`, `app/shared/api.ts`.

Do not change the synchronous path's behaviour in any way. Prove it: the 749
existing tests are your regression suite.

## Acceptance

1. `.venv/bin/python -m pytest -q` — **749 pass, 5 skip** at baseline, all still
   passing plus yours.
2. Every refusal path has a test that reaches it and asserts the *reason text*
   names the specific construct at fault, not a generic message.
3. The hand-built hazardous netlist is refused by stage 5a, and the test fails
   if you weaken the X-propagation.
4. A determinism test: the same async design assigns the same state codes and
   emits the same netlist twice.
5. A test asserting `gatepack/verify/hazard.py` imports nothing from
   `gatepack/synth/async_/`.
6. Anything you claim closes under a real tool must come from
   `gatepack-toolchain:m6` with `-u "$(id -u):$(id -g)"`, transcript in your
   notes.

## Output

`docs/BUILD-NOTES-async.md` and `docs/handoff/notes-async.md`: which stages you
completed, what you guessed, which textbook method you used at each stage and
where you are unsure it is the right one, and the three things you are least
confident about. If you believe a stage is subtly wrong but passing, say so —
notes from previous runs have caught defects the agent could not reach itself.
