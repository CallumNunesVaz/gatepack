# Worked example — the pelican crossing, from specification to BOM

This is the §18.1 showcase run end to end: a specification file becomes a bill
of materials and a schematic netlist, with the equivalence proof that gatepack
exists to provide. Every command below was run and its output pasted verbatim;
nothing here is illustrative.

You will need either Yosys/Icarus/SymbiYosys on `PATH`, or the toolchain
container. On this machine the tools are not installed, so `./start` runs the
toolchain commands in the container and says so on stderr — exactly as you will
see below.

## 0. Where you are

```console
$ ./start doctor
  ✓ gatepack     gatepack 0.1.0
  ✗ yosys        not found
  ✗ sby          not found
  ✗ iverilog     not found
  ✓ container    gatepack-toolchain:m6 (used automatically when a tool is missing)
```

`./start doctor` is the honest status report: the Python core is present, the
native tools are not, and the container that will stand in for them is.

## 1. The showcase

```console
$ ./start cli examples list
pelican (showcase)
    Pelican crossing controller — the showcase project (§18.1)
```

Extract it into a directory you own:

```console
$ ./start cli examples extract pelican -o .gpout/pelican
wrote .gpout/pelican/design.yaml
wrote .gpout/pelican/parts.csv
```

The specification is the interesting half of the project. Its spine:

```yaml
name: pelican
timing_model: synchronous
clock: {signal: clk, freq_hz: 1, source: OSC}
reset: {signal: rst_n, active: low, async_assert: true, sync_deassert: true, source: SUPERVISOR}
encoding: one_hot

inputs:
  - {name: request, sync: true}   # a button, asynchronous -> synchronised
  - {name: hold, sync: true}      # maintenance override, also asynchronous

states: [GO, WARN, STOP, CROSS, CLEAR]
initial: STOP

transitions:
  - {from: GO,    to: WARN,  when: "request & !hold"}
  - {from: GO,    to: GO,    when: "!request | hold"}
  - {from: WARN,  to: STOP,  when: "1"}
  - {from: STOP,  to: CROSS, when: "!hold"}
  - {from: STOP,  to: STOP,  when: "hold"}
  - {from: CROSS, to: CLEAR, when: "1"}
  - {from: CLEAR, to: GO,    when: "1"}

output_logic:
  traffic_red: "state == STOP | state == CROSS | state == CLEAR"
  traffic_amber: "state == WARN"
  traffic_green: "state == GO"
  walk: "state == CROSS"

properties:
  - {name: never_walk_with_traffic, kind: mutex, expr: "!(walk & traffic_green) & !(walk & traffic_amber)"}
```

Two details matter for what follows. `request` and `hold` are `sync: true`,
which makes gatepack emit two-flop synchronisers for them (a button is
asynchronous and must not drive a state flop directly). And the `properties`
block is not a comment: it is discharged by the prover in step 5, and if it
could not be proved the build would be refused.

## 2. Is it worth building? `estimate`

```console
$ ./start cli estimate .gpout/pelican/design.yaml --library libraries/74aup.csv
yosys is not on PATH — running in gatepack-toolchain:m6 instead.
Paths are relative to the repository root inside the container.
design: pelican (synchronous, one_hot, vcc 3.3 V)
verdict: AMBER
  package count:                 20  (green)
  flop count:                    11  (amber)
  clock net fanout:              11  (amber)
  combinational depth:      unknown  (unknown)
message: marginal: flop count, clock net fanout are in the amber band. Consider input-space collapse (§6.1) and re-measure before committing.
```

The verdict is a *verdict*, not a promise: 20 packages is comfortably discrete
logic, while 11 flops and an 11-way clock fanout are flagged amber so you look
before you commit.

## 3. Build it

```console
$ ./start cli build .gpout/pelican/design.yaml --library libraries/74aup.csv --out .gpout/pelican-out
yosys is not on PATH — running in gatepack-toolchain:m6 instead.
Paths are relative to the repository root inside the container.
packed: 20 package(s), 3 spare gate(s), pack_cost 32
wrote .gpout/pelican-out/bom.csv
wrote .gpout/pelican-out/netlist.net
wrote .gpout/pelican-out/refdes.json
wrote .gpout/pelican-out/report.md
wrote .gpout/pelican-out/netlist.unpacked.net
```

