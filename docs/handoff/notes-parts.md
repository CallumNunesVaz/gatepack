# Parts library: more parts — handoff notes

Adds four rows to `libraries/74aup.csv` (three verified multi-gate package
variants, one new combinational function) and their citations to
`libraries/74aup.refs.md`, plus tests that pin the library against its
citation record.

## Parts added (with datasheet, revision, and what each citation covers)

All datasheets are Nexperia product data sheets, fetched from
`assets.nexperia.com` and read in full (text-extracted). "Revision" is the
document ID + release date from each sheet's own revision-history table.

### `74AUP2G86` — XOR2, dual 2-input XOR (multi-gate variant)

- **Datasheet:** Nexperia 74AUP2G86 data sheet, `74AUP2G86 v.11`, release
  `2023-07-31`.
- **Confirmed:** Title *"Low-power dual 2-input EXCLUSIVE-OR gate"* and General
  description *"provides the dual 2-input EXCLUSIVE-OR function"* → `gates_per_pkg=2`.
  Ordering information (Table 1) → package `VSSOP8` (package code SOT765-1),
  CSV spelling `VSSOP-8`.
- **Recorded in:** packaging table, `gates_per_pkg=2, package VSSOP-8`.
- **Still placeholder:** `vcc`/`tpd_ns`/`iq_ua` (mirrored from the existing
  XOR2 row), `mfrs` (`TI;Nexperia`), `area` (2.0, a design weight).

### `74AUP2G34` — BUF, dual buffer (multi-gate variant)

- **Datasheet:** Nexperia 74AUP2G34 data sheet, `74AUP2G34 v.9`, release
  `2023-07-27`.
- **Confirmed:** Title *"Low-power dual buffer"* and General description
  *"is a dual buffer"* → `gates_per_pkg=2`. Ordering information (Table 1) →
  package `TSSOP6` (package code SOT363-2), CSV spelling `SOT-363` (the same
  6-pin package as the existing `74AUP2G04` dual inverter).
- **Recorded in:** packaging table, `gates_per_pkg=2, package SOT-363 (TSSOP6)`.
- **Still placeholder:** electrical figures, `mfrs`, `area` (1.4).

### `74AUP3G34` — BUF, triple buffer (multi-gate variant)

- **Datasheet:** Nexperia 74AUP3G34 data sheet, `74AUP3G34 v.7`, release
  `2024-04-29`.
- **Confirmed:** Title *"Low-power triple buffer"* and General description
  *"is a triple buffer"* → `gates_per_pkg=3`. Ordering information (Table 1) →
  package `VSSOP8` (SOT765-1), CSV spelling `VSSOP-8`.
- **Recorded in:** packaging table, `gates_per_pkg=3, package VSSOP-8`.
- **Still placeholder:** electrical figures, `mfrs`, `area` (2.0).

### `74AUP1G157` — MUX2, single 2-input multiplexer (new function cell)

- **Datasheet:** Nexperia 74AUP1G157 data sheet, `74AUP1G157 v.10`, release
  `2023-07-12`.
- **Confirmed:** General description *"is a single 2-input multiplexer"*.
  Function table (Table 4): `S=L → Y=I0`, `S=H → Y=I1`; Pin description
  (Table 3): pin 1=I1, pin 2=GND, pin 3=I0, pin 4=Y, pin 5=VCC, pin 6=S.
  This is the boolean function `Y = (I0·!S) + (I1·S)`, written for the CSV as
  `function=(A&!C)|(B&C)`, `inputs=3` (A=I0, B=I1, C=S). Package `TSSOP6`
  (SOT363-2), CSV spelling `SOT-363`; `gates_per_pkg=1`.
- **Recorded in:** the new *Function citations* table (keyed `cell_function`,
  deliberately not `cell`, so it is not mistaken for the electrical table).
- **Sourcing:** single-sourced — `mfrs=Nexperia` only. See below.
- **Still placeholder:** `vcc`/`tpd_ns`/`iq_ua` (electrical row
  `placeholder — unverified`), `area` (1.0).

### Sourcing investigation (why `MUX2` is single-sourced)

I did **not** record a second source for `74AUP1G157` because I could not
confirm one, and the task forbids guessing compatibility from a similar part
number:

- **TI** `SN74AUP1G157` — `ti.com/product/SN74AUP1G157` and
  `ti.com/lit/ds/symlink/sn74aup1g157.pdf` both return 404; TI does not offer
  it.
- **Diodes** `74AUP1G157` — `diodes.com` returns 404.
- **Toshiba** `TC7SP157` — the document endpoint is Akamai `Access Denied`
  from this environment (could not reach, so nothing recorded).
- **Nexperia `74LVC1G157`** (a pin/function-compatible single 2-input mux,
  `74LVC1G157 v.12`, `2023-08-15`, function table and pinout identical to
  `74AUP1G157`) was checked as a candidate alternate, but it is the **same
  manufacturer**, so it does not provide second-source relief and was not
  recorded as one.

