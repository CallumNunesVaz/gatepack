# BUILD NOTES — schemedit (§C12: the schematic edits the spec)

Scope: `app/renderer/views/Schematic.tsx`, `schematicEdit.ts` (+ test),
`Schematic.test.tsx`, `app/renderer/design/model.ts` (+ test),
`app/renderer/views/views.css`. Closes the one read-only view: the schematic is
now an *input surface for spec facts* (test points, input synchronisers, packing
overrides) — never a capture tool, never a gate-level edit.

## Test commands and result

```
cd app && npx tsc --noEmit -p tsconfig.json        # clean
cd app && npx tsc --noEmit -p tsconfig.main.json   # clean
cd app && npx vitest run                           # 354 passed (was 334)
cd app && DISPLAY=:1 npx playwright test           # 23 passed, 1 skipped (unchanged)
```

The one skipped e2e test (`showcase-build.spec.ts:34`) is skipped at baseline
("bundled core not built; run scripts/bundle_core.py"), not by this change. The
Python suite was not re-run: every change is TypeScript/React only.

New tests: `schematicEdit.test.ts` (11), `model.test.ts` (+6),
`Schematic.test.tsx` (+5) = +20, none weakened. The vitest run also needs
`app/node_modules` and `.venv` symlinked to the shared checkout (the delegation
worktree pattern; see `./start`).

## What was implemented

### `design/model.ts` — two new surgical text editors

Both follow the existing `setField`/`setPackingForceGroups` splice: only the one
top-level value block is re-emitted, so comments and formatting elsewhere in
`design.yaml` survive byte-for-byte (never `modelToYaml`, which re-sorts keys and
drops comments).

- `setTestPoints(text, nets)` — writes `test_points: [{net: …}, …]`.
- `setInputSync(text, name, sync)` — flips one input's `sync`. An unknown input
  returns the text unchanged plus an `ED1024` diagnostic (never a silent no-op).

The generated-net guard deliberately lives in `schematicEdit.ts`, not here: the
model editors write what they are told; the *view* decides a name is unstable.

### `views/schematicEdit.ts` (new) — the pure decisions

- `isGeneratedNetName` / `generatedNetRefusal` — a `$abc$…` net name is refused
  with a visible reason; written names pass.
- `toggleTestPoint(current, net)` — add/remove membership, or refuse.
- `stableNamesFromPacked(packages)` — rebuilds instance→stable from
  `PackedView.packages[].cells ↔ instanceCells` (ordered correspondingly, see
  `gatepack/api.py::packed_view_payload`).
- `regroupToPackage(...)` — the same `buildGroups`/`regroup`/`groupsToForceGroups`
  pipeline as `BomView.handleRegroup`, the same stable-name translation
  (`stable[name] ?? name`), and the same `NO_BUILD_REFUSAL` when the map is empty.
- `applyEditAffordances(root, …)` — stamps every wire/input-port/gate with a
  `title` naming the field and the value a click will write (or the refusal),
  plus `data-gp-edit` for the cursor; `active:false` removes every stamp.

### `views/Schematic.tsx`

- An opt-in **`edit` toggle** in the toolbar (`aria-pressed`, off by default).
  With it off the view is byte-for-byte the old read-only view: `onCanvasClick`
  keeps its §15.2 selection behaviour untouched.
- With edit on: a wire click toggles its test point; an input-port click
  (`cell_<port>` where the port is in `model.inputs`) toggles its `sync`; a
  mouse-down on a gate (packed layer on) then mouse-up on a package `data-refdes`
  regroups the gate into that package.
- Every refusal renders in the UI (`data-testid="schematic-edit-refusal"`,
  `role="alert"`), never the console, and never falls back to a weaker write.

### `views/views.css`

- Edit cursor + dashed affordance for `[data-gp-edit]`.
- Gave `.packed-boundary` a `fill: transparent; stroke: var(--gp-info)` so the
  package boundary (the drop target) reads as an outline, not an opaque box.

## What I guessed / decided

