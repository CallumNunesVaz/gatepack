# BUILD NOTES — M17 (C13 packing view + C14 analysis dashboard)

Scope: turn the two thin shells (`BomView.tsx`, `AnalysisView.tsx`) into the
C13 packing/BOM view and the C14 dashboard. Everything is driven through the
injectable fake bridge; nothing touches a real process, `window.gatepack`, or
`app/main`/`app/preload`. Off-limits files were read but not edited; `api.ts`
remains the authoritative contract and was matched field for field.

## Test commands and result

```
$ .venv/bin/python -m pytest tests -q         # 467 passed, 2 skipped  (unchanged)
$ cd app && npx tsc --noEmit -p tsconfig.json  # clean
$ cd app && npx tsc --noEmit -p tsconfig.main.json  # clean
$ cd app && npx vitest run                     # 125 passed -> 146 passed
$ cd app && npx vite build                     # builds clean (12.8 s)
```

New tests: 21. `components/packing.test.ts` (9), `design/packing.test.ts` (4),
`views/BomView.test.tsx` (4), `views/AnalysisView.test.tsx` (4).

## What was built

### C13 — packing and BOM (`BomView.tsx` + `components/`)

- `components/packing.ts` — the pure packing-group model: `buildGroups`
  (persisted `force_groups` kept verbatim, unmapped cells become singletons),
  `regroup` (move a cell between groups, refusing a mixed-function move with a
  message), `groupsToForceGroups` (only groups of ≥2 cells, deterministic),
  `rationaleFor`. The function identity of a cell is its mapped `type`, which is
  the renderer's mirror of the packer's `_pack_key`.
- `components/PackingCards.tsx` — package groupings as cards, HTML5
  drag-to-regroup, the refusal message, and the inert note. Pure rendering +
  drag transport; every decision lives in `packing.ts` / the parent.
- `views/BomView.tsx` — groups derive from `mappedNetlist()` cells +
  `model.packing.forceGroups`; a valid regroup runs `setPackingForceGroups`
  (new `design/model.ts` edit op) and `setSpecText`, so the override persists
  to `design.yaml` through `writeSpec`. The mapped netlist is re-fetched after a
  build lands (it only exists once a build has produced `mapped.json`). The BOM
  table keeps the `singleSourced` hard marker (`SINGLE-SOURCE` chip + red row,
  `data-single-sourced`).
- `design/model.ts` — `Packing` on `DesignModel`, parse/emit of
  `packing.force_groups`, and `setPackingForceGroups`.

### C14 — analysis dashboard (`AnalysisView.tsx`)

- Metrics rendered red on `Metric.violated` **only** — the renderer never
  recomputes the comparison. A `VIOLATED` flag and `data-violated` are added;
  no second opinion.
- The §6 verdict comes from `estimate()` (it lives in `EstimateResult`, not
  `AnalysisSummary`), with reasons and the red-alternative.
- SCOAP table, the four stuck-at classes (`detected`/`undetected`/`redundant`/
  `untestable`) each with its own label + note + colour, never collapsed into a
  percentage, and the CPLD blockers list.

## Honesty requirements, met

- **Grouping is inert for the shipped library.** Every `74aup.csv` part is one
  gate per package, so `packed == unpacked` and no spare can exist. The view
  says so plainly (`packing-inert`) instead of rendering a cost delta that is
  always zero. The stats strip shows the core's `packageCount`/`spareCount`/
  `packCost` unchanged by regrouping.
- **Mixed-function refusal is surfaced**, never silently dropped: a rejected
  regroup renders `not the same function` in an alert and writes nothing.

## Guesses / contract gaps (the important section)

1. **`force_groups` name space is the biggest risk.** The core's packer resolves
   force-group members against `stable_cell_names` (function + cone-hash,
   `gatepack/netlist.py`), but the renderer's only cell identity is the
   `write_json` instance name from `mappedNetlist()`. No bridge method exposes
   stable names or the instance→stable mapping. The renderer therefore writes
   instance names. `tests/unit/test_packer.py::test_force_groups` uses instance
   names, but only in the identity case (no `stable_names` passed), and there is
   no core test exercising `force_groups` through `build`/`assemble` where
   `stable_cell_names` is applied — so the name the core actually expects for a
   real build is unverified on both sides. This seam most likely needs a
   follow-up (`cellNames()` bridge method, or the core accepting instance names).
2. **Per-group rationale is derived locally.** The core emits a `rationale`
   string per package (`PackageGroup.rationale`, printed in `report.md`), but it
   is not on the `BuildResult` IPC payload. The cards show a locally-derived
   line matching the core's *shape* (`forced group: …`, `unpacked: one … per
   package`), not the core's exact string.
3. **The §C14 metric list is the core's list, not the doc's.** §C14 names
   "spare count, clock fanout, static current by tier, worst-case tPD"; the
   core's `AnalysisSummary.metrics` emits only package count, flop count, static
   current (total), combinational depth, pack cost. I render exactly what the
   core emits — no fabricated metrics — and no violated comparison is
   recomputed.
4. **The §6 verdict is fetched from `estimate()`, not `analyse()`.** The task
   lists the verdict alongside `scoap`/`faults`/`metrics`/`cpldBlockers`, but
   the verdict lives in `EstimateResult`; `AnalysisSummary` has no verdict
   field. `AnalysisView` runs both commands on one "Run analysis" click.
5. **`Metric.value` can be `null` at runtime** even though `api.ts` types it
   `number` (`analysis_summary` emits `None` for static current / timing when
   synthesis has not run). The view renders `—` defensively.
6. **The "inert" note is stated, not computed.** The renderer cannot see
   `gates_per_pkg` (the library CSV is not on the contract), so "one gate per
   package" is a stated fact about the shipped 74AUP library, not a derived
   property. A user-supplied multi-gate library would make the note wrong; the
   contract has no field to detect that.
7. **Drag is HTML5 DnD**, tested with a mocked `dataTransfer`. Fine under jsdom;
   unexercised in a real Electron window.

## What I could not verify

- No Yosys/mapped.json here, so the cell list and grouping cards have only ever
  rendered against a hand-written `write_json` fixture — never a real
  `mapped.json` with the actual instance names the packer's `force_groups`
  would need.
- No Electron window, so the drag interaction has only run under jsdom.
- The container image (`gatepack-toolchain:m6`) was not used: this work package
  is renderer-only and produces no tool-run claim; the Python core (467 tests)
  is untouched and still green.

## Three things I am least confident about

1. The `force_groups` name space (instance vs stable cell names). If the core
   expects stable names and the renderer writes instance names, the override
   persists but the core will refuse it as an "unknown cell" on the next build.
   This is the one gap that could make the drag-regroup a paper feature.
2. Whether a reviewer wanted the grouping cards driven by `build()`'s packages
   (cell→refdes) rather than `mappedNetlist()` cells. The contract exposes no
   cell→package/refdes mapping, so cells are the only honest unit; but the cards
   and the BOM table do not share a key, which is a visible seam.
3. Hard-coding the inert note instead of computing it from the library. Honest
   for the shipped library, wrong for a hypothetical multi-gate one, and the
   contract gives no way to tell them apart.
