# Package: more parts in the library

You are a components engineer. You read datasheets for a living, you know the
difference between a part number convention and a confirmed fact, and you have
seen what happens when a library value nobody checked reaches a fabricated
board.

## The project

`gatepack` compiles a truth table or FSM specification into a bill of materials
and a schematic netlist built from discrete 74AUP logic packages, formally
verifying the result on every build. `libraries/74aup.csv` is the parts library
it maps onto; `libraries/74aup.refs.md` is that library's citation record.

## The task

The library has 22 rows covering 16 cells. That is a thin catalogue: the packer
can only use what the library offers, so a missing dual-gate or a missing
function costs the user real packages on a real board. **Add more parts.**

## The rule that governs everything here

**Never invent an electrical or packaging value.** §1.3 and §23 are absolute:
every value carries a datasheet citation with document number, revision and the
table or page it came from, **or** it is recorded as a placeholder in
`74aup.refs.md`.

A plausible number with a fabricated citation is the worst thing you could do to
this project, and it could reach a physical board. **If you cannot reach a
datasheet, say so and add nothing for that part.** A part left out is a correct
outcome; a part invented is not.

Note what the file already says about itself: the electrical figures for the
existing 16 cells are placeholders, honestly marked. The packaging facts
(`gates_per_pkg`, `package`) for six multi-gate parts *are* verified, with
citations, in the packaging table. That is the standard to meet.

## What "more parts" means, in order of value

### 1. More package variants of cells that already exist (pure data)

The library has `74AUP2G00/2G02/2G04/2G08/2G32` and `74AUP3G04`. The 74AUP
family offers more multi-gate parts than that. Each new multi-gate row lets the
packer put more gates in one package.

**A multi-gate row must have its `gates_per_pkg` and `package` verified against
the manufacturer's datasheet, with a citation added to the packaging table.**
This is not optional and not negotiable: `gatepack build` refuses an unverified
multi-gate part, deliberately, because a wrong `gates_per_pkg` decides which
gates share a die and produces a netlist that physically cannot be built. Adding
an unverified one would break the showcase build, which currently succeeds with
no acknowledgement flag.

### 2. More cell functions (also pure data — check this yourself)

A G-cell's Liberty model *and* its Verilog simulation model are both generated
from the `function` column (`gatepack/liberty/boolean.py`,
`translate`/`translate_verilog`). Read that code and confirm it for yourself
before relying on it. If it holds, a new combinational function — XNOR, 3-input
OR, an AND-OR-invert, a 2:1 multiplexer — is a *data* addition, and the parser
supports `!`, `&`, `|`, `^` and parentheses.

Confirm for each new function cell:
- the function string is what the datasheet says the part does;
- `inputs` matches the number of distinct variables in the function;
- synthesis actually maps something onto it (see "Prove it").

If a function you want cannot be expressed, or the generated model does not
verify, leave it out and say why.

### 3. Second sources

The `mfrs` and `equivalents` columns exist so a BOM is not single-sourced.
Where you can confirm a genuinely pin- and function-compatible part from a
second manufacturer, record it — with a citation. Do not guess compatibility
from a part number that merely looks similar.

## Out of scope

- **Do not** promote the existing 16 cells' placeholder *electrical* values to
  verified as a side effect. If you happen to have a datasheet open and can cite
  the electrical figures for a cell properly, that is welcome — but it is a
  separate, larger job and you must do it *completely and citably* for a cell or
  not at all. Never half-verify a row.
- F-tier (flip-flop), M-tier (macro) and S-tier (supervisor) rows: leave alone
  unless you can cite them fully.
- `area` is gatepack's own cost weight, not datasheet data. Follow the existing
  convention (a larger package costs more in total but less per gate) and say in
  the refs file that it is a design decision, as the file already does.

## Prove it

Do not report a part as working because the row looks right.

The toolchain is **not on your PATH**. It is in the docker image
`gatepack-toolchain:m6`, already built on this machine — this is how
`tests/toolchain/*` run. Mount your own worktree:

```
docker run --rm -v "$PWD:/repo" -w /repo gatepack-toolchain:m6 \
  python3 -m gatepack build examples/pelican/design.yaml \
  --library libraries/74aup.csv --out .gpout/parts --json
```

Required checks, with real output quoted in your notes:

1. `gatepack lib check libraries/74aup.csv` passes — every row has a refs entry.
2. The showcase still builds **with no acknowledgement flag**. If
   `--allow-unverified-gates-per-pkg` becomes necessary, you have added an
   unverified multi-gate part: remove it.
3. `gatepack verify examples/pelican/design.yaml --library libraries/74aup.csv`
   still passes every check. New cells change what synthesis maps onto, so this
   is where a bad Liberty model or a wrong function string shows up as an
   equivalence failure.
4. The full Python suite: `.venv/bin/python -m pytest tests -q` (the venv is
   already linked into your worktree). **The showcase's package count may
   change** — that is the point of adding parts. Several tests pin it
   (`tests/toolchain/test_estimate_build_consistency.py`,
   `tests/golden/test_showcase.py`). If a count changes, update the test **only
   after** confirming from the build output that the new number is right, and
   say explicitly in your notes what changed from what to what and why.
5. For at least one new function cell, show it is actually reachable: a design
   (a golden under `tests/golden/designs/` or a scratch spec) that synthesis
   maps onto it, with the mapped cell counts to prove it. A part nothing can be
   mapped onto is dead weight in the BOM.

## Tests

Add tests that would fail if this work were wrong:

- every row in `74aup.csv` has an entry in the appropriate `74aup.refs.md`
  table, and every multi-gate row (`gates_per_pkg > 1`) has a **packaging**
  citation — not just an electrical one;
- every `function` string parses and yields exactly `inputs` variables;
- the packaging table's `part_number` values all exist in the CSV and vice
  versa, so a citation cannot drift away from its row.

## Files you own

`libraries/**`, new tests under `tests/`, and `tests/golden/designs/**` if you
add a design to demonstrate a new cell.

You may read anything. Do **not** modify `gatepack/**`, `app/**`, or
`examples/**` — another agent is adding bundled examples in this repo right
now. If you find a defect in `gatepack/liberty/**` or `gatepack/parts.py`,
report it in your notes rather than fixing it.

## Report

Write `docs/handoff/notes-parts.md` recording, per part added: the part number,
the datasheet you read (document number and revision), what you confirmed from
it and where in the document, and what remains a placeholder. List separately
anything you *wanted* to add and did not, and why — a part you could not reach a
datasheet for is a result worth recording, not a gap to hide.
