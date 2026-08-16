# Package: make unverified data impossible to ship by accident

You are an engineer who has watched a project ship a plausible-looking number
that nobody had checked, and who thinks the fix is structural rather than a
warning in a log.

## The project

`gatepack` compiles a truth table or FSM specification into a bill of materials
and a schematic netlist built from discrete 74AUP logic packages, formally
verifying the result on every build. Its governing rule (§1.3, §23) is that
**no electrical value is ever invented**: every value in `libraries/74aup.csv`
must carry a datasheet citation with document revision and table or page, and
values without one are marked as placeholders.

You are not being asked to source datasheet values. You cannot, and inventing
one would be the worst thing you could do to this project. You are being asked
to make the unverified ones impossible to mistake for verified ones.

## Problem 1 — 16 of 22 cells carry placeholder electrical data

```
$ ./start cli lib check libraries/74aup.csv
warning: 16 cell(s) carry unverified/placeholder electrical data
citations: all 22 cells have a 74aup.refs.md entry
```

A warning on a command nobody has to run. `gatepack build` proceeds silently and
emits a BOM and a report containing those numbers, with nothing in the output
saying which are real.

The sharpest case is not tPD. It is **`gates_per_pkg` on the multi-gate rows**.
That value decides how many physical packages the board needs and which gates
share a die. A wrong one yields a netlist that **physically cannot be built** —
a far worse failure than a wrong propagation delay, and it is currently an
unverified claim sitting beside verified ones.

What to build:

- **Distinguish the values structurally**, not by a note. A placeholder value
  should be a different thing in the data model from a cited one, so that any
  code path consuming it has to acknowledge which it has.
- **Propagate it into the outputs.** The BOM, the report and the `--json`
  envelopes must mark which figures rest on unverified data. A reader of
  `report.md` should not have to go back to the CSV to find out.
- **Gate the dangerous one.** `gates_per_pkg` being unverified is a
  build-affecting claim: make the build refuse, or require an explicit
  acknowledgement flag, rather than proceeding quietly. Decide which, argue for
  it in your notes, and make the refusal message say exactly what is unverified
  and what could go wrong. Follow the precedent already set by
  `--allow-single-source`.
- Surface the count in `gatepack doctor` output so it is visible without running
  a separate command.

## Problem 2 — M8 rests on a sample of one

The macro verification story is: the specification side of formal equivalence
reads an independent model (`gatepack/macros/specs.py` generates
`cells_spec.v`), while the gate side reads the hand-written implementation model
(`gatepack/macros/models/CNT4.v`). Mutating the implementation is therefore
caught. Verified against real Yosys 0.23: counting by two instead of one
produces `ERROR: Found 4 unproven $equiv cells`.

`CNT4` is the **only** M-cell in the library, so that property is demonstrated
once. And nothing *requires* a macro to have a specification model before it can
be used — `get_spec` raises rather than degrading silently, which fails loudly,
but it is a guard, not a gate.

What to build:

- **Make the spec model mandatory.** Adding an M-cell to a library without a
  corresponding entry in `specs.py` must fail at library load or at compile,
  with a message explaining that a macro without an independent specification
  model cannot be verified — not at the point someone happens to run
  equivalence. Test that a macro without one is rejected.
- **Add a second M-cell so the property is demonstrated more than once.** It
  must be synthetic (§1.3 — every bundled example is), it must have both an
  implementation model and an independently written specification model, and the
  mutation test must cover it: mutate the implementation, confirm equivalence
  fails; restore, confirm it passes. A shift register or a Johnson counter is a
  natural second case because its failure mode differs from a binary counter's.
  Use the real toolchain — `gatepack-toolchain:m6` has Yosys 0.23 — and never a
  fake runner.
- If you add a physical part row for it, **every electrical value must be a
  marked placeholder with no invented number**, consistent with problem 1. It is
  entirely acceptable for the new M-cell to be verification-only and carry no
  physical binding at all; say which you chose and why.

## Rules specific to this package

- **Never invent an electrical value.** Not a tPD, not a current, not a
  `gates_per_pkg`. A placeholder marked as such is correct; a plausible number
  is a defect that could reach a physical board.
- Every test must be able to fail. Break the thing, watch it go red, restore,
  and report what the failure looked like.

## Files you own

`libraries/**`, `gatepack/parts.py`, `gatepack/macros/**`,
`gatepack/liberty/**`, `gatepack/report/**`, and new tests under `tests/`.

## Off-limits — three other agents are in this repo right now

- `app/**` entirely — two agents are in the renderer and one owns
  `app/shared/api.ts` and `app/main/core.cts`. If a `--json` payload needs a new
  field to carry the verified/placeholder distinction, **describe it in your
  notes** rather than editing the contract; the core side is yours to build.
- `scripts/**`, `gatepack/toolchain.py`, `gatepack/doctor.py`, `Dockerfile*`,
  `.github/**` — the toolchain agent. `gatepack doctor`'s placeholder count is
  the one exception: put the *data* in place and note what doctor should read,
  rather than editing `doctor.py`.
- `gatepack/cli.py` — the exit-code agent.
- `docs/MILESTONE-AUDIT.md`, `gatepack-design.md` — inputs.
