# GUI audit — M13–M16 exit criteria vs. reality

**Date:** 2026-08-16. Checked against the §20 exit criteria, by driving the real
Electron application against the real Python core (not the fake bridge), and by
running the core's `--json` commands against real Yosys 0.23 output in
`gatepack-toolchain:m6`.

The reason for auditing this way is the same one that produced
`docs/MILESTONE-AUDIT.md`: the GUI milestones were merged on their test counts,
and the tests all drive an injectable fake bridge (`app/renderer/bridge/fake.ts`).
Nothing in the green suite exercises the real `window.gatepack` → main process →
core path, so a passing test count says nothing about whether the application
works against the thing it actually talks to.

| ID | Exit criterion (§20) | Status |
|---|---|---|
| M13 | C10 spec editor — three-way sync; positions in sidecar only | **met** (positions stay out of YAML; sidecar is `localStorage`, not `design.layout.json` — see note) |
| M14 | C11 truth table — live spec + simulated outputs; divergence highlighting | **NOT MET** |
| M15 | C12 schematic — netlistsvg rendering all layers | **NOT MET** |
| M16 | Linked selection (§15) — all cross-highlights in the §15.2 table work | **NOT MET** |

The single finding that explains most of the damage: **the renderer is wired to
three core subcommands that do not exist.** `main/session.cts` invokes
`gatepack mapped-netlist`, `gatepack provenance` and `gatepack analyse`. The CLI
registers none of them. So `mappedNetlist()`, `provenance()` and `analyse()` all
return an error envelope in the real application, which silently disables the
schematic's netlist, the entire linked-selection spine, and the analysis
dashboard.

---

## M13 — met (with one deviation from the letter of §10.3)

Driven in the real app: first launch opens the pelican showcase (5 states), the
FSM graph renders five nodes, and a graph edit ("+ state") rewrites `design.yaml`.

```
app/tests/e2e/gui-audit.spec.ts › M13: a graph edit mutates the YAML, and positions never enter design.yaml  — passed
```

The three-way sync holds: the graph is not a second model — `FsmGraph.addState`
calls `applyTopLevelEdit(specText, 'states', …)` and pushes the new text through
`setSpecText`, which is the single authoritative path (Monaco, the structured
form and the graph all edit *through* the text). Positions are written by
`onNodeDragStop` to a `LayoutStore` and never touch the document; the e2e test
asserts the spec text contains no `position`/`layout`/`x:`/`y:` marker before or
after an edit.

