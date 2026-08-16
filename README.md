# gatepack

Compile a truth table or finite state machine into a **bill of materials and a
schematic netlist built entirely from discrete logic packages** — 74AUP-class
parts, one to three gates each — with formal verification on every build.

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
packed: 20 package(s), 3 spare gate(s), pack_cost 32
```

```csv
part_number,manufacturers,package,quantity,refdes,tier
74AUP1G175,TI;Nexperia,SOT-353,11,U3;U4;U5;U6;U7;...,F
74AUP2G08,TI;Nexperia,VSSOP-8,2,U16;U17,G
74AUP2G32,TI;Nexperia,VSSOP-8,3,U18;U19;U20,G
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
real toolchain — every golden design verifies, the must-fail goldens fail, and
two clean builds are byte-identical including the netlist and BOM. The desktop
application launches and renders.

`docs/MILESTONE-AUDIT.md` is the honest status of every milestone, checked by
running things rather than by counting tests. Read it before relying on
anything here. Still open: provenance coverage is computed but not reported,
packaging and signed installers do not exist, and the GUI milestones have not
been audited the way the core was. "KiCad import clean" has never been tested
by importing anything into KiCad.

This project records what it has *measured* rather than what it assumes.
`docs/M0-FINDINGS.md` and `docs/M6-FINDINGS.md` hold results from real Yosys and
real SymbiYosys runs, and **they override the design document wherever they
disagree with it.**

## Getting started

```bash
./start doctor       # what is installed, what is missing, what that costs you
./start              # the desktop application
./start dev          # the same, with renderer live-reload
./start cli ARGS...  # the command-line core
```

`./start` creates the venv on a fresh clone, builds the app only when a source
file is newer than the build, and — when a command needs Yosys and Yosys is not
installed — runs it in the toolchain container instead, saying so on stderr.
It never substitutes a result for a missing tool.

The rest of this section is what `./start` does, spelled out, for when you want
to drive the pieces yourself.

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
| `gatepack simulate` | the exhaustive divergence table (spec vs mapped netlist) |
| `gatepack lib check/gen` | cell-library citation audit and Liberty generation |
| `gatepack project bundle/explode` | single-file `.gpk` project format |
| `gatepack examples list/extract` | bundled example projects |

## Parts data

Every electrical value in `libraries/74aup.csv` must carry a datasheet citation
with document revision and table or page — see `libraries/74aup.refs.md`.
Values without one are marked as placeholders. **No electrical value in this
project is ever invented**, and `gatepack lib check` enforces it.

The multi-gate rows carry an extra unverified claim: a package and a gate
count. A wrong `gates_per_pkg` yields a netlist that physically cannot be
built, which is a worse failure than a wrong tPD — so confirm those before any
of this reaches a real BOM.

## Licence

GPL-3.0-or-later. Yosys, ABC, SymbiYosys, Icarus Verilog and Espresso are
separate works with their own licences; see `scripts/dependencies.json` and the
licence audit in CI.

All bundled examples are synthetic and written for this project.
