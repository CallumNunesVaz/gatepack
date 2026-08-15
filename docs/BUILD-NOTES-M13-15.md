# BUILD NOTES — M13–M15 (renderer views)

Covers the three renderer views this work package owns — C10 spec editor, C11
truth-table grid, C12 schematic — plus the app shell and the two behaviours the
brief said matter more than the rest: the four-state check badge, and
stale-result invalidation on document edit.

## Test commands and result

```
$ npx tsc --noEmit -p tsconfig.json      # clean (no output)
$ npx vitest run
# Test Files  9 passed (9)
#       Tests 54 passed (54)

$ npx vite build                          # built in ~13 s (renderer only)
```

All tests drive the injectable fake bridge (`app/renderer/bridge/fake.ts`); no
test touches a real process, `window.gatepack`, or `app/main`/`app/preload`.

## What was built

### Bridge seam (against the contract, not the other agent's code)

- `api.ts` — `getApi()` reads `window.gatepack` when present and otherwise
  returns an injected fake; `setApi()` is how every test installs the fake.
  `nextToken()` mints cancellation tokens.
- `bridge/fake.ts` — a full `GatepackApi` in memory: configurable results per
  command (`setOk`/`setError`/`setOkFactory`), a call log, a `cancelled` log,
  per-command async hooks so a test can hold a call open and resolve it late,
  and event emitters.
- `bridge/context.tsx` — `ApiProvider`/`useApi`.

### C10 spec editor (M13)

Three synchronised representations of the same text, all editing *through* the
text:

- `views/spec/MonacoEditor.tsx` — Monaco, text authoritative.
- `views/spec/StructuredForm.tsx` — name/timing/encoding/initial, inputs,
  outputs, states (read-only), properties, constraints. Every field edit
  rewrites the YAML via `design/model.ts`.
- `views/spec/FsmGraph.tsx` — React Flow; states = nodes, transitions = labelled
  edges. Reconnect target / edit guard / add state / add transition / rename
  state are all document mutations producing new YAML. Node positions go to a
  layout store, never into the YAML.

Supporting machinery (all pure, all tested):

- `design/yaml.ts` — a hand-rolled YAML-subset parser mirroring
  `gatepack/frontend/yaml_subset.py` exactly (same subset, same duplicate-key /
  tab / block-scalar rejections, same `ON`-stays-a-string rule), with **character
  ranges** for every top-level key so an edit can splice one block without
  touching the rest; plus a serialiser mirroring `gatepack/project/serialize.py`.
- `design/expr.ts` — the boolean expression language (`! & | ^`, `0`/`1`,
  `state == NAME`), precedence `! > & > ^ > |`, tri-valued (`'0'|'1'|'x'`)
  evaluation, `freeVars`/`statesReferenced`/`expand` with cycle detection. This
  is a deliberate mirror of `gatepack/frontend/expr.py`, because the live
  truth-table column is the *sanctioned* client-side exception and must agree
  with the core exactly.
- `design/model.ts` — the typed `DesignModel`, `parseDesignText` (structural +
  expression-reference validation mirroring `schema.py`/`model.py`, with
  renderer-local diagnostic codes `ED1xxx`), and edit operations
  (`applyTopLevelEdit`, `setField`, `renameState`).
- `design/layout.ts` — the node-position sidecar store.

### C11 truth table (M14)

- `truth/minterms.ts` — input-minterm enumeration, live output evaluation
  (named-expression expansion + state context), reachability for the coverage
  indicator.
- `mapped/cells.ts` — the G-cell function table mirrored from `libraries/74aup.csv`.
- `mapped/sim.ts` — a `write_json` parser (mirroring `netlist.py`/`capture.py`)
  plus a combinational-cone evaluator that returns output values per minterm.
- `views/TruthTable.tsx` — the grid: live column (spec), simulated column
  (mapped netlist), per-row divergence highlighting, coverage indicator
  (specified / don't-care / unreachable), editable `-` don't-care cells, and a
  debounced (300 ms) `estimate()` cover preview showing `cellCounts` +
  `packageCount`.

### C12 schematic (M15)

- `worker/renderSchematic.ts` — `netlistsvg.render(skin, write_json)`, the exact
  seam, imported by the worker **and** exercised directly by the test.
- `worker/schematic.worker.ts` + `worker/schematicClient.ts` — the web worker
  that runs netlistsvg + elkjs off the UI thread, with an in-process fallback
  for environments without a Worker.
- `views/Schematic.tsx` — renders the SVG; three independently toggleable layers.

### C15 verification + C13/C14 shells

- `components/StatusBadge.tsx` — four unmistakable states; `bounded` displays its
  bound `(k = N)` and is never green. Used in the verification panel.
- `views/VerificationPanel.tsx` — `verify()` results, four-state badges,
  counterexample traces; runs on explicit request.
- `views/BomView.tsx`, `views/AnalysisView.tsx` — read-only shells over
  `build()`/`analyse()`.

### Staleness (the other behaviour that matters)

- `hooks/useRevisionedTask.ts` — a core call tied to the document revision:
  cancels in-flight work on revision change and flags any already-arrived result
  stale; discards results that resolve after supersession. Tested three ways.
- `state/project.tsx` — the authoritative `specText` + monotonically increasing
  `revision`; every editor view mutates through `setSpecText`.

## Guesses / decisions I had to make

1. **The simulated column is evaluated client-side, not "from the core".**
   `app/shared/api.ts` exposes `verify()` (checks + counterexamples) and
   `mappedNetlist()` (the `write_json`), but **no per-vector exhaustive-sim
   result**. The divergence column is "the single most valuable thing in this
   view" and it cannot be rendered from the contract as written, so I evaluate
   the mapped netlist's combinational cone client-side (arithmetic over the
   `write_json`, using the G-cell function table from `74aup.csv`). This is the
   same *kind* of arithmetic as the sanctioned boolean evaluation, but it is a
   workaround for a contract gap, not the "from the core" the brief described.
   If the contract later gains an exhaustive-vectors payload, `mapped/sim.ts` is
   the single drop-in point to swap it in.
