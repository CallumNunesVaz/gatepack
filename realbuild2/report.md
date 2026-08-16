# pelican — build report

timing model: synchronous

## Packing (§9.7)

| result | packages | spare gates | package cost | pack_cost |
|---|---|---|---|---|
| packed | 23 | 0 | 23 | 23 |
| unpacked | 23 | 0 | 23 | 23 |


_pack_cost = sum(package_cost) + spare_count * spare_leakage_weight. Package count and spare count are reported separately on purpose; spare gates are a cost, not free (§9.7)._

## Bill of materials

| part | manufacturers | package | qty | refdes | tier |
|---|---|---|---|---|---|
| 74AUP1G00 | TI;Nexperia;Diodes | SOT-353 | 1 | U1 | G |
| 74AUP1G04 | TI;Nexperia;Diodes | SOT-353 | 1 | U2 | G |
| 74AUP1G08 | TI;Nexperia | SOT-353 | 3 | U3;U4;U5 | G |
| 74AUP1G11 | TI;Nexperia | SOT-353 | 1 | U6 | G |
| 74AUP1G175 | TI;Nexperia | SOT-353 | 11 | U7;U8;U9;U10;U11;U12;U13;U14;U15;U16;U17 | F |
| 74AUP1G27 | TI;Nexperia | SOT-353 | 1 | U18 | G |
| 74AUP1G32 | TI;Nexperia | SOT-353 | 5 | U19;U20;U21;U22;U23 | G |

## Package grouping (per-package rationale)

| refdes | rationale |
|---|---|
| U1 | function group: NAND2 (1G00) holds 1 gate(s) |
| U2 | function group: INV (1G04) holds 1 gate(s) |
| U3 | function group: AND2 (1G08) holds 1 gate(s) |
| U4 | function group: AND2 (1G08) holds 1 gate(s) |
| U5 | function group: AND2 (1G08) holds 1 gate(s) |
| U6 | function group: AND3 (1G11) holds 1 gate(s) |
| U7 | function group: DFF_R (1G175) holds 1 gate(s) |
| U8 | function group: DFF_R (1G175) holds 1 gate(s) |
| U9 | function group: DFF_R (1G175) holds 1 gate(s) |
| U10 | function group: DFF_R (1G175) holds 1 gate(s) |
| U11 | function group: DFF_R (1G175) holds 1 gate(s) |
| U12 | function group: DFF_R (1G175) holds 1 gate(s) |
| U13 | function group: DFF_R (1G175) holds 1 gate(s) |
| U14 | function group: DFF_R (1G175) holds 1 gate(s) |
| U15 | function group: DFF_R (1G175) holds 1 gate(s) |
| U16 | function group: DFF_R (1G175) holds 1 gate(s) |
| U17 | function group: DFF_R (1G175) holds 1 gate(s) |
| U18 | function group: NOR3 (1G27) holds 1 gate(s) |
| U19 | function group: OR2 (1G32) holds 1 gate(s) |
| U20 | function group: OR2 (1G32) holds 1 gate(s) |
| U21 | function group: OR2 (1G32) holds 1 gate(s) |
| U22 | function group: OR2 (1G32) holds 1 gate(s) |
| U23 | function group: OR2 (1G32) holds 1 gate(s) |

## Power (§13.3)

Static current, broken out by tier (assumption: IQ values are as cited in parts.csv; no temperature derating is applied because the data model has no derating curve):

| tier | static current (µA) |
|---|---|
| G | 10.8 |
| F | 9.9 |
| M | 0 |
| S | 0 |
| **total** | **20.7** |

Spare-gate leakage penalty (estimate: each spare slot's idle IQ, §9.7): 0 µA

Dynamic current (estimate): 1.518e-05 µA
- nominal only: assumes 2 pF/gate output, 0.1 activity; excludes inter-package routing capacitance, which will dominate — not a budget

## Timing (§13.3)

- worst-case combinational depth: 4 levels
- cumulative tPD: 19.9 ns
- worst path: $abc$148$auto$blifparse.cc:386:parse_blif$149 -> $abc$148$auto$blifparse.cc:386:parse_blif$150 -> $abc$148$auto$blifparse.cc:386:parse_blif$153 -> $abc$148$auto$blifparse.cc:386:parse_blif$154
- note: excludes PCB parasitics; not static timing analysis (no clock-to-Q, no setup, no routing skew)

## Reference designator delta ([R4-19])

- unchanged: 0
- added: 23
- removed: 0
- renumbered: 0

## Testability (SCOAP, §13.1)

- absolute SCOAP costs are not directly comparable; the delta table reports the nets with the highest observability + max(CC0,CC1), where an observability >= 1073741824 means the net is unobservable at every primary output.

| net | CC0 | CC1 | observability |
|---|---|---|---|
| rst_n_s1 | 2 | 3 | ∞ |
| hold | 1 | 1 | 22 |
| request | 1 | 1 | 22 |
| $abc$148$new_n22_ | 2 | 3 | 20 |
| $abc$148$new_n21_ | 2 | 6 | 19 |
| hold_s1 | 2 | 4 | 19 |
| request_s1 | 2 | 4 | 19 |
| $abc$148$new_n14_ | 4 | 2 | 17 |
| $abc$148$new_n23_ | 4 | 2 | 17 |
| hold_s2 | 2 | 7 | 16 |

Unobservable nets (no path to any primary output; rendered as an overlay by C12): rst_n_s1

## Fault analysis (§13.2)

- single stuck-at; single stuck-at analysis over the combinational cut (flop Q as pseudo-inputs, D as pseudo-outputs); detected is an upper bound because all 2**k flop states are enumerated, not just reachable ones.
- uncollapsed faults (nets + cell pins): 216
- collapsed faults (equivalence + dominance): 59
- detected: 53, undetected: 0, redundant: 0, untestable: 6
- vector set: exhaustive (8192 vectors)

## CPLD fallback (§24.1)

- blockers: none — generated.v is CPLD-portable (no memories, latches, async logic, or surviving internal cells)
- alternative flow: flash CPLD (e.g. MAX V) driven by the portable inferred Verilog in generated.v; the generated design uses no memories, latches, asynchronous logic or surviving internal cells

## Notes

- Packing is advisory (§12 C5): sharing a package forces physical adjacency; overrides persist in design.yaml.
- Pack cost uses spare_leakage_weight = 2 in the same units as package area (§9.7).
- Dynamic current excludes inter-package routing capacitance and is not a budget.
- tPD excludes PCB parasitics and is not STA.
- Static current is the sum of the placeholder IQ values in parts.csv; no temperature derating is applied (the data model has no derating curve).
- Pin numbers in the netlist are assigned deterministically; real footprint pin numbers need footprint data (parts.csv has none).
