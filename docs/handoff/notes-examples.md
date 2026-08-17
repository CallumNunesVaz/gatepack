# Handoff notes — bundled examples

Added five new bundled examples alongside the `pelican` showcase, each teaching
one thing the others do not, plus toolchain/unit tests that iterate the whole
set (never a hand-written list). Every example was built and verified against
the real toolchain in `gatepack-toolchain:m6`; the output is quoted below.

## What I added

| example | category it covers | what it teaches | packages |
|---|---|---|---|
| `parity` | purely combinational | `states: [S0]` with one self-transition, all work in `output_logic`; an XOR tree `a ^ b ^ c` mapping to two 74AUP 1G86 gates | 2 |
| `mux2to1` | smallest useful size | a 2:1 multiplexer held entirely in the head; De Morgan's mapping of `(s & a) \| (!s & b)` to one inverter + three NAND2s | 3 |
| `sequence_detector` | sequential, real state | an overlapping "101" detector; the overlap decision (from the match state a `1` returns to S1, not S0) is where hand-written FSMs go wrong | 14 |
| `debounce` | asynchronous input, `sync: true` | §9.3 made concrete: a push button is asynchronous, gatepack emits the two-flop synchroniser, and a three-cycle hold rejects ~30 ms of bounce | 12 |
| `power_sequencer` | `properties:` that genuinely prove | a stepper sequencer with a `kind: liveness` property ("eventually ready"), discharged as §21.5 bounded reachability | 10 |

Headers are in the showcase's voice, each first non-empty comment line is the
deliberate one-liner that `examples list` and `gatepack/examples.py::_summary`
pick up, and each header states the design is synthetic (§1.3). None ships a
`parts.csv` (only the showcase does); none ships a `.gpk`.

### Why these five and not the other suggested ones

- **No `asynchronous` `timing_model` with `fundamental_mode`** — impossible
  today, not a choice. `gatepack/frontend/frontend.py::compile_design` raises
  `AsyncRefused` for `timing_model: asynchronous`, so such an example cannot
  build. Documented rather than faked.
- **No M-cell macro example** — I wrote one (`examples/counter`, a CNT4
  counter) and then deleted it because it does not build. See "Defects found"
  below.
- **A liveness property instead of a second mutex** — the showcase already
  proves mutexes (`never_walk_with_traffic`, `one_traffic_aspect`); `power_sequencer`
  demonstrates the `liveness` kind, which nothing else in the set shows.

## Build and verify results (real output, per example)

Run with `docker run --rm -v "$PWD:/repo" -w /repo gatepack-toolchain:m6
python3 -m gatepack <build|verify> examples/<name>/design.yaml --library
libraries/74aup.csv`. No example needed `--allow-unverified-gates-per-pkg`.

### parity — 2 packages

```
build (JSON): ok=true packageCount=2
  bom: 74AUP1G86 x2 (both XOR gates)
verify:
  verification: passed
    equivalence:               passed
    exhaustive simulation:     passed
    mutation:                  passed (all applicable mutations detected)
    flop reset connectivity:   passed
    supervisor parameters:     passed
    mutation nand_to_and:      not applicable
    mutation flop_d_invert:    not applicable
    mutation reset_polarity_flip: not applicable
```

The three mutations report `not applicable` (not `not detected`): the mapped
netlist is two XOR gates with no NAND2 and no flop (the single one-hot state
flop is optimised away because a purely combinational design has no state), so
the flop/NAND mutations are category errors, kept out of the vacuity verdict.

### mux2to1 — 3 packages

```
build (JSON): ok=true packageCount=3 spare=1
  bom: 74AUP1G04 x1 (INV), 74AUP2G00 x2 (dual NAND2, one spare slot)
verify:
  verification: passed
    equivalence:               passed
    exhaustive simulation:     passed
    mutation:                  passed
    flop reset connectivity:   passed
    supervisor parameters:     passed
    mutation nand_to_and:      detected
    mutation flop_d_invert:    not applicable
    mutation reset_polarity_flip: not applicable
```

### sequence_detector — 14 packages

```
build (JSON): ok=true packageCount=14 spare=3
  bom: 74AUP1G04 x1, 74AUP1G175 x6, 74AUP1G27 x2, 74AUP2G02 x1,
       74AUP2G08 x2, 74AUP2G32 x2
verify:
  verification: passed
    equivalence:               passed
    exhaustive simulation:     passed
    mutation:                  passed
    flop reset connectivity:   passed
    supervisor parameters:     passed
    mutation nand_to_and:      not applicable
    mutation flop_d_invert:    detected
    mutation reset_polarity_flip: detected
```

### debounce — 12 packages

