# Handoff notes — schematic edits the spec (§C12)

## What changed

- `app/renderer/design/model.ts` — `setTestPoints(text, nets)` and
  `setInputSync(text, name, sync)`, both `setField`-style splices (only the one
  top-level block is re-emitted). `setInputSync` on an unknown input returns the
  text unchanged plus an `ED1024` diagnostic.
- `app/renderer/views/schematicEdit.ts` (new) — pure edit decisions:
  `isGeneratedNetName`/`generatedNetRefusal`, `toggleTestPoint`,
  `stableNamesFromPacked`, `regroupToPackage`, `applyEditAffordances`.
- `app/renderer/views/Schematic.tsx` — an opt-in **edit** toolbar toggle (off by
  default); with it on, wire-click toggles a test point, input-port-click toggles
  `sync`, and a gate mouse-down + package mouse-up regroups (packed layer on).
  Refusals render in an alert note. With the toggle off, behaviour is unchanged.
- `app/renderer/views/views.css` — edit cursor/affordance, and
  `.packed-boundary` given an outline stroke (it had no CSS before).

## Tests added / changed

- `schematicEdit.test.ts` (new, 11): generated-name refusal; add/remove toggle;
  `stableNamesFromPacked`; regroup refuses with no stable map, refuses a
  mixed-function move, and writes stable names (never `g0`/`g1`); affordance
  titles stamp and un-stamp.
- `model.test.ts` (+6): `setTestPoints` preserves comments + unrelated lines when
  appending and when replacing; `setInputSync` flips one input, refuses an
  unknown input.
- `Schematic.test.tsx` (+5): toggle a test point and assert the YAML gained the
  entry with comments intact; generated `$abc$…` net refused with `design.yaml`
  unchanged; edit-off click changes nothing; input-sync toggle; regroup writes
  stable names.

No existing assertion asserted these edits were absent, so none weakened.

## What I guessed / flagged

- **The stable map is derived from the packed view, not from `build()`.** The
  schematic has no build button, so `build.state.data.stableCellNames` (BomView's
  source) is unavailable. `PackedView.packages[].cells` (stable) and
  `.instanceCells` (instance) are ordered correspondingly
  (`gatepack/api.py::packed_view_payload`), so `stableNamesFromPacked` rebuilds
  it. Consequence: "no build result" in the UI is "no packages to drop onto",
  not the refusal text — the `NO_BUILD_REFUSAL` string is exercised by the unit
  test, not by a click path.
- **`buildGroups` mixes name spaces (pre-existing).** BomView feeds instance-name
  `cells` and stable-name `forceGroups` to `buildGroups`, so a persisted group
  re-renders with stable names + empty func and its instance cells as singletons.
  `regroupToPackage` reuses this faithfully. Fixing it means touching
  `BomView.tsx`/`packing.ts` (out of scope); the brief explicitly permitted
  duplicating the guard and saying so.
- **Whole-block rewrite for the edited block.** Intra-block comments on
  `inputs:`/`test_points:` are re-emitted in canonical flow style (lost), while
  everything outside the block survives — the exact behaviour of `setField`, which
  the brief named as the style to mimic. Acceptance #3's "comments intact" refers
  to comments outside the edited block.

## Not verified / unfinished

- Real-browser drag hit-testing (overlay SVG `pointer-events` flipped mid-drag)
  is only exercised by jsdom's direct `fireEvent` dispatch, not Electron pixels.
- Net-click editing relies on `data-gp-net`, stamped only when the signal-values
  layer is on (default). With it off, wire edits are inert.
- Python suite untouched (TS-only change); e2e `showcase-build.spec.ts` skipped at
  baseline (bundled core not built).

## Test results

- Before: 334 passed (vitest); 23 passed + 1 skipped (playwright).
- After: 354 passed (vitest, +20); 23 passed + 1 skipped (playwright, unchanged).
- `npx tsc --noEmit -p tsconfig.json` and `-p tsconfig.main.json` both clean.

## Three things I am least confident about

1. Deriving the stable map from the packed view (rather than a build task) is the
   right call, but "no build → refusal text" is only unit-tested, not reachable
   through the UI.
2. The `?? name` fallback in the stable translation (copied from BomView) would
   write an instance name if a cell were missing from the packed map; the guard
   is only the empty-map check.
3. Re-emiting the whole `inputs:`/`test_points:` block drops intra-block comments;
   I accepted this to match `setField`, but a per-item splice would preserve
   them if that becomes a requirement.
