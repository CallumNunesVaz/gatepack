# BUILD-NOTES — gates_per_pkg verification (multi-gate packaging facts)

Scope: separate `gates_per_pkg`/`package` verification from electrical-value
verification, cite the six multi-gate parts against real datasheets, and make
the showcase build out-of-the-box against the full library.

## What I implemented

### Packaging verification is a separate axis

`Part` previously carried a single `verification` flag that conflated electrical
values (`vcc`/`tpd`/`iq`/`area`) with packaging facts (`gates_per_pkg`,
`package`). That made a verified gate count read the placeholder electrical data
as verified — exactly the §1.3 / §23 collapse the gate exists to prevent.

- `gatepack/parts.py`: `Part` gains `packaging_verification` (default
  `PLACEHOLDER`) and `packaging_is_verified`. `unverified_multi_gate_parts()` now
  keys on `packaging_is_verified`. `mark_packaging_verification()` attaches
  packaging status **keyed by `part_number`** (not `cell`), because one function
  cell is offered as several packages (`AND2` = `74AUP1G08` single and
  `74AUP2G08` dual) and a cell-level citation cannot say which was confirmed.
- `gatepack/refs.py`: the refs file now holds two markdown tables — an
  **electrical** table keyed by `cell` (unchanged columns) and a **packaging**
  table keyed by `part_number`. `parse_refs` / `parse_refs_packaging` split them
  by header; `load_parts_cited` attaches both.
- `gatepack/build.py`: the build gate (`_gate_unverified_gates_per_pkg`) now
  refuses on `packaging_is_verified`, not `is_verified`. A part can therefore
  have a confirmed gate count/package while its electrical figures remain
  placeholders — which is the honest state of every multi-gate row today.

### Citations

`libraries/74aup.refs.md` gains a packaging table citing Nexperia data sheets for
all six multi-gate rows. Gate counts and packages were confirmed:

| part_number | gates_per_pkg | package (CSV) | Nexperia package |
|-------------|---------------|---------------|------------------|
| 74AUP2G00 | 2 (dual 2-input NAND) | VSSOP-8 | VSSOP8 (SOT765-1) |
| 74AUP2G02 | 2 (dual 2-input NOR) | VSSOP-8 | VSSOP8 (SOT765-1) |
| 74AUP2G04 | 2 (dual inverter) | SOT-363 | SOT363 (SC-88) |
| 74AUP2G08 | 2 (dual 2-input AND) | VSSOP-8 | VSSOP8 (SOT765-1) |
| 74AUP2G32 | 2 (dual 2-input OR) | VSSOP-8 | VSSOP8 (SOT765-1) |
| 74AUP3G04 | 3 (triple inverter) | VSSOP-8 | VSSOP8 (SOT765-1) |

The electrical table is untouched: all 16 cells remain `placeholder —
unverified`. The `gatepack lib check --json` contract (which asserts the whole
library is electrically unverified) still holds.

## Verified end-to-end

- `env -i HOME=/tmp app/resources/bin/gatepack build examples/pelican/design.yaml
  --library libraries/74aup.csv --out .gpout/firstrun --json` → `ok`, **20
  packages**, no acknowledgement flag (the bundled frozen core + bundled
  toolchain, no PATH).
- `env -i HOME=/tmp app/resources/bin/gatepack verify …` → **all seven checks
  pass** (equivalence, exhaustive simulation, mutation, flop reset connectivity,
  supervisor parameters, both sby properties).
- The same command in `gatepack-toolchain:m6` (source checkout) → 20 packages,
  no flag.
- New e2e test `app/tests/e2e/showcase-build.spec.ts` drives the **real** main
  process with `GATEPACK_CORE` = the frozen binary and `PATH=''`, and asserts the
  first-launch showcase builds to 23 packages (its embedded single-gate library).

## What I guessed / did not verify

- **Revision label.** The Nexperia "revision" I cite is the data-sheet release
  date from each PDF's embedded XMP metadata (e.g. `2023-07-19`). Nexperia data
  sheets also carry a `Rev. n` label in their `Revision history` table, which I
  could not read back (the PDF text streams are compressed). The date is real and
  pinnable; the `Rev. n` is not recorded.
- **Package spelling.** The CSV spells the 8-pin package `VSSOP-8`; Nexperia
  spells it `VSSOP8` (package code SOT765-1). Same physical package, different
  spelling — the discrepancy is documented in the refs file rather than silently
  rewritten.
- **Single-gate packages.** Only the multi-gate rows were in scope. The
  single-gate rows' `SOT-353`/`SOT-23`/`SO-16` package claims, and every
  electrical value, remain unverified placeholders.

## Weakest points / suspicions

1. **`BomRow.unverified` and the report note still name `gates-per-package` among
   the "electrical figures"** (`gatepack/emit/bom.py`, `gatepack/report/report.py`
   — both outside my file scope). The field itself is still correct (it reflects
   the *electrical* axis), but the human-facing parenthetical is now imprecise:
   multi-gate parts have a verified gate count while still being listed as
   "unverified" for their electrical data. Worth a wording pass later.
2. **The e2e test exercises the app's single-gate build (23 packages), not the
   20-package multi-gate pack.** The gates_per_pkg gate is exercised by the CLI
   full-library build (docker + frozen binary) and the toolchain tests, not by
   the app, because the app builds the showcase against its embedded library
   subset. If the showcase were ever switched to the full library, the e2e
   assertion (23) would need to move to 20 — and would then exercise the gate
   directly.
3. **A cell-level electrical citation still applies to every package of that
   cell.** `parse_refs` returns one electrical status per `cell`, so `INV`'s
   placeholder status attaches to `74AUP1G04`, `74AUP2G04` and `74AUP3G04`
   alike. That is correct for now (all electrical data is placeholder) but will
   need per-part electrical citations when the electrical job is taken on.
