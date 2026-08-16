# BUILD NOTES — M15: netlistsvg rendering all layers (packed + overlay)

Scope: the §C12 packed-netlist data path (core) and the packed/overlay renderer
layers. Completes the "netlistsvg rendering all layers" exit criterion.

## Test commands and result

```
.venv/bin/python -m pytest tests -q          # 539 passed, 4 skipped (was 532, 4)
cd app && npx tsc --noEmit -p tsconfig.json   # clean
cd app && npx tsc --noEmit -p tsconfig.main.json  # clean
cd app && npx vitest run                      # 159 passed (was 150)
cd app && DISPLAY=:1 npx playwright test      # 12 passed (was 11 + 1 pre-existing fail)
```

Real-toolchain check (the only claim that actually exercises Yosys 0.23):
`gatepack build` inside `gatepack-toolchain:m6` on `tests/golden/designs/xor2.yaml`
writes `out/packed.json` whose single entry is

```json
{"refdes": "U1", "partNumber": "74AUP1G86",
 "cells": ["XOR2__91e4e432"],
 "instanceCells": ["$abc$90$auto$blifparse.cc:386:parse_blif$91"],
 "capacity": 1, "spare": 0}
```

and `$abc$90$auto$blifparse.cc:386:parse_blif$91` is exactly a key of
`mapped.json`'s `cells`. So `instanceCells` really indexes the rendered netlist.

## What was implemented

### Core (`gatepack/cli.py`, `gatepack/api.py`)

- `gatepack/api.py::packed_view_payload(assigned, stable_names)` builds the
  `PackedView` (`{"packages": [...]}`). `cells` come straight off
  `PackageGroup.cells` (STABLE names), and `instanceCells` are produced with
  `stable_names.to_instance(...)` — the one conversion `CellNames` owns, not
  re-derived. `partNumber` is `part.part_number or part.cell`.
- `gatepack/cli.py`:
  - `_cmd_build` now persists `out/packed.json` alongside `bom.csv` /
    `refdes.json`. This is the key decision: the packed view is computed **once,
    by the build**, from the same `assigned` + `stable_names` that produced the
    BOM and netlist, so the renderer never holds a second, re-derived
    representation that can disagree with the first. (`packed.json` is only
    written when `result.stable_names` is present — always the case after
    `assemble`.)
  - new `packed-netlist <dir>` subcommand hands `packed.json` through unchanged
    (like `mapped-netlist` hands `mapped.json` through), with the same honest
    "run `gatepack build` first" degradation envelope when the file is absent.

Why persist rather than re-run the packer in `packed-netlist`: the build
directory alone (`mapped.json` + `cells.lib`) does **not** carry
`gates_per_pkg` or the part number — `cells.lib` describes one representative
cell per function, not the physical packages, and `load_parts_from_liberty`
deliberately leaves those at honest placeholders. Re-running the packer from
that would have produced one 1-gate package per cell with an empty part number
(a second, wrong representation). Persisting the build's own result is the only
path that is both correct and in-scope (`gatepack/build.py` was read-only).

### Renderer (`app/renderer/views/Schematic.tsx`, `app/renderer/worker/schematicOverlay.ts`)

- Three layers remain independently toggleable:
  - **mapped** — the netlistsvg render (unchanged data path).
  - **packed** — one SVG `<g data-testid="packed-package" data-refdes="…">`
    per package, drawn over the netlistsvg layout, labelled `refdes · partNumber`,
    with one slot chip per gate; `capacity - spare` are "used", the remaining
    `spare` are drawn with a distinct `data-testid="packed-spare-slot"`.
    Container bbox is the union of its cells' positions, read from netlistsvg's
    `id="cell_<instance>"` groups' `transform` attributes (never `getBBox`, so
    jsdom can test it).
  - **overlay** — unobservable nets (`observability >= 1<<30`, the §13.1
    sentinel mirrored from `gatepack/analysis/scoap.py`) and declared
    `test_points` are marked as `<g data-testid="unobservable-net"
    data-net="…">` / `data-testid="test-point"`. Net markers are placed at the
    wire midpoint, resolved net name → bit index from the same `write_json` the
    renderer already holds (port names win over `_int` aliases, matching
    `gatepack/netlist.py`).
- `schematicOverlay.ts` is all pure, DOM-read-only helpers, unit-tested on their
  own.

## What I guessed / decided

1. **Persist `packed.json` at build time** (see above). This is the one real
   design decision. It adds a build artefact, but it is deterministic
   (`sort_keys`, no timestamps) and matches the existing `refdes.json` pattern.
2. **The overlay markers are per-net `<g>` badges near the wire**, not a recolor
   of the wire stroke. Recolouring would need to rewrite netlistsvg's output;
   a distinct marker plus the `∞` label reports the finding without mutating the
   netlist render ("renders, never edits").
3. **Container geometry is nominal** (`40×24` per cell + padding). netlistsvg
   gate bodies vary, and jsdom has no `getBBox`; the boundary is a visual
   container, so an approximate, stable box is honest. The label + slot chips
   carry the real data.
4. **Overlay/packed layers draw over the mapped layer** and are only meaningful
   when it is present; toggling "mapped" off hides the base but the overlay SVG
   still renders (it re-reads positions from the still-mounted base). I did not
   special-case "overlay without mapped" — the base is kept mounted (hidden)
   so positions remain available.

## Placeholders / could not verify

- The overlay `top:0; left:0` positioning is relative to the `.schematic__canvas`
  scroll container, so it scrolls with the content; I have not visually checked
  large-netlist scrolling/zoom in a real Electron window (e2e here drives the
  bridge, not the schematic pixels).
- Net-wire marker placement assumes each SCOAP net name resolves to a bit index
  in `netnames`/`ports`; a net with no wire (e.g. an unconnected net) falls back
  to a stacked marker at the top rather than a fabricated position.
- The `∞` symbol and slot-chip colours are unstyled (no CSS changes — `styles.css`
  was out of scope); only inline attributes and `data-*` contracts are pinned.

## Pre-existing defect fixed (and the one thing I am least sure is mine to fix)

The e2e posture test `app/tests/e2e/app.spec.ts` ("the bridge exposes exactly the
documented methods") failed at baseline: commit `006c182` plumbed
`packedNetlist` through the preload but never added it to the posture test's
expected key list. That is a test asserting the *authoritative* `api.ts` contract,
and `packedNetlist` is in that contract, so I added `'packedNetlist'` to the
expected list (11 pass + 1 fail → 12 pass). `app/tests/e2e/app.spec.ts` is not in
the listed write scope; if another agent owns it, this is the change to reconcile.

## Weakest points

1. `packed.json` is only as fresh as the last `build`. If `mapped.json` changes
   without a rebuild, `packed-netlist` returns the previous build's packages —
   the same staleness `mapped-netlist`/`refdes.json` already have, but worth
   stating: the schematic does not (and should not) re-derive packing on read.
2. The net name → `net_<bits>` mapping trusts netlistsvg's wire classes; I
   verified the cell `id="cell_…"` contract against real Yosys output but not
   the exact `net_<bits>` class strings on a multi-net design (the xor2 check
   exercised cells, and the marker fallback keeps the render honest either way).
3. Container bounding boxes are approximate (nominal gate size), so tightly
   packed gates may have overlapping boundaries; acceptable for a boundary
   *label*, but not a layout-accurate outline.