Consequence: `MUX2` is excluded from the default Liberty file (§10.1 [R4-9])
until a genuine second source is confirmed; `lib gen --allow-single-source`
includes it, and its model is exercised by `tests/toolchain/test_mux2_reachable.py`.

## Proof (real command output)

`gatepack lib check` (exit 0; every row cited, multi-gate rows carry packaging
citations):

```
$ .venv/bin/python -m gatepack.cli lib check libraries/74aup.csv
warning: 17 cell(s) carry unverified/placeholder electrical data
loaded 26 cells from libraries/74aup.csv
dropped 4 cell(s):
  - MUX2: single-sourced — 1 source(s); need >= 2 (use --allow-single-source)
  - DFF_S: single-sourced — 0 source(s); need >= 2 (use --allow-single-source)
  - CNT4: tier — tier 'M' is never an inference target
  - SUPERVISOR: tier — tier 'S' is never an inference target
  summary: single-sourced: 2, tier: 2
citations: all 26 cells have a 74aup.refs.md entry
```

Showcase build (no acknowledgement flag; `ok:true`, `packageCount` still **20**):

```
$ docker run --rm -v "$PWD:/repo" -w /repo gatepack-toolchain:m6 \
    python3 -m gatepack build examples/pelican/design.yaml \
    --library libraries/74aup.csv --out .gpout/parts --json
{"command":"build","data":{...,"packageCount":20,...},"ok":true,"schema":1,"warnings":[]}
```

The package count did **not** change from 20: the pelican showcase maps onto
AND/OR/NAND/NOR/INV/flop cells only, so the new XOR/buffer package variants
(and the single-sourced mux) are not used by it. No golden count needed
updating for the showcase.

`gatepack verify` (every check passes):

```
verification: passed
  equivalence:               passed
  exhaustive simulation:     passed
  mutation:                  passed
      all applicable mutations detected
  flop reset connectivity:   passed
  supervisor parameters:     passed
  property never_walk_with_traffic: passed
  property one_traffic_aspect: passed
```

MUX2 reachability (real Yosys run, single-sourced cell included via
`allow_single_source=True`): the combinational `tests/golden/designs/mux2.yaml`
maps onto the new cell —

```
$ .venv/bin/python -m pytest tests/toolchain/test_mux2_reachable.py -q
1 passed
# mapped cell types of that run:  Counter({'MUX2': 1})
```

Full Python suite:

```
$ .venv/bin/python -m pytest tests -q
675 passed, 5 skipped in 58.24s
```

One existing test changed, and only after confirming the new behaviour:
`tests/unit/test_liberty.py::test_allow_single_source_includes_dff_s` asserted
`len(result.cells) == 14`; with the single-sourced `MUX2` now also eligible
under `allow_single_source`, the count is 15 (13 default + DFF_S + MUX2). The
default cell list (13 cells, no MUX2, no DFF_S) is unchanged.

## What I could not verify, and what I deliberately left out

- **A cross-manufacturer second source for the 2:1 mux** — TI and Diodes do not
  offer a single-gate 2-input multiplexer (404 on both part lookups), Toshiba
  is unreachable from here, and the only confirmed pin-compatible alternate
  (`74LVC1G157`) is the same manufacturer. Recorded above rather than guessed.
- **XNOR, 3-input OR, AND-OR-invert as new functions** — no fixed-function
  74AUP single-gate part exists for these (the AUP single-gate portfolio's only
  new fixed combinational function is the 2:1 mux). Left out; nothing to cite.
- **`74AUP2G157`** — the `2G` prefix looks like a dual mux, but its data sheet
  describes a *single* mux with complementary `Y`/`Ȳ` outputs and an active-low
  enable — not two muxes in one package. Adding it as a dual mux would be a
  wrong `gates_per_pkg`/function, so it was not added.
- **Schmitt-trigger (`74AUP2G14`/`2G17`) and open-drain (`74AUP2G06`/`3G07`)
  variants** — truth-table identical to the existing INV/BUF cells, but the
  Schmitt/open-drain electrical distinction is not representable in the
  `function` column; adding them would mis-describe a plain inverter/buffer.
  Left out.
- **Promoting any electrical value to verified** — deliberately not done. All
  `vcc`/`tpd_ns`/`iq_ua` figures on the new rows remain placeholders, exactly
  like the existing 16 cells, so no row is half-verified. The existing six
  packaging citations were left as they were.

### Note on an existing refs wording, corrected in passing

The packaging-table prose previously described the 6-pin package as
`SOT363 (SC-88)`. The current Nexperia sheets for the 6-pin dual/triple parts
name it `TSSOP6` (package code `SOT363-2`, outline ref SC-88A). I updated that
prose sentence to match, and recorded the new 6-pin parts as `SOT-363 (TSSOP6)`
in their packaging citations. The existing six packaging rows themselves were
not changed.
