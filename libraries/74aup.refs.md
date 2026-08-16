# 74AUP cell library — datasheet citations

> **STATUS: PLACEHOLDER — NOT DESIGN DATA.**
>
> No electrical value in `74aup.csv` has been verified against a datasheet.
> Every `vcc_min`/`vcc_max`, `tpd_ns` and `iq_ua` figure, every manufacturer
> list, and every part number below is a plausible placeholder pending
> datasheet confirmation (§10.1, §19 R8: nothing is inferred or remembered).
> None of these values are to be used as design data until the `datasheet`,
> `revision` and `table/page` columns are filled in from a real, pinned
> document revision. See `docs/BUILD-NOTES.md`.

> **Multi-gate packages (added 2026-08-16) carry an extra unverified claim.**
> `74AUP2G00`, `74AUP2G02`, `74AUP2G04`, `74AUP2G08`, `74AUP2G32` and
> `74AUP3G04` assert a **gate count and a package** as well as electrical
> values. A dual 2-input gate needs eight pins and a dual inverter six, so the
> `VSSOP-8`/`SOT-363` split below is a plausible placeholder and nothing more.
> Pin count, package and gate count must all be confirmed against a datasheet
> before any of these appear on a real BOM — a wrong `gates_per_pkg` produces a
> netlist that cannot be built, which is a worse failure than a wrong tPD.
>
> `area` for these rows is **not** datasheet data at all: it is gatepack's own
> cost weight, chosen so a larger package costs more in total but less per
> gate. It is a design decision, documented here so it is not mistaken for a
> measurement.

`gatepack lib check` fails if a row in `74aup.csv` has no entry in this table.

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
| DFF | TBD | TBD | TBD | placeholder — unverified |
| DFF_R | TBD | TBD | TBD | placeholder — unverified |
| DFF_S | TBD | TBD | TBD | placeholder — unverified (no candidate part yet, §9.2) |
| DFF_SR | TBD | TBD | TBD | placeholder — unverified |
| CNT4 | TBD | TBD | TBD | placeholder — unverified (74LVC161 candidate, §9.4) |
| SUPERVISOR | TBD | TBD | TBD | placeholder — unverified (TPS3839 candidate, §9.5) |
