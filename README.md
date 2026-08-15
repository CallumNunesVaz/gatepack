# gatepack

Compile a truth table or finite state machine into a **bill of materials and a
schematic netlist built entirely from discrete single-gate logic packages** —
74AUP-class parts, one gate per package — with formal verification on every
build.

You write a specification. gatepack produces the Verilog, maps it to real
purchasable parts, proves the netlist is equivalent to what you specified,
and hands you a BOM with reference designators and a KiCad netlist.

```yaml
name: pelican
states: [GO, WARN, STOP, CROSS, CLEAR]
initial: STOP
inputs:
  - {name: request, sync: true}
transitions:
  - {from: GO, to: WARN, when: "request & !hold"}
  # ...
properties:
  - {name: never_walk_with_traffic, kind: mutex,
     expr: "!(walk & traffic_green) & !(walk & traffic_amber)"}
```

```
$ gatepack build examples/pelican/design.yaml --library libraries/74aup.csv --out out/
packed: 23 package(s), 0 spare gate(s), pack_cost 23
```

```csv
part_number,manufacturers,package,quantity,refdes,tier
74AUP1G08,TI;Nexperia,SOT-353,3,U3;U4;U5,G
74AUP1G175,TI;Nexperia,SOT-353,11,U7;U8;U9;U10;U11;...,F
```

## Why

Small logic — an interlock, a sequencer, a crossing controller — is often built
from discrete gates because a microcontroller is unqualifiable, unavailable, or
simply the wrong answer for something that must be inspectable. Doing that by
hand means hand-drawing gates, hand-picking parts, and hand-checking that the
result matches what you meant.

gatepack's claim is narrow and specific: **the netlist it emits is formally
proven equivalent to the specification you wrote.** Not simulated against a few
vectors — proven, with exhaustive simulation and mutation testing on top to
establish the proof is not vacuous.

## What it is not

- Not a schematic editor. It renders; it never edits (that lock-in is the thing
  it exists to avoid).
- Not an analogue simulator. No SPICE, no timing closure, no signal integrity.
- Not a microcontroller replacement tool, and it will tell you when your design
  is too big for discrete gates and should target a CPLD instead.

## Status

**Pre-release. Not yet v0.1.0.** The core pipeline runs end to end against a
real toolchain, and the desktop application launches and renders, but several
milestones are still open — including one where the verification claim above
does not currently hold.

`docs/MILESTONE-AUDIT.md` is the honest status of every milestone, checked by
running things rather than by counting tests. Read it before relying on
anything here. The short version: equivalence checking is under repair, SCOAP
and stuck-at analysis do not exist yet, and provenance coverage is computed but
not reported.

This project records what it has *measured* rather than what it assumes.
`docs/M0-FINDINGS.md` and `docs/M6-FINDINGS.md` hold results from real Yosys and
real SymbiYosys runs, and **they override the design document wherever they
disagree with it.**

## Getting started

```bash
python -m venv .venv && .venv/bin/pip install -e .

.venv/bin/gatepack examples list
.venv/bin/gatepack examples extract pelican -o my-project
.venv/bin/gatepack estimate my-project/design.yaml --library libraries/74aup.csv
```

`estimate` runs the front end and synthesis and gives you a viability verdict
before you invest in a full build.

### The toolchain

Synthesis and verification need Yosys, ABC, Icarus Verilog and SymbiYosys.
A container is provided:

```bash
docker build -f Dockerfile.probe -t gatepack-toolchain:m6 .
docker run --rm -v "$PWD:/repo" -w /repo gatepack-toolchain:m6 \
  python3 -m gatepack verify tests/golden/designs/xor2.yaml \
    --library libraries/74aup.csv --build .gpout/xor2
```

Without those binaries gatepack **refuses to synthesise** rather than producing
an unverified result. That is deliberate: `gatepack build` will tell you
"synthesis unavailable ... (never faked here)" instead of inventing a netlist.

### The desktop application

```bash
cd app && npm install && npm run build && npm start
```

The application is strictly a **view over artefacts the CLI produces**. It never
reimplements core logic — everything it shows comes from invoking `gatepack`.

## Commands

| | |
|---|---|
| `gatepack estimate` | §6 viability verdict — front end + synthesis only |
| `gatepack compile` | specification → behavioural Verilog + properties |
| `gatepack verify` | equivalence, exhaustive simulation, mutation, properties |
| `gatepack build` | pack and emit BOM, KiCad netlist, report |
| `gatepack lib check/gen` | cell-library citation audit and Liberty generation |
| `gatepack project bundle/explode` | single-file `.gpk` project format |
| `gatepack examples list/extract` | bundled example projects |

## Parts data

Every electrical value in `libraries/74aup.csv` must carry a datasheet citation
with document revision and table or page — see `libraries/74aup.refs.md`.
Values without one are marked as placeholders. **No electrical value in this
project is ever invented**, and `gatepack lib check` enforces it.

## Licence

GPL-3.0-or-later. Yosys, ABC, SymbiYosys, Icarus Verilog and Espresso are
separate works with their own licences; see `scripts/dependencies.json` and the
licence audit in CI.

All bundled examples are synthetic and written for this project.
