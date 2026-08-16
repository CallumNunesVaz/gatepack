# BUILD NOTES — M16 (linked selection + core divergence column)

Scope: the C11 divergence column moving into the core (`gatepack simulate`), and
the §15.2 selection bus in the renderer that makes the divergence data
selectable. Everything was driven through the injectable fake bridge — the
main-process `window.gatepack.simulate` handler and `SimulationTableSchema` do
not exist in this worktree and were not touched (another agent owns
`app/main`/`app/preload`).

## Test commands and result

```
$ .venv/bin/python -m pytest tests -q           # 403 passed, 2 skipped  ->  412 passed, 2 skipped
$ cd app && npx tsc --noEmit -p tsconfig.json  # clean
$ cd app && npx vitest run                     # 98 passed  ->  115 passed
```

No `npm install`, no `package.json` edits, no `app/main`/`app/preload`/`api.ts`
touches. The off-limits files (`gatepack/api.py`, `gatepack/project/`,
`gatepack/analysis/`, `gatepack/verify/properties.py`,
`gatepack/frontend/verilog.py`) were read but not edited.

## What was built

### Core — `gatepack/simulate.py` + `simulate` subcommand

- `build_simulation_table(compiled, mapped, parts, config)` emits the exact
  `SimulationTable` shape from `app/shared/api.ts`: `inputNames`, `outputNames`,
  `rows` (each `inputs`, optional `state`, `expected`, optional `actual`,
  `diverges`), `dontCareCount`, `unreachableCount`, `exhaustive`.
- **`expected` reuses C4's spec evaluator** — literally
  `gatepack.verify.simulation._expected_outputs`, the same function the verified
  exhaustive check uses. This is the point: the divergence column cannot
  disagree with the verified simulator, because it *is* the verified
  simulator's expected-value computation.
- **`actual` evaluates the mapped netlist's combinational cone** in Python,
  grounded in the *same* function table the C2 behavioural models (`cells_sim.v`)
  use: `parts.csv` `function` strings via `gatepack.liberty.boolean`, plus the
  `$_*` primitive table from `gatepack.provenance.match` for any residual
  un-mapped cell. It is not a second *spec* evaluator.
- Sequential (F/M/S) cell outputs are unknown (`'x'`); state is not clocked, so
  a state-held output never yields a false divergence. Divergence is asserted
  only where both sides are known.
- No netlist -> `actual` is omitted from every row and `diverges` is false
  (never fabricated). Row cap `DEFAULT_MAX_ROWS = 4096`; above it `exhaustive`
  is `false` and rows are truncated to the cap, never silently.
- `gatepack simulate <design> [--library csv] [--build dir] [--mapped json] [--json]`
  follows the envelope pattern (`api.envelope_ok`/`api.dump`). `--library` is
  optional: without it, G-cell outputs evaluate unknown.

### Renderer — §15.2 selection bus (`app/renderer/selection/`)

- `types.ts` — the `Selection` union (§15.2) and `HighlightSet`.
- `map.ts` — the pure, testable mapping: `parsePointer`, `indexProvenance`,
  `linkConfidence` (`exact` > `inferred` > `none`), `coneCells` (transitive
  fan-in), `divergingOutputs`, and `resolveSelection` mapping a selection in any
  view to the artefacts in every other view **and back** (transition<->cell,
  minterm<->cell, state<->cell).
- `bus.tsx` — `SelectionProvider`/`useSelection`/`useHighlights`.
- `useLinkContext.ts` — loads `provenance()` + `mappedNetlist()` + `simulate()`
  and memoises a `LinkContext`.
- `SelectionBadge.tsx` — three distinct, greppable states: `exact`, `inferred`,
  and `no exact link` (a transition with no surviving link says so instead of
  silently highlighting nothing).
