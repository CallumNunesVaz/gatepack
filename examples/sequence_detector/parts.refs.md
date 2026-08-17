# 74AUP cell library — datasheet citations

> **STATUS: electrical values are still PLACEHOLDER — NOT DESIGN DATA.**
>
> No *electrical* value in `74aup.csv` has been verified against a datasheet.
> Every `vcc_min`/`vcc_max`, `tpd_ns` and `iq_ua` figure, every manufacturer
> list, and every part number below is a plausible placeholder pending
> datasheet confirmation (§10.1, §19 R8: nothing is inferred or remembered).
> None of these values are to be used as design data until the `datasheet`,
> `revision` and `table/page` columns are filled in from a real, pinned
> document revision. See `docs/BUILD-NOTES.md`.
>
> `area` is **not** datasheet data at all: it is gatepack's own cost weight,
> chosen so a larger package costs more in total but less per gate. It is a
> design decision, documented here so it is not mistaken for a measurement.

> **Packaging (gates_per_pkg + package) is verified for the multi-gate parts.**
> The nine multi-gate rows below (`74AUP2G00`, `74AUP2G02`, `74AUP2G04`,
> `74AUP2G08`, `74AUP2G32`, `74AUP2G86`, `74AUP2G34`, `74AUP3G04`,
> `74AUP3G34`) have their gate count and package confirmed against Nexperia
> data sheets (see the *packaging* table). A wrong `gates_per_pkg` produces a
> netlist that physically cannot be built, which is why it is gated on its own
> citation; it does **not** promote the placeholder electrical figures on those
> rows to verified. The cells carrying placeholder electrical data remain a
> separate, larger job and are out of scope here.

`gatepack lib check` fails if a row in `74aup.csv` has no entry in the
electrical table.

| cell | datasheet | revision | table/page | electrical status |
|------|-----------|----------|------------|-------------------|
| INV | TBD | TBD | TBD | placeholder — unverified |
| BUF | TBD | TBD | TBD | placeholder — unverified |
| NAND2 | TBD | TBD | TBD | placeholder — unverified |
| NAND3 | TBD | TBD | TBD | placeholder — unverified |
| NOR2 | TBD | TBD | TBD | placeholder — unverified |
| NOR3 | TBD | TBD | TBD | placeholder — unverified |
| AND2 | TBD | TBD | TBD | placeholder — unverified |
| AND3 | TBD | TBD | TBD | placeholder — unverified |
| OR2 | TBD | TBD | TBD | placeholder — unverified |
| XOR2 | TBD | TBD | TBD | placeholder — unverified |
| MUX2 | TBD | TBD | TBD | placeholder — unverified |
| DFF | TBD | TBD | TBD | placeholder — unverified |
| DFF_R | TBD | TBD | TBD | placeholder — unverified |
| DFF_S | TBD | TBD | TBD | placeholder — unverified (no candidate part yet, §9.2) |
| DFF_SR | TBD | TBD | TBD | placeholder — unverified |
| CNT4 | TBD | TBD | TBD | placeholder — unverified (74LVC161 candidate, §9.4) |
| SUPERVISOR | TBD | TBD | TBD | placeholder — unverified (TPS3839 candidate, §9.5) |

## Packaging citations (gates_per_pkg + package)

Keyed by part number, because one function cell is offered as several packages
(`AND2` = `74AUP1G08` single-gate and `74AUP2G08` dual-gate); a cell-level
citation cannot say which of them had its gate count confirmed. The revision is
the data-sheet release date recorded in each PDF's embedded metadata. Nexperia
names the 8-pin package `VSSOP8` (package code SOT765-1) and the 6-pin package
`TSSOP6` (package code SOT363-2); the CSV spells them `VSSOP-8` and `SOT-363`.
(The dual single-input gates `74AUP2G04`/`74AUP2G34` and the single mux
`74AUP1G157` are 6-pin TSSOP6 parts; the dual two-input gates are 8-pin VSSOP8.)

| part_number | datasheet | revision | table/page | packaging status |
|-------------|-----------|----------|------------|------------------|
| 74AUP2G00 | Nexperia 74AUP2G00 data sheet | 2024-08-12 | Title ("dual 2-input NAND gate"); Ordering information (Table 3) | verified — gates_per_pkg=2, package VSSOP-8 |
| 74AUP2G02 | Nexperia 74AUP2G02 data sheet | 2024-04-26 | Title ("dual 2-input NOR gate"); Ordering information (Table 3) | verified — gates_per_pkg=2, package VSSOP-8 |
| 74AUP2G04 | Nexperia 74AUP2G04 data sheet | 2023-07-19 | Title ("dual inverter"); Ordering information (Table 3) | verified — gates_per_pkg=2, package SOT-363 |
| 74AUP2G08 | Nexperia 74AUP2G08 data sheet | 2023-07-19 | Title ("dual 2-input AND gate"); Ordering information (Table 3) | verified — gates_per_pkg=2, package VSSOP-8 |
| 74AUP2G32 | Nexperia 74AUP2G32 data sheet | 2024-08-12 | Title ("dual 2-input OR gate"); Ordering information (Table 3) | verified — gates_per_pkg=2, package VSSOP-8 |
| 74AUP2G86 | Nexperia 74AUP2G86 data sheet | 2023-07-31 | Title ("dual 2-input EXCLUSIVE-OR gate"); General description ("provides the dual 2-input EXCLUSIVE-OR function"); Ordering information (Table 1) | verified — gates_per_pkg=2, package VSSOP-8 |
| 74AUP2G34 | Nexperia 74AUP2G34 data sheet | 2023-07-27 | Title ("dual buffer"); General description ("is a dual buffer"); Ordering information (Table 1) | verified — gates_per_pkg=2, package SOT-363 (TSSOP6) |
| 74AUP3G04 | Nexperia 74AUP3G04 data sheet | 2023-07-31 | Title ("triple inverter"); Ordering information (Table 3) | verified — gates_per_pkg=3, package VSSOP-8 |
| 74AUP3G34 | Nexperia 74AUP3G34 data sheet | 2024-04-29 | Title ("triple buffer"); General description ("is a triple buffer"); Ordering information (Table 1) | verified — gates_per_pkg=3, package VSSOP-8 |

## Function citations (new combinational cells)

The `function` string of a G-cell is a *logic* fact, verified against the
data sheet's function table, independently of the (still placeholder)
electrical figures on the same row.  (The first column is `cell_function`,
not `cell`, so this table is not mistaken for the electrical table above.)

| cell_function | part_number | datasheet | revision | table/page | function status |
|---------------|-------------|-----------|----------|------------|-----------------|
| MUX2 | 74AUP1G157 | Nexperia 74AUP1G157 data sheet | 2023-07-12 | Function table (Table 4); Pin description (Table 3) | verified — Y = (I0·S̄) + (I1·S), inputs I0/I1/S (CSV: A=I0, B=I1, C=S, function `(A&!C)|(B&C)`) |

## Second-sourcing notes

`MUX2` (`74AUP1G157`) is **single-sourced**: the data sheet above confirms
Nexperia as the only manufacturer of a single-gate 2-input multiplexer found.
TI (`SN74AUP1G157`), Diodes (`74AUP1G157`) and Toshiba (`TC7SP157`) were
checked and either do not offer the part or could not be reached; no
cross-manufacturer single-gate 2:1 mux is recorded. The `mfrs` column therefore
names `Nexperia` alone, and the cell is excluded from the default Liberty file
(§10.1 [R4-9]) until a second source is confirmed. `lib gen
--allow-single-source` includes it; its function and generated model are
covered by the reachability test in `tests/toolchain/`.
