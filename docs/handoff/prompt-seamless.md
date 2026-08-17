# Package: the showcase must build out of the box

You are an engineer who takes "it works on first run, with nothing installed"
as a hard requirement rather than an aspiration.

## The project

`gatepack` compiles a truth table or FSM specification into a bill of materials
and a schematic netlist built from discrete 74AUP logic packages, formally
verifying the result on every build. The desktop app opens a bundled showcase
project (the pelican crossing) on first launch — it is the tour of the tool.

The native toolchain now ships inside the app: yosys, abc, iverilog, vvp, sby,
z3 in `app/resources/bin/`, built by `scripts/bundle_toolchain.py`. Verified —
with `env -i` and no PATH at all, `gatepack verify` passes equivalence,
exhaustive simulation, mutation and both sby properties.

## The requirement

**The showcase must build on first run with nothing else installed.** The
maintainer's words: *"this whole program needs to contain all the necessary
tools and library components to get the design process going seamlessly."*

It does not. Press Build and you get:

```
error: AND2, OR2: gates_per_pkg is unverified/placeholder for the multi-gate
part(s) 74AUP2G08 (gates_per_pkg=2, 2 gate(s) sharing a die); 74AUP2G32
(gates_per_pkg=2, 2 gate(s) sharing a die). This value decides which gates
share a die and how many physical packages the board needs — a wrong value
produces a netlist that physically cannot be built.
```

That gate is correct and must stay. `gates_per_pkg` decides which gates share a
die; a wrong value yields a board that cannot be built. The right fix is to
**verify the values**, not to weaken the gate.

## What to do

### 1. Verify `gates_per_pkg` against real datasheets

This is the core of the task and the one rule that governs it: **never invent an
electrical or packaging value.** §1.3 and §23 are absolute — every value carries
a datasheet citation with document revision and table or page, or it is marked a
placeholder.

`gates_per_pkg` is the most tractable of these because it is a *packaging* fact,
not an electrical one: a 74AUP2G08 is a dual 2-input AND gate, and the "2G" in
the part number is the manufacturer's own convention for the gate count. That
still needs confirming from the datasheet itself — the part number convention is
strong evidence, not a citation.

For each multi-gate part in `libraries/74aup.csv`, find the manufacturer
datasheet (TI, Nexperia, Diodes), confirm the gate count and the package, and
record the citation in `libraries/74aup.refs.md` in the format the file already
uses — document number, revision, and the table or page the value came from.
Then mark the value verified so the gate stops firing.

**If you cannot reach a datasheet, say so and stop there for that part.** An
unverified part left honestly unverified is a correct outcome. A plausible
number with a fabricated citation is the worst thing you could do to this
project, and it could reach a physical board.

Whatever you verify, verify only `gates_per_pkg` and `package` unless a
datasheet gives you the electrical values too — the 16 cells carrying
placeholder electrical data are a separate, larger job and are not in scope.

### 2. Make the showcase's path work end to end

After verification, confirm — do not assume:

```
env -i HOME=/tmp app/resources/bin/gatepack build examples/pelican/design.yaml \
  --library libraries/74aup.csv --out .gpout/firstrun --json
```

succeeds with no acknowledgement flag, produces 20 packages, and that
`gatepack verify` still passes all seven checks. Then drive the **app** the same
way — the e2e suite (`app/tests/e2e/`) can launch the real main process with
`GATEPACK_CORE` pointed at the bundled binary. Add a test that the showcase
builds from a first launch with nothing on PATH. That test is the requirement,
stated executably.

### 3. If some parts stay unverified

Then the showcase still must build. Options, in order of preference — argue for
the one you pick:

- Ship the showcase against a library subset containing only verified parts.
  The build uses more packages (23 rather than 20) and that is fine; a correct
  BOM that is bigger beats a refusal.
- Have the app surface the refusal as an actionable prompt rather than a wall,
  with the acknowledgement as a deliberate one-click choice.

What is **not** acceptable is the app passing `--allow-unverified-gates-per-pkg`
silently on the user's behalf. That would make the gate decorative, which is the
exact failure this project exists to avoid.

## Files you own

`libraries/**`, `examples/**`, `gatepack/parts.py`, `gatepack/build.py`,
`app/tests/e2e/**`, and new tests under `tests/`.

## Off-limits — another agent is in this repo right now

`.github/**`, `app/electron-builder.yml`, `scripts/bundle_core.py`,
`docs/RELEASING.md`, `app/signing/**` — the signing agent.

Also: `docs/MILESTONE-AUDIT.md`, `gatepack-design.md` — inputs.