```
build (JSON): ok=true packageCount=12 spare=2
  bom: 74AUP1G175 x8, 74AUP1G27 x1, 74AUP2G08 x2, 74AUP2G32 x1
verify:
  verification: passed
    equivalence:               passed
    exhaustive simulation:     passed
    mutation:                  passed
    flop reset connectivity:   passed
    supervisor parameters:     passed
    mutation nand_to_and:      not applicable
    mutation flop_d_invert:    detected
    mutation reset_polarity_flip: detected
```

### power_sequencer — 10 packages

```
build (JSON): ok=true packageCount=10 spare=2
  bom: 74AUP1G175 x6, 74AUP1G27 x1, 74AUP2G02 x1, 74AUP2G08 x1, 74AUP2G32 x1
verify:
  verification: passed
    equivalence:               passed
    exhaustive simulation:     passed
    mutation:                  passed
    flop reset connectivity:   passed
    supervisor parameters:     passed
    property eventually_ready: bounded pass (bound 64)
        cover gp_cover_0 reached in step 11 (M6-FINDINGS §4)
    mutation nand_to_and:      not applicable
    mutation flop_d_invert:    detected
    mutation reset_polarity_flip: detected
```

The liveness property is correctly reported `bounded pass` with its depth, never
a green `passed` — that is the §21.5 four-state model working, not a partial
verification. `gatepack verify` exits 0 for it (no check is `failed` or `not
run`).

## Tests added

- `tests/unit/test_examples.py` (5 tests, toolchain-free): every example
  directory has a `design.yaml` and is discovered by `list_examples()`; every
  example parses/compiles; every example has a non-empty summary line; any
  example `parts.csv` is a verbatim row-subset of `libraries/74aup.csv`; no
  non-showcase example ships a `.gpk`. All walk `examples_root()` — no
  hand-written name list.
- `tests/toolchain/test_examples.py` (2 tests x N examples, skips when the
  toolchain image is absent): every example from `list_examples()` builds
  (`--json`, assert `ok` and `packageCount >= 1`) and verifies (assert exit 0,
  `equivalence: passed`, and no `not run`). Ran for real: 12 passed.

Results: `tests/unit` 546 passed (was 541); `tests/contract` 44 passed;
`tests/toolchain/test_examples.py` 12 passed.

## Defects found (reported, not fixed — gatepack source is off-limits)

1. **An M-cell macro cannot be built into a BOM.** My `counter` example (a CNT4
   counter) "built" with `ok=true packageCount=0` and an empty BOM. Two causes,
   both in code I may not modify:
   - The macro's `Q` output is an internal wire that is never routed to a design
     output, so Yosys optimises the `(* blackbox *)` instance away during
     synthesis — `mapped.v` contains no `CNT4` instance.
   - Independently, `gatepack/netlist.py::load_mapped_json` reads
     `top, module = next(iter(modules.items()))`, i.e. the *first* module in
     `mapped.json`. When a macro is present that module is the empty `CNT4` stub,
     not the design module, so the cells are read from the wrong module even if
     the instance survived.
   I deleted `examples/counter` rather than ship an example that "builds" to
   0 packages (the task's "an example that does not build is worse than no
   example").

2. **`asynchronous` `timing_model` is refused by the front-end** (`AsyncRefused`),
   so the suggested `fundamental_mode` example is out of scope until async
   synthesis lands (§7.3 / §23.3).

## The frozen bundle

`scripts/bundle_core.py` collects examples with
`--add-data f"{REPO / 'examples'}{os.pathsep}examples"` (bundle_core.py:158-159),
which folds the whole `examples/` tree into the extraction root. A **new example
directory is therefore collected automatically** — nothing in `examples/` is
enumerated by name in the bundler, so the new directories ride along. The frozen
binary itself is a gitignored build artefact (`app/resources/bin/` is absent from
this worktree), was frozen before this work, and cannot see the new examples
until the maintainer rebuilds. I could not run it to confirm; the mechanism is
correct as written.

## What I could not verify

- The frozen binary / packaged app: not present in the worktree, not rebuilt by
  me. The bundler mechanism is confirmed by reading it; the actual bundle is the
  maintainer's to rebuild and confirm.
- The one thing I removed (`counter`) is documented above rather than shipped.

## Guesses / judgements

- `debounce` uses a 100 Hz clock so "three stable cycles ≈ 30 ms" is a
  defensible bounce window; the two-flop synchroniser adds two further cycles of
  raw-input latency, which the header does not dwell on (it is about the FSM's
  own hold count, not the total pin-to-output delay).
- I chose not to add `docs/EXAMPLES.md` (the task's optional index): each
  example's header already carries its own summary and purpose, and
  `examples list` surfaces them. An index would be a second place to keep in
  sync for little gain at five examples.