- Wired: `TruthTable.tsx` now renders the **core** `simulate()` divergence
  column (dropping the client-side `simulateCombinational` comparison); row
  click emits a `minterm` selection and reflects selections from other views.
  `FsmGraph.tsx` emits `state`/`transition` selections, highlights the matching
  nodes/edges, and shows the confidence badge in the inspector. `Schematic.tsx`
  shows a text readout of the highlighted nets/cells. `fake.ts` gained
  `simulate`.

## Guesses / decisions I had to make

1. **`dontCareCount` and `unreachableCount` are always 0.** The current design
   model is FSM-only: `output_logic` fully specifies every output (no `-`
   syntax) and the front-end rejects unreachable states at compile time. A
   `truth_table.csv` document *exists* in the project format (§10.4) but is not
   consumed by C1 yet, so there is no don't-care source for the core to read.
   The fields are emitted honestly as zero rather than invented.
2. **Sequential `actual` is the combinational cone only.** I did not write a
   cycle-accurate Python simulator (that would be "a second simulator that can
   disagree with the verified one" — the verified one is Icarus). A Moore/Mealy
   FSM therefore shows `'x'` for state-held outputs and no divergence; the
   divergence column is meaningful for the combinational case, which is the case
   the truth table reduces to. Documented, not hidden.
3. **`expected` uses *current-state* semantics**, matching the renderer's old
   "live" column, not the next-state semantics the Icarus testbench checks.
   `_expected_outputs` is state-parameterised, so both are one line apart, but
   they are not the same thing — worth flagging.
4. **`transition` identity is `(from, to)` per §15.2**, not an index. Duplicate
   (from, to) pairs union their provenance; in practice the goldens have unique
   pairs.
5. **`package` and `property` selections resolve to nothing.** The contract has
   no cell->refdes map (only `bom` lines keyed by part number) and the
   counterexample pointers live inside `verify()` results, so a package or
   property selection has no honest cross-highlight. Returned empty rather than
   guessed (§15.2 "never imply a false one-to-one").
6. **The truth-table don't-care toggle was removed.** It was a client-side
   overlay that the core cannot express, and the divergence column now comes from
   the core, so the two no longer compose. The cover preview still uses
   `estimate()`.

## What is stubbed / placeholders

- **Schematic cross-highlight is a text readout**, not a recoloured netlistsvg
  SVG nor a clickable gate. netlistsvg interaction was out of scope; the
  structural mapping (which cells/nets to highlight) is done and tested.
- **Package/property selection** maps to nothing (see guess 5).
- **`mapped/sim.ts` `simulateCombinational` is now unused by the views** (only
  its own test still exercises it). `parseWriteJson` is retained and used for
  cone computation. I left the superseded function in place rather than delete a
  passing, tested utility mid-merge.

## What I could not verify

- No Yosys/Icarus/iverilog here, so `actual` was never produced from a *real*
  `mapped.json`. The netlist evaluator is pinned by synthetic fixtures and by
  the shared `parts.csv`/`$_*` function table, but has not run against the
  pinned toolchain's output.
- No Electron window, so the FSM-graph badge and the schematic highlight readout
  have only ever rendered under jsdom/fake, never the real bridge.

## Three things I am least confident about

1. That "reuse C4's simulator" is satisfied by reusing only the *expected-value*
   computation and not the Icarus run: the task forbade a second simulator, so I
   deliberately made `actual` combinational-only. If the reviewer wanted a
   clocked `actual` for sequential designs, that is a real gap, not a stylistic
   one.
2. Whether `dontCareCount`/`unreachableCount` should have been wired to the
   (unconsumed) `truth_table.csv` document — I read it as out of scope because C1
   ignores it, but emitting two always-zero fields feels like shipping a column
   that measures nothing, which is exactly the failure mode this project warns
   about.
3. The `transition` identity as `(from,to)` (vs. an index) — it matches the
   design doc but loses the unambiguous pointer mapping when two transitions
   share endpoints, and I had to union their provenance.
