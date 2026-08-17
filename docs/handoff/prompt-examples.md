# Package: more worked examples, bundled with the program

You are a digital-logic engineer who writes teaching examples: small circuits
that are honest about what they are, that build first time, and that each show
one thing the last one did not.

## The project

`gatepack` compiles a truth table or FSM specification into a bill of materials
and a schematic netlist built from discrete 74AUP logic packages, formally
verifying the result on every build. The desktop app and the CLI both ship a set
of bundled example projects; the app opens one (the "showcase") on first launch,
and `gatepack examples list` / `gatepack examples extract <name> <dir>` reach
the same set from the command line.

## The task

**There is exactly one bundled example today — `examples/pelican`.** One example
cannot show the range of what the tool does. Add more.

Add **at least four** new bundled examples. Each must:

1. Teach something the others do not. Between them, cover at least:
   - a purely **combinational** design (`states: [S0]`, one self-transition,
     all the work in `output_logic:`) — decoders, encoders, comparators,
     multiplexers, parity;
   - a **sequential** design with real state — a sequence detector, a stepper
     sequencer, a debounce/hold timer;
   - a design with **asynchronous inputs** that must be synchronised
     (`sync: true`), since that is a §9.3 feature nothing but the showcase
     currently demonstrates;
   - a design in the **smallest useful size** — something a reader can hold in
     their head completely, three or four gates, as the first thing to open
     after the showcase.
   Beyond those four, add more if you have something worth showing (an
   `asynchronous` `timing_model` with `fundamental_mode`, a design with
   `properties:` that genuinely prove, an M-cell macro). Argue for what you add.
2. **Build and verify for real.** See "Prove it" below. An example that does not
   build is worse than no example.
3. Be **synthetic** (§1.3): written for this project, not derived from any real
   product, installation, standard or datasheet application note. Say so in the
   header comment, as `examples/pelican/design.yaml` does.
4. Carry a header comment in the same voice as the showcase: what the circuit
   is, why someone would look at it, and what it demonstrates. **The first
   non-empty comment line becomes the example's one-line summary** in
   `examples list` and in the app (`gatepack/examples.py::_summary`) — write
   that line deliberately.

## The rule that governs this package

**Never invent an electrical or packaging value.** §1.3 and §23 are absolute.
You are not adding parts data here and you must not: use only cells that already
exist in `libraries/74aup.csv`, and if an example ships its own `parts.csv`
(the showcase does), copy the rows **verbatim** from `libraries/74aup.csv`.
Never edit a value, never add a row, never touch `libraries/74aup.refs.md`.

If a design you want needs a cell the library does not have, the design is out
of scope — pick another. Say so in your notes rather than adding the cell.

## Prove it

Do not report an example as working because the YAML looks right.

The native toolchain ships inside the app at `app/resources/bin/gatepack`, so
this runs with nothing installed:

```
app/resources/bin/gatepack build examples/<name>/design.yaml \
  --library libraries/74aup.csv --out .gpout/<name> --json
app/resources/bin/gatepack verify examples/<name>/design.yaml \
  --library libraries/74aup.csv --json
```

For each new example, record in your notes: the package count, the verdict, and
which checks ran. **A build that needs `--allow-unverified-gates-per-pkg` is a
failure** — the showcase builds without it and so must these.

If a check reports `not_run`, say which and why; do not present a partial
verification as a pass.

## Tests

Add a test that iterates **every** bundled example and asserts it builds and
verifies — not a hand-written list that a future example can be added without
joining. Put the toolchain-dependent part under `tests/toolchain/` alongside the
existing toolchain tests (they skip when the toolchain is absent); anything that
can be checked without the toolchain (every example parses, has a summary line,
has a design.yaml, names only cells the library defines) belongs in
`tests/unit/`.

The point of that test is that it fails if someone adds a broken example.

## Also check, and fix if wrong

- `gatepack examples list` shows every new example with its summary.
- `gatepack examples extract <name> <dir>` produces a directory that builds.
- The frozen build finds them: `scripts/bundle_core.py` collects `examples/`
  via PyInstaller `--add-data`, and a *new directory* must come along. Verify
  with the bundled binary and a scrubbed environment:
  `env -i HOME=/tmp app/resources/bin/gatepack examples list`.
  (This has bitten before — the bundle shipped with `examples/` missing
  entirely and reported "no bundled examples found" with exit 0.)
- Do **not** add `.gpk` files. The showcase ships one because it predates the
  known defect that a `.gpk` round-trip loses comments and key order; a new
  example shipping a lossy copy of itself would be a trap.
- `examples/pelican` stays the showcase (`SHOWCASE = "pelican"`); do not change
  which project opens on first launch.

## Files you own

`examples/**`, new tests under `tests/`, and `docs/EXAMPLES.md` if you think the
set deserves an index (optional — argue for it).

You may read anything. Do not modify `libraries/**`, `gatepack/**` source, or
anything under `app/` except to *run* the bundled binary — if you find a defect
in `gatepack/examples.py` or the bundling, **report it in your notes rather than
fixing it**, unless it makes the task impossible, in which case fix the minimum
and flag exactly what you changed.

## Report

Write `docs/handoff/notes-examples.md` recording, per example: what it teaches,
its package count, its verification verdict, and anything you guessed or left
unfinished. An honest account of a partial result is worth more than an
optimistic one.
