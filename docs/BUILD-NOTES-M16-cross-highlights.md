# BUILD NOTES — M16 cross-highlights (package + property selections)

Scope: the two §15.2 rows that still mapped to nothing after the data path was
fixed — **package card ↔ gates** and **failing property / counterexample step →
spec constructs + gates**. Everything else in the §15.2 table already worked and
is treated as a regression surface. All tests drive the injectable fake bridge;
nothing here spawns a real process.

## Test commands and result

```
$ .venv/bin/python -m pytest tests -q            # 532 passed, 4 skipped (unchanged — no core edits)
$ cd app && npx tsc --noEmit -p tsconfig.json   # clean
$ cd app && npx tsc --noEmit -p tsconfig.main.json  # clean
$ cd app && npx vitest run                      # 150 -> 161 passed
$ DISPLAY=:1 npx playwright test --config playwright.config.cjs   # 12 passed (after build:main + vite build)
```

No `npm install`, no `gatepack/`, `api.ts`, `app/main`, `app/preload`,
`Schematic.tsx` or `worker/` edits. `gatepack-design.md` and the audit docs are
untouched.

## What was built

### `app/renderer/selection/`

- `types.ts` — `Selection` gained `{ kind: 'cexStep'; property: string; cycle: number }`;
  `HighlightSet` gained `packages: string[]` (refdes list); `LinkContext` gained
  `packed: PackedView | null` and `verify: VerifyResult | null`.
- `map.ts` — `indexPacked` indexes `packedNetlist()` as refdes↔instance-cell in
  **both** directions. `propertyHighlights` resolves a property/step selection
  through `Check.counterexample.pointers` → provenance nets/cells and
  pointer-paths → FSM states/transitions. `resolveSelection` now handles
  `package`, `property` and `cexStep`; the `cell` direction also returns its
  containing package(s).
- `linkData.ts` (new) — a tiny module store so the VerificationPanel can
  *publish* its `verify()` result to the selection spine without a provider
  wrapper (App.tsx is out of scope). `useLinkContext` reads it back; it never
  auto-runs the expensive sby `verify()`.
- `useLinkContext.ts` — also fetches `packedNetlist()` and guards every fetch
  against a null `data` (the fake returns `ok(null)` for unseeded commands,
  which previously could set `provenance` to null and crash `resolveSelection`).

### `app/renderer/views/`

- `BomView.tsx` — the BOM table's refdes are now clickable package cards: each
  emits `{ kind: 'package', refdes }` and reflects `highlights.packages`. This is
  the §15.2 "package card ↔ contained gates" spine; the schematic shows the
  contained cells via the existing `highlights.cells` readout.
- `VerificationPanel.tsx` — a failing property row emits a `property` selection;
  each counterexample cycle row emits a `cexStep` selection (with
  `stopPropagation` so a step click is not also a property click). The panel
  publishes its `verify()` result into `linkData` on success.

### Tests

- `map.test.ts` — 7 new cases: package→instance-cells (and **stable names never
  leak**), cell→package (reverse), unknown-refdes honest-empty, failing
  property→states/nets/cells/pointers, cexStep→same, passed property→empty +
  `none`, unverified property→empty. The 14 prior cases still pass unchanged.
- `BomView.test.tsx` — wraps the view in `SelectionProvider` (it now uses the
  selection bus) and adds a "clicking a refdes highlights it" test with a seeded
  `PackedView`.
- `VerificationPanel.test.tsx` (new) — property-click, step-click, and idle-state
  tests, all through the fake bridge.
- `app/tests/e2e/app.spec.ts` — added `packedNetlist` to the §5.2 posture test's
  expected bridge-method list. The packed3 seam (`006c182`) exposed
  `packedNetlist` on the bridge but this test was not updated, so it was failing
  red at HEAD before any of my renderer work; the fix aligns it with the
  authoritative `api.ts`.

## Guesses / decisions

1. **Package identity is `refdes`, not part number.** §15.2's `package` selection
   is `{ refdes }`, and `PackedView.packages` has one refdes per package. The
   BOM table's part rows carry `refdes` lists, so each refdes becomes its own
   clickable card (a multi-refdes part yields multiple cards, matching the
   packed layer).
2. **Package selection uses `instanceCells`, never `cells`.** `PackedView.cells`
   are stable cone-hash names; the schematic/provenance are keyed by instance
   names. The name-space test pins this.
3. **`cexStep` resolves to the counterexample's pointers, not per-cycle
   constructs.** The core's `_trace_pointers` names `properties` + `states`
   (whole-list tokens) and explicitly does not recover a per-step state, so I
   did not reimplement that recovery in the renderer. A step selection resolves
   to the same construct set as its property; the `cycle` only pins which trace
   row is highlighted in the panel.
4. **Property reverse direction is not implemented.** §15.2 has no
   "state/cell → property" row, and the counterexample pointers (whole-list
   `states`/`properties`) cannot name a single property to highlight in the
   reverse direction. The panel reflects property/step selections directly via
   `useSelection()`.
5. **Confidence for a package is `none`.** The badge renders only for
   state/transition; package containment is not a provenance link, so I did not
   overload `LinkConfidence`.

## Placeholders / could not verify

- **`packed-netlist` does not exist in the CLI.** `api.packedNetlist()` maps to
  `gatepack packed-netlist`, which is not a registered subcommand, so in the
  *real* app `ctx.packed` stays null and package selections resolve to an
  honest empty set (the refdes still highlights itself). The renderer is correct
  against the `PackedView` contract; the core half is owned by `gatepack/`
  (off-limits here). Tests use the fake bridge's `PackedView`.
- **No Yosys here.** Nothing was verified against real toolchain output; all
  fixtures are synthetic, shaped like the real payloads (no `port_directions`,
  stable-vs-instance name split).
- **The §15.2 "dangerous-fail fault" row is still gapped.** `AnalysisSummary`
  carries only fault-class *counts*, not individual faults with pin/stuck, and
  there is no `fault` selection kind in the renderer. Implementing it would need
  a contract addition (api.ts is off-limits) — recorded, not guessed.

## Three things I am least confident about

1. **The module store (`linkData.ts`) is a stopgap.** The clean fix is a
   `VerifyProvider` in App.tsx, but App.tsx is outside the write scope. A
   module-scoped store persists across the app's life (and within a test file),
   so a verify result survives pane switches while the panel itself remounts to
   "not run". I judged that consistent-enough, but it is the weakest seam here.
2. **Property reverse direction absence.** I could not derive a precise
   state→property reverse from whole-list pointers, so I left it out. If the
   reviewer expects "selecting a state highlights the failing property", that is
   a real gap, not a stylistic one.
3. **`cexStep` cycle is cosmetic.** I did not validate the cycle against the
   trace length or recover per-cycle state; it only pins the row highlight. If
   the requirement was "step N highlights the state active at cycle N", I
   deliberately did not build it because the core says it cannot recover that.