`build` synthesises the specification to gates, maps them to real 74AUP parts,
packs them into packages (here into the multi-gate 74AUP2G00/2G08/2G32 parts,
freeing 3 spare gates), and emits the artefacts a board needs.

## 4. The bill of materials

```console
$ cat .gpout/pelican-out/bom.csv
part_number,manufacturers,equivalents,package,quantity,refdes,tier,unit_price
74AUP1G04,TI;Nexperia;Diodes,,SOT-353,1,U1,G,
74AUP1G11,TI;Nexperia,,SOT-353,1,U2,G,
74AUP1G175,TI;Nexperia,,SOT-353,11,U3;U4;U5;U6;U7;U8;U9;U10;U11;U12;U13,F,
74AUP1G27,TI;Nexperia,,SOT-353,1,U14,G,
74AUP2G00,TI;Nexperia,,VSSOP-8,1,U15,G,
74AUP2G08,TI;Nexperia,,VSSOP-8,2,U16;U17,G,
74AUP2G32,TI;Nexperia,,VSSOP-8,3,U18;U19;U20,G,
```

Twenty packages, each with a reference designator, grouped by function. The
eleven 74AUP1G175 parts (tier F) are the one-hot state flops plus the input
synchronisers; the multi-gate parts are where the packer earned its keep —
three 2G32 packages hold the five OR2 gates, leaving spare slots.

## 5. Prove it — `verify`

The claim gatepack makes about this netlist is a proof, not a simulation:

```console
$ ./start cli verify .gpout/pelican/design.yaml --library libraries/74aup.csv --build .gpout/pelican-vbuild
yosys is not on PATH — running in gatepack-toolchain:m6 instead.
Paths are relative to the repository root inside the container.
verification: passed
  equivalence:               passed
  exhaustive simulation:     passed
  mutation:                  passed
      all applicable mutations detected
  flop reset connectivity:   passed
  supervisor parameters:     passed
  property never_walk_with_traffic: passed
  property one_traffic_aspect: passed
  mutation nand_to_and:      detected
  mutation flop_d_invert:    detected
  mutation reset_polarity_flip: detected
```

- **equivalence** closes the mapped netlist against a golden model (real Yosys).
- **exhaustive simulation** checks every input combination, not a sample.
- **mutation** flips gates, input polarities and reset polarity and confirms
  each fault is detected — the control that proves the first two are not
  vacuous.
- **property `never_walk_with_traffic`** is the safety property from step 1,
  discharged by SymbiYosys rather than asserted.

## 6. The netlist

`netlist.net` is a KiCad netlist; every part and net carries the name you
specified where it survived synthesis:

```console
$ head -c 1200 .gpout/pelican-out/netlist.net
(export "version" "gatepack-0.1.0")
(design "source" "gatepack" (sheet "number" "1" "name" "" "tstamps" "/"))
(components (comp "ref" "U1" "value" "74AUP1G04" "footprint" "SOT-353" ...)) ...
(nets (net "code" 11 "name" "clk" (node "ref" "U10" "pin" "1") ...))
```

And `report.md` (written by the same build) carries the provenance coverage,
SCOAP testability and stuck-at fault analysis that the GUI renders as overlays
— see `docs/MILESTONE-AUDIT.md` §M11b and §M10 for what those figures mean.

## What this walkthrough does *not* claim

- The **electrical values** in `parts.csv` are placeholders pending datasheet
  citation (`gatepack lib check` enforces this). The BOM is a real shape; it is
  not yet a purchasable part list.
- The **netlist has not been imported into KiCad** by anyone (M10). Pin
  numbers are deterministic, but footprint pin numbers need footprint data that
  `parts.csv` does not carry.
- **"passed" in `verify` is a measured result** on this machine and this
  toolchain image; it is re-measured on every build, not remembered.
