# Package L — the asynchronous path has no functional check

Read `docs/handoff/delegation-rules.md` first. Every rule there applies.

## The gap, measured

`gatepack verify` on the bundled asynchronous example reports:

```
verification: passed
  equivalence:               not applicable
      asynchronous designs have no synchronous golden netlist; equivalence is
      not a meaningful check (§7.3)
  hazard (ternary):          passed
  hazard (glitch sim):       passed
```

Three checks, and **not one of them asks whether the netlist implements the
design**. Equivalence is skipped for a defensible reason. The two hazard checks
ask only whether outputs glitch. Nothing plays the role that exhaustive
simulation plays on the synchronous path.

This was measured, not inferred. `tests/toolchain/_async_hazard_injection.py`
drops one z3-selected product term from the cover — exactly what a bug in the
covering constraints would do — and the result is:

```
cover cubes, clean run   [1, 2]
cover cubes, faulty run  [1, 1]      <- the injection fired
hazard (ternary)         passed
hazard (glitch sim)      passed
netlist accessor         RETURNED A NETLIST
```

A netlist that no longer implements the specified machine, reported green. That
probe is committed; read it first.

**This is not a defect in the hazard checker.** Hazards are all it claims to
check and it checks them — the classic `Y = A·B + Ā·C` hazard is detected and the
consensus term clears it. The gap is that nothing else is checked at all.

## What to build

**Exhaustive fundamental-mode simulation of the mapped netlist against the flow
table**, as a first-class check in the asynchronous verification report,
alongside the two hazard checks.

The size cap that stage 1 already enforces is what makes this tractable:
admission refuses designs above a stated state count, so the reachable total
state space is small enough to enumerate rather than sample. **A coverage figure
on random stimulus is a confidence trick and never contributes to a green
status (§C4.3, §21.4)** — enumerate, or report the check as not applicable and
say why.

The shape:

* for every **stable total state** (a state/input combination the flow table
  marks stable), and every **single-input change** admissible under the declared
  mutual exclusion;
* evaluate the mapped netlist to a fixed point — `gatepack/verify/hazard.py`
  already has the binary evaluator and the fixed-point loop;
* compare the settled next-state code and the outputs against what the flow
  table says they must be;
* a mismatch is a **failed check** naming the total state, the input that
  changed, and the expected/actual values. Not a warning.

### Where it lives, and the constraint on that

`gatepack/verify/hazard.py` must keep importing nothing from
`gatepack/synth/async_/` — there is a test that parses its AST to enforce this,
and it exists because a verifier that shares the synthesiser's data structures
verifies nothing. Do not weaken that test.

The functional check needs the **flow table**, which is derived from the *spec*,
not from the cover — so using it is legitimate; it is the specification's own
semantics. `gatepack/verify/asynchronous.py` already re-derives the flow table
and the assignment, so that is the natural home. Think about whether re-deriving
the *assignment* from the same z3 code is circular for your purposes, and say
what you conclude either way — the function under test is the cover, not the
assignment, but the argument is worth making explicitly rather than assuming.

## Acceptance

1. Measure the pytest baseline yourself before you start; everything still
   passes plus yours. The synchronous path must be untouched.
2. **The injection probe must now fail the verification.** Turn
   `tests/toolchain/_async_hazard_injection.py` into a real test: with the cube
   dropped, `verify` reports a failed functional check and no netlist is
   obtainable. This is the acceptance criterion that matters — everything else
   is secondary to it.
3. `examples/async_latch` still verifies green, with the new check passing and
   reported by name.
4. A test that the check enumerates rather than samples — assert the number of
   total-state/input-change pairs it examined, so a future change that quietly
   reduces coverage fails.
5. A test that a design too large to enumerate reports `not applicable` with the
   reason, and that `not applicable` never reads as `passed`.
6. `gatepack/verify/hazard.py`'s independence test still passes, unmodified.
7. Two clean builds of the async example still byte-identical
   (`scripts/repro_check.py`).

## Your file scope — nothing outside it

* `gatepack/verify/asynchronous.py`, `gatepack/async_pipeline.py`
* `gatepack/verify/hazard.py` — **only** if you need a pure evaluator helper
  exposed, and never in a way that adds a synth import; say so in the notes
* `gatepack/report/report.py` (the new check in the async report)
* `tests/toolchain/_async_hazard_injection.py` and
  `tests/toolchain/test_async_*.py`, `tests/unit/test_async_*.py`
* `docs/BUILD-NOTES-asyncfunc.md`, `docs/handoff/notes-asyncfunc.md`

**Off-limits**: `gatepack/synth/**` — the synthesiser is not to be changed to
make the checker pass; if the check finds a real defect in stage 4, **report it,
do not fix it here**. Also `gatepack/verify/simulation.py` and
`equivalence.py` (the synchronous path), `libraries/**`, `app/**`, and as always
`gatepack-design.md`, `docs/*-FINDINGS.md`, `docs/MILESTONE-AUDIT.md`,
`docs/GUI-AUDIT.md`, `app/shared/api.ts`.

## The failure mode to avoid

The version here is a functional check that enumerates a subset it happens to
get right, passes on the injection probe, and reports green. **If you cannot
make the injected fault fail the verification, you have not built the check** —
say so, and leave the gap recorded rather than closed on paper.

## Output

`docs/BUILD-NOTES-asyncfunc.md` and `docs/handoff/notes-asyncfunc.md`: what the
check enumerates and what it cannot reach, what you concluded about re-deriving
the assignment, anything the check found in stage 4, and the three things you
are least confident about.
