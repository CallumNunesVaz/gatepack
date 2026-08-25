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

**v0.1.0, unsigned.** Every milestone closes. Installers build **unsigned** and
say so: signing credentials cost money, have no bearing on whether the tool is
correct, and buying them is not a release blocker for a FOSS project, so
"signed installers" was removed from the v0.1.0 exit criteria rather than left
permanently unmet ([M18-4]). Nothing is fabricated — no self-signed certificate
presented as real, no placeholder identity — and a maintainer who supplies
credentials later gets signed, *verified* installers with no code change.
Expect a Gatekeeper or SmartScreen warning on first launch.

The Linux build ships its own toolchain: yosys, iverilog, vvp, z3, abc and a
frozen sby, with provenance recorded per binary. On macOS and Windows those are
still host tools, reported by name and purpose by `gatepack doctor` rather than
stubbed.

The core pipeline runs end to end against a real toolchain — every golden
design verifies, the must-fail goldens fail, and two clean builds are
byte-identical including the mapped netlist and BOM. Provenance coverage is
measured and reported on every golden (M11b). The GUI milestones (M12–M17) have
been audited by driving the real application — `docs/GUI-AUDIT.md` — and all
close.

**All thirteen bundled examples complete the whole journey through the GUI**,
and so does a design created from nothing: File > New, compile, estimate,
verify, build, and every post-build view. That is measured, not assumed —
`app/tests/e2e/examples-end-to-end.spec.ts` drives the real Electron main
process against a real core with the real toolchain, once per example. Three
things it found are fixed: the Analysis tab was a dead end for asynchronous
designs, the Provenance tab told users to run a build they had just run, and
**any project in a path containing a space failed synthesis** — the generated
Yosys script embedded paths unquoted, so `/home/me/My Board` became
`Can't open input file '/home/me/My'` and reported a *failed verification* for
a reason with nothing to do with the design. The Python core ships inside the app as a self-contained PyInstaller
binary (`scripts/bundle_core.py`), and the licence audit now enumerates what
that binary actually contains rather than the declared dependency list. A
walkthrough from specification to BOM is in `docs/worked-example.md`.

`docs/MILESTONE-AUDIT.md` is the honest status of every milestone, checked by
running things rather than by counting tests. Read it before relying on
anything here.

**The KiCad netlist is emitted but its import has never been verified.** No
check in this project can close that — it needs a human with KiCad opening the
file and confirming power symbols and no-connect flags survive — so the
criterion is descoped from v0.1.0 rather than left open indefinitely. The
emitter's tests establish that it emits what it intends to emit, and nothing
about whether KiCad accepts it. Treat the netlist as unverified output until
you have imported one yourself.

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

**File > New Project…** (`Mod+N`) scaffolds a `design.yaml` and a `parts.csv`
into a directory you choose and opens them. The template is a *working* two-state
design, not a stub: press verify immediately after creating it and you get a
verdict, which is also the fastest way to confirm your toolchain is wired up.
The template lives in the core (`gatepack project new`), not in the application,
so the CLI and the GUI produce the same project and cannot drift. An existing
`design.yaml` is never overwritten.

In the schematic, the wheel zooms about the pointer, dragging pans the sheet,
and clicking is forgiving: a wire is selectable within ±5 px of the line and a
gate symbol anywhere inside it. Both were measured first — the wire was ±0.5 px
and the middle of a gate symbol hit nothing at all, because SVG hit-tests only
what it paints and the skin fills nothing. `docs/MILESTONE-AUDIT.md` [GUI-2] has
the numbers.

Drag and click share the left button, so they are separated by distance rather
than by a modifier: a press becomes a pan only once the pointer has moved 4 px,
and the click that ends a pan is dropped instead of changing the selection.
Middle-drag always pans, and the grab cursor appears only when the sheet is
actually larger than the pane — offering to move something that cannot move is
the same class of lie as a button that does nothing.

**File > Reveal Outputs** opens `.gatepack/out` in the file manager, and
**Export Outputs…** copies the BOM, the KiCad netlist and the report to a folder
you choose. Both refuse rather than doing something useless: reveal will not open
an empty directory when nothing has been built, and export will not overwrite a
file you already had — it names the conflicts and writes nothing.

So the answer to "can I do all of this in the GUI?" is now: yes, from creating a
design to handing the outputs on. What the GUI still cannot do is tell you
whether KiCad will accept the netlist — see the Status note above; that needs a
human with KiCad open.

## Windows

The core is pure Python and runs on Windows; the desktop installer and the
native toolchain are the parts that differ. See **`docs/WINDOWS.md`** for
install/run instructions, what needs OSS CAD Suite or WSL2, and — plainly —
what has never been run on a Windows machine. In short:

```powershell
start.ps1 doctor       # what is installed, what is missing, where to get it
start.ps1 cli ARGS...  # the command-line core
start.ps1              # the desktop app (after `cd app` + `npm ci`)
```

## macOS

The core is pure Python and runs on macOS; the desktop installer and the native
toolchain are the parts that differ. See **`docs/MACOS.md`** for
install/run instructions — yosys, iverilog and z3 come from Homebrew, SymbiYosys
comes from OSS CAD Suite — and for what has never been run on a Mac. `gatepack
doctor` reports each tool's purpose plus its macOS install route, and
`scripts/bundle_toolchain.py` refuses on macOS rather than shipping inert Linux
binaries.

## Commands

| | |
|---|---|
| `gatepack estimate` | §6 viability verdict — front end + synthesis only |
| `gatepack compile` | specification → behavioural Verilog + properties |
| `gatepack verify` | equivalence, exhaustive simulation, mutation, properties |
| `gatepack build` | pack and emit BOM, KiCad netlist, report |
| `gatepack simulate` | the exhaustive divergence table (spec vs mapped netlist) |
| `gatepack lib check/gen` | cell-library citation audit and Liberty generation |
| `gatepack project new` | scaffold a working `design.yaml` + `parts.csv` |
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