2. **Sequential (F/M) cells evaluate to `'x'`.** The client sim does not clock
   flops; the combinational cone is evaluated and state-held outputs are unknown.
   Divergence is therefore only asserted where both sides are known — which is
   exactly the combinational case where "minterm disagrees" means something.
   This is a real limitation for FSMs, and the brief's truth table is at its
   most meaningful for truth-table/decoder-style designs anyway.
3. **Layout sidecar is `localStorage`, not `design.layout.json`.** The contract
   has no read/write for arbitrary project files, so the gitignored sidecar file
   the design specifies cannot be reached from the renderer. Positions are
   persisted in `localStorage` keyed by project path via an injectable
   `LayoutStore`. The invariant that matters — positions never appear in
   `design.yaml` — is pinned by a test.
4. **Don't-care cells are a local overlay, not written back.** Marking a minterm
   `-` affects the coverage counts and divergence, but it cannot feed the
   `estimate()` cover preview, because the contract has no way to hand the core
   an edited truth table (only `writeSpec` for `design.yaml`). The cover preview
   therefore reflects `design.yaml` edits (it updates live on any spec change),
   not the grid's `-` toggles. Honest gap, documented here.
5. **Diagnostics are split by namespace.** Client-side structural/expression
   diagnostics use renderer-local codes `ED1xxx`; the *semantic* checks
   (reachability, guard overlap/exhaustiveness, SAT) are deliberately **not**
   reimplemented in the renderer — those arrive from `compile()`/`estimate()`.
   A single reachability BFS is mirrored for the coverage indicator only
   (normally zero, since the core rejects unreachable states).
6. **Cover preview uses `estimate()`** (which returns `cellCounts` +
   `packageCount`), not a distinct Espresso dump, because that is what the
   contract exposes.
7. **Monaco offline config.** `monaco-setup.ts` points the loader at the local
   `monaco-editor` and sets a trivial editor worker via `MonacoEnvironment`.
   The YAML tokenisation is a monarch grammar on the main thread (no language
   worker). This has been type-checked and bundled but not exercised in a real
   Electron window (no Electron here).

## What is stubbed / placeholders

- **C13/C14 are shells**, not full views (deliberately — "three views right over
  six sketched"): BOM table + single-source marker, metrics/SCOAP/fault lists.
  No drag-to-regroup packing, no CPLD-escape-hatch interaction.
- **Packed-schematic layer** is an honest "not exposed by the contract" notice —
  `mappedNetlist()` returns the logical netlist only; package-boundary
  containers need a packed `write_json` that the bridge does not provide.
- **Test-point/unobservable overlay** lists declared `test_points` and
  SCOAP-observability-zero nets from `analyse()` as text; it does not (yet)
  recolour nets inside the SVG.
- **Per-vector signal-value overlay** (§24.2, colouring every net by its 0/1 for
  a selected minterm) is not implemented — it needs the per-vector sim data that
  is the same contract gap as guess #1.
- **`window.gatepack` integration is unexercised** — `app/main`/`app/preload`
  are another agent's work in flight, so the renderer has only ever run against
  the fake.

## What I think is weakest

1. **The M14 simulated/divergence column is client-side arithmetic, not core
   data.** It is correct for combinational cones and tested, but it is not what
   the brief asked for ("from the core"), because the contract cannot express
   it. This is the single most important caveat in this whole work package.
2. **The FSM-graph edit surface is narrower than ideal.** Reconnect/guard/rename
   work and are tested at the model level, but the graph component itself is not
   covered by a component test (React Flow + jsdom), and add/remove *transition*
   via direct edge interaction is not wired (buttons + inspector are). The
   invariant that matters — a graph edit changes YAML, positions stay out — is
   pinned, but the React Flow glue is the least-tested code here.
3. **Monaco/worker runtime paths are unexercised.** Both type-check and bundle,
   and the schematic seam is tested directly, but no real Electron window or
   worker thread has run them.

## Three things I am least confident about

1. Whether `netlistsvg`'s internal elkjs (0.3.0, its own nested dependency) will
   behave in a **real** web-worker under the pinned elkjs 0.9.3 at the top level.
   It works in-process (the test proves it) and the worker bundles and builds,
   but the two elkjs versions coexisting is a risk I could not run.
2. Whether the surgical YAML edits preserve enough of a user's formatting to be
   acceptable — editing a list re-serialises that *block* canonically (sorted
   flow keys, re-quoted expressions), which matches the core's own canonical
   emitter but will still reflow a hand-formatted block the first time it is
   edited. Comment preservation inside edited blocks is not handled.
3. That my "simulated from the client" decision is what the reviewer actually
   wants, versus being told to leave the divergence column empty until the
   contract grows an exhaustive-vectors method. I chose "show it honestly now"
   over "hide it", and flagged it everywhere.