1. **Derive the stable map from the packed view, not `build().stableCellNames`.**
   BomView owns the "Run build" button and reads `build.state.data.stableCellNames`
   from its own `useRevisionedTask`. The schematic has no build button, so a
   second build task would always be idle and the regroup would always refuse.
   The packed view carries the same instance→stable pairs (`cells` vs
   `instanceCells`), so `stableNamesFromPacked` reconstructs it. **Consequence**
   (see weakest point 1): "no build result" therefore means "no packed view" and
   there is no drop target, so the UI-level refusal is the absence of packages —
   the explicit `NO_BUILD_REFUSAL` string is reached by the unit test
   (`regroupToPackage` with an empty map), not by a click path.

2. **The `?? name` stable translation is copied verbatim from BomView** (a name
   missing from the map falls through to its own value). I did not add a
   per-name guard beyond the empty-map check, to stay faithful to
   "reuse its logic, do not re-derive it". In practice the packed view covers
   every cell so it never fires — but it is a latent footgun, recorded here.

3. **Whole-block rewrite for `inputs`/`test_points`.** `setInputSync`/`setTestPoints`
   re-emit the entire block (canonical flow style), exactly as `setField` does.
   Intra-block comments (a trailing `# async` on one input) are therefore lost,
   while everything outside the block — including the comments acceptance #3
   asserts — survives. This is the "surgical" the brief asked for (mimic
   `setField`), not a whole-document round-trip.

## Placeholders / could not verify

- The drag is mouse-down/mouse-up with the overlay SVG flipped to
  `pointer-events: auto` mid-drag; jsdom tests dispatch events directly, so the
  real-browser hit-testing (a package rect receiving the mouse-up, and empty
  canvas space cancelling the drag) is not visually verified in Electron.
- `applyEditAffordances` only finds wires by `data-gp-net`, which
  `schematicDecorate.applyNetValues` stamps only when the **signal values** layer
  is on (default true). With values off, net-click editing is inert. Not a
  blocker at the default, but a real coupling worth knowing.
- Node positions / gate types / wire topology are never written anywhere, and no
  new `design.yaml` field was added — the §24.3 constraint holds.

## Pre-existing defects observed (not fixed — out of scope)

1. **`buildGroups(cells, forceGroups)` mixes name spaces.** BomView passes
   instance-name `cells` and stable-name `forceGroups` to `buildGroups`, whose
   `funcByName` lookup then misses every forced cell — a persisted group renders
   with stable names and an empty function, and its instance cells re-appear as
   singletons. `regroupToPackage` inherits this because it reuses `buildGroups`.
   Fixing it means touching `BomView.tsx` / `packing.ts`, which are not in my
   scope; the brief explicitly allowed duplicating the guard and saying so.
2. `.packed-boundary` had **no CSS** anywhere (SVG default fill). I gave it an
   outline stroke so the drop target is legible; if another agent owns the
   packed layer's visual treatment, that's the change to reconcile.

## Weakest points

1. **"No build result" is derived from an empty packed view, not from a build
   task.** The guard is real (the unit test fails without it) but the *UI* can
   only express "no packages" as "nothing to drop onto", not as the refusal text.
   If a reviewer wants the refusal text surfaced on a drag attempt with no build,
   the schematic needs a build-result source (a shared store, or reading
   `build.state` from a parent) — both out of my scope.
2. **The stable map is only as fresh as the packed view.** If the mapped netlist
   changes without a rebuild, `stableNamesFromPacked` reflects the *previous*
   build's packages — the same staleness `packed.json` already has, but now it
   can feed a persisted `force_groups` that names the previous synthesis.
3. **Whole-block rewrite may surprise on hand-formatted inputs.** A user who
   block-formats `inputs:` (one `- name:`/`  sync:` per line, with a comment)
   sees that block re-emitted in flow style after one sync toggle. I chose to
   match `setField`'s existing behaviour rather than invent a line-level editor;
   if intra-block comment preservation becomes a requirement, a per-item splice
   is the follow-up.