**The deviation:** the sidecar is `localStorage` keyed by project path
(`gatepack.layout:<path>`), **not** the gitignored `design.layout.json` that
§10.3 names. This is documented in `docs/BUILD-NOTES-M13-15.md` (guess #3): the
IPC contract has no read/write for arbitrary project files, so the renderer
cannot reach the gitignored file. The invariant that matters — node positions
never enter `design.yaml`, so diffs stay about logic — holds. The letter of
"positions in the gitignored sidecar" does not. I score this **met** on the
functional invariant and flag the file-location deviation as an open item for
the core owner (it needs a contract addition to `writeSpec`/a project-file API).

---

## M14 — not met: the divergence column is inert

The renderer half is genuinely fixed. `TruthTable.tsx` reads the divergence
table from `ctx.simulation`, which `useLinkContext.ts` populates from
`api.simulate()` — the core. The old client-side `simulateCombinational` in
`mapped/sim.ts` is dead code: `grep` shows it referenced only by its own test.
So the renderer no longer compares the specification against itself.

The core half measures nothing. `gatepack simulate` returns `actual: "x"` for
**every output of every design**, combinational included, so `diverges` is
always `false`. The truth-table column can never diverge — not because the
netlist agrees, but because the netlist is never evaluated.

Reproduced against a real Yosys 0.23 mapped netlist in the toolchain container
(a single-cell `XOR2` netlist computing `y = a ^ b`, four rows):

```
$ python3 -m gatepack.cli simulate design.yaml --library parts.csv --mapped out/mapped.json --json
row 0 {"actual": {"y": "x"}, "diverges": false, "expected": {"y": "0"}, "inputs": {"a": "0", "b": "0"}}
row 1 {"actual": {"y": "x"}, "diverges": false, "expected": {"y": "1"}, ...}
row 2 {"actual": {"y": "x"}, "diverges": false, "expected": {"y": "1"}, ...}
row 3 {"actual": {"y": "x"}, "diverges": false, "expected": {"y": "0"}, ...}
```

**Root cause.** The post-ABC `write_json` carries **no `port_directions`** on
cells (verified: `mapped.json` has 0 occurrences; `premap.json`, written before
`abc`, has them). `netlist.parse_mapped_json` therefore builds cells with empty
`directions`, so `simulate.evaluate_mapped_netlist` sees empty `input_pins` /
`output_pins` and skips every cell, leaving every output `None` → `"x"`.
`simulate.load_mapped` never calls `netlist.resolve_parts`, which is the call
that recovers directions from the parts table (the build path does call it,
which is why packing/BOM work while the divergence column does not). The fix is
to resolve parts before evaluating:

```
$ python3 -c "…"
before resolve: cell directions = {}
after resolve:  cell directions = {'A': 'input', 'B': 'input', 'Y': 'output'}
evaluate (a=1,b=0): {'y': True}
```

The only test that exercises this path,
`tests/unit/test_simulate.py::test_cli_simulate_divergent_with_mapped`,
**fabricates a `mapped.json` that includes `port_directions`** — a shape the
real toolchain never emits. That is exactly the failure mode this project has
now shipped six times: a test that pins a synthetic input and passes forever
while the real input makes the check measure nothing. The docstring even says
"so a deliberately-wrong netlist makes `diverges` true (the check can fail)" —
true only against the synthetic netlist.

This is a **core defect** (`gatepack/` is off-limits here). The regression test
in `app/tests/e2e/gui-audit.spec.ts` ("M14: simulate() returns real (non-x)
`actual` for a combinational netlist") seeds a `mapped.json` shaped exactly like
real Yosys output (no `port_directions`) and fails against the current core.

---

## M15 — not met: two of three layers are not rendered

`Schematic.tsx` declares three toggleable layers. What each actually does against
the real core:

- **mapped netlist (logical):** calls `api.mappedNetlist()` → the main process
  runs `gatepack mapped-netlist`, which does not exist. The envelope is
  `ok: false` (GP9002, "core emitted no parseable JSON envelope"). Until this
  audit, that failure was **silently swallowed** — the pane showed
  "laying out the netlist…" forever. (Fixed here: `Schematic.tsx` now reports
  the failure instead of spinning.)
- **packed netlist (package boundaries):** hardcoded text, not a rendering:

  ```
  The packed netlist (package-boundary containers) is not exposed by the IPC
  contract (`mappedNetlist()` returns the logical netlist only). See BUILD-NOTES.
  ```

- **test points / unobservable nets:** a text list of declared `test_points` and
  SCOAP-observability-zero nets from `analyse()` — which also does not exist, so
  it always reads "(none reported)" (previously silent; now reported as an
  `analyse()` failure).

Only the first layer is a netlistsvg render at all, and it cannot obtain its
input. "netlistsvg rendering all layers" is therefore **not met**: the packed
and overlay layers are text notices, not renders, and the one netlistsvg layer
has no data path. The honest "not exposed by the contract" notice is correct
behaviour in isolation, but it is an admission that the exit criterion was not
met, not an implementation of it.

---

## M16 — not met: the selection spine cannot reach the core

Linked selection consumes `provenance()` (the §15.1 spine) and `mappedNetlist()`
(the cone). Both are dead in the real app: `gatepack provenance` and
`gatepack mapped-netlist` do not exist.

```
$ .venv/bin/python -m gatepack.cli provenance out
gatepack: error: argument command: invalid choice: 'provenance'
  (choose from 'lib', 'compile', 'estimate', 'verify', 'simulate', 'build', 'examples', 'project')   # exit 2
$ .venv/bin/python -m gatepack.cli mapped-netlist out
gatepack: error: argument command: invalid choice: 'mapped-netlist'  ...                                 # exit 2
$ .venv/bin/python -m gatepack.cli analyse out
gatepack: error: argument command: invalid choice: 'analyse'  ...                                        # exit 2
```

`useLinkContext.ts` then holds `EMPTY_PROVENANCE` and `netlist = null`, so
`resolveSelection` returns `confidence: 'none'` and empty highlight sets for
every selection — every cross-highlight in the §15.2 table is inert, regardless
of the renderer logic.

Walking the §15.2 table against what *would* happen once the core is fixed
(measured in the toolchain container from the pelican build):

| Select this (§15.2) | Reality |
|---|---|
| truth-table row | cone from `mappedNetlist()` — no netlist, so no cells |
| gate in schematic | no schematic, no BOM/package link |
| state in FSM graph | bare `states` token fix is present (`map.ts`); pelican's `states` entry is exact (9 nets, 2 cells) — **would work** if provenance arrived |
| transition edge | 5 of 7 transitions have entries; `transitions[1]` (GO→GO) and `transitions[4]` (STOP→STOP) have **none** |
| package card | maps to nothing (`map.ts` returns `EMPTY_HIGHLIGHTS` — no cell→refdes map in the contract) |
| input | `inputs[i]` entries present — would work |
| failing property | counterexample pointers live inside `verify()`; package/property selections map to nothing |
| dangerous-fail fault | maps to nothing |

The §15.2 state-selection fix (bare `states` token) is present and correct — the
provenance measurement confirms `states` is the best-covered construct kind
(exact, 9 nets / 2 cells) — but it is unreachable because `provenance()` cannot
return. The "no exact link" state for a transition with no surviving link
(`SelectionBadge`) is implemented and tested, but the transitions it would
badge (`[1]` and `[4]`) are unreachable for the same reason. **M16 is not met.**

---

## What was done here (in-scope)

- `docs/GUI-AUDIT.md` — this document.
- `app/tests/e2e/gui-audit.spec.ts` — a regression spec that drives the real
  main process + real core and pins three things: M13's graph-edit→YAML +
  positions-out-of-YAML (passes), M14's non-`x` `actual` (fails against the
  buggy core), and M15/M16's "core recognises `mapped-netlist`/`provenance`/
  `analyse`" (fails against the buggy core).
- `app/renderer/views/Schematic.tsx` — stop silently swallowing
  `mappedNetlist()`/`analyse()` failures; report them. (The previous behaviour
  was an endless spinner and a misleading "(none reported)".)
- `app/renderer/views/Schematic.test.tsx` — pins the two failure-reporting
  behaviours.

## Open items for the core owner (not fixable in the renderer scope)

1. **`simulate` must resolve pin directions** (call `resolve_parts` before
   `evaluate_mapped_netlist`, or carry directions in `parse_mapped_json` from
   the parts table). Without it the M14 divergence column measures nothing.
2. **Add `mapped-netlist`, `provenance`, `analyse` subcommands** to the CLI,
   matching the `main/session.cts` argv. `provenance` has a ready payload
   builder (`gatepack.provenance.coverage.provenance_map_payload`) that is
   currently only called by the report generator; the docstring there already
   says "the entry point a `gatepack provenance` command … calls".
3. **A `cell → refdes` / package map** in the IPC contract, so the §15.2
   package/property/fault rows can highlight anything (currently `map.ts`
   returns `EMPTY_HIGHLIGHTS` for them).
4. **A packed `write_json`** for the schematic's package-boundary layer, and
   per-vector signal values for the §24.2 overlay (both noted in
   `docs/BUILD-NOTES-M13-15.md`).
5. **`design.layout.json`** needs a project-file read/write in the contract if
   the sidecar is to live where §10.3 says it should.
