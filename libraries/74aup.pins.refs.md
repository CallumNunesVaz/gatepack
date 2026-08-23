# 74AUP cell library — pin-map citations

> **STATUS: every pin number in `74aup.pins.csv` is a PLACEHOLDER — NOT DESIGN DATA.**
>
> No pin number in this file has been verified against a datasheet.  The pin
> *positions* below are positional (gate-1 signal pins, gate-2 signal pins, …,
> VCC, GND), not the manufacturer's pinout, and the ``NC`` rows are placeholder
> no-connect markers whose count is derived from arithmetic (package pins minus
> known signal/power pins), not from a datasheet.  None of these numbers are to
> be used to fabricate a board until the `datasheet`, `revision` and `table/page`
> columns are filled in from a real, pinned document revision.
>
> What the pin map *does* provide is structure, not truth: it is cross-checked
> against data the library already holds — pin count vs `package`, exactly one
> `VCC` and one `GND`, coverage of exactly `gates_per_pkg` gates, exactly
> `inputs` input pins and one output per gate, contiguous pin numbers, and no two
> rows for the same part disagreeing.  A placeholder pin map that satisfies all
> six cannot silently misdescribe how many gates or pins a part has, which is
> the class of error that reaches a board; an inconsistent one is rejected by
> `gatepack lib check` before it ships.

`gatepack lib check` treats a pin map with no entry in the table below as a
placeholder (fail-closed), never as verified.  A part that has no pin-map file
at all is not an error — the pin map is optional, and the KiCad emitter falls
back to positional numbering with a loud notice.

| part_suffix | datasheet | revision | table/page | pin status |
|-------------|-----------|----------|------------|------------|
| 1G04 | TBD | TBD | TBD | placeholder — unverified |
| 1G34 | TBD | TBD | TBD | placeholder — unverified |
| 1G00 | TBD | TBD | TBD | placeholder — unverified |
| 1G02 | TBD | TBD | TBD | placeholder — unverified |
| 1G08 | TBD | TBD | TBD | placeholder — unverified |
| 1G11 | TBD | TBD | TBD | placeholder — unverified |
| 1G32 | TBD | TBD | TBD | placeholder — unverified |
| 1G86 | TBD | TBD | TBD | placeholder — unverified |
| 1G157 | TBD | TBD | TBD | placeholder — unverified |
| 1G79 | TBD | TBD | TBD | placeholder — unverified |
| 1G175 | TBD | TBD | TBD | placeholder — unverified |
| 2G04 | TBD | TBD | TBD | placeholder — unverified |
| 2G34 | TBD | TBD | TBD | placeholder — unverified |
| 2G00 | TBD | TBD | TBD | placeholder — unverified |
| 2G02 | TBD | TBD | TBD | placeholder — unverified |
| 2G08 | TBD | TBD | TBD | placeholder — unverified |
| 2G32 | TBD | TBD | TBD | placeholder — unverified |
| 2G86 | TBD | TBD | TBD | placeholder — unverified |
| 3G04 | TBD | TBD | TBD | placeholder — unverified |
| 3G34 | TBD | TBD | TBD | placeholder — unverified |

## Parts deliberately without a pin map

A pin map is only written where `gatepack/pins.py` already owns the per-cell pin
table, so the map can be cross-checked against `inputs`, `gates_per_pkg` and the
cell's input/output pin names.  The following library rows have no pin map, and
their omission is deliberate:

* `DFF_SR` (`74AUP1G74`) — the refs record (`74aup.refs.md`) names it
  "complementary Q/Q̄"; the pin model (`gatepack/pins.py` `F_PIN_DIRECTIONS`)
  carries only `Q`, not `Q̄`, so a pin map that used the model would leave the
  8th lead unaccounted.  Writing it as `NC` would be a fabrication (the lead is
  an output, not a no-connect).  It stays unmapped until the pin model grows a
  `Q̄` output.
* `DFF_S`, `NAND3`, `NOR3` — no candidate part (empty `part_suffix`); there is
  no ordered part to map.
* `CNT4` (`74LVC161`, M-cell) and `SUPERVISOR` (`TPS3839`, S-cell) — their pin
  tables are seams (`gatepack/macros`, `gatepack/infra`); not this file's scope.
