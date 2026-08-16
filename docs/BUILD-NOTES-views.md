# BUILD-NOTES-views — six views restyle (functional → professional)

Scope: `app/renderer/views/**` only. Nothing outside it was touched; the
selection spine, `ui/**`, `styles.css`, `api.ts` and the core are all
untouched. Behaviour is unchanged — this is a restyle plus interaction polish.

## What was implemented

- `views.css` — the view design layer. Every colour and every spacing is a
  `var(--gp-*)` token; the only raw numbers are hairline/focus stroke widths
  (1px/2px/3px) and a few layout minimums expressed in `rem` (`min-width`,
  `min-height`), because the token scale has no border-width or min-size token.
- `views/kit.tsx` — local `Spinner`, `EmptyState`, `IconButton`, `ActionButton`
  built from `ui/Icon` + `ui/Tooltip` + tokens. These are placeholders for the
  primitives the shell agent is adding to `ui/`; swap them out when those land.
- `views/virtualize.ts` (+test) — pure windowed-rendering arithmetic for the
  truth table, with a "render everything" fallback when the viewport is
  unmeasurable (jsdom).
- `views/bomSort.ts` (+test) — pure BOM column ordering.
- `views/schematicSelection.ts` (+test) — pure mapping from a §15.2 highlight
  set to netlistsvg element ids/classes.

Per view:

- **TruthTable** — real data grid: sticky headers, zebra rows, monospace, the
  divergence made colour *and* icon (a row-level `error` icon plus a per-cell
  flag on the divergent output), keyboard-selectable rows (`tabIndex` + Enter/
  Space), tooltips on the `#`/expected/actual headers, windowed rendering for
  2^n tables, and real empty/loading states.
- **Schematic** — zoom in/out with a live % readout, fit-to-window, reset zoom,
  a layer legend, self-contained scrolling, and the §15.2 selection drawn on
  the rendered cells/nets with the `--gp-select-*` tokens (a `gp-sel` class,
  applied by `selectionSvgTargets`).
- **BomView** — sortable columns (`aria-sort` on the headers), monospace part
  numbers, a "Gates/pkg" column + a "Spares" stat card so the spare-gate story
  is visible at a glance, and a prominent (icon + red marker + left border)
  single-source warning. The "grouping is inert" claim stays derived from
  `BomLine.gatesPerPackage`, never hardcoded.
- **AnalysisView** — metric cards (value, unit, limit, band) where the band is
  rendered from the core's `Metric.violated` only; the §6 verdict keeps its own
  icon + label + reasons + alternative, all from `estimate()`.
- **VerificationPanel** — the four-state badge restyled so passed/bounded/
  failed/not-run are distinct by shape and icon as well as colour (bounded gets
  a square amber glyph and always shows `(k = N)`); counterexample steps are
  navigable by click and by Enter/Space.
- **SpecEditor** — tab icons, a dirty-state indicator in the tab strip, and
  diagnostics with per-severity icons; the three-way sync is untouched.
- **FsmGraph** — nodes/edges restyled through the token theme (removed the
  hardcoded `#4c9ffe`/`#23a55a`), with a distinct `fsm-node--selected` /
  `fsm-edge--selected` state on top of the cross-highlight.

## What I guessed / had to decide

1. **Virtualisation row height.** Fixed at 28px (`--v-row-h: calc(--gp-space-4
   + --gp-space-3)` in views.css; `ROW_HEIGHT_PX = 28` in TruthTable.tsx). The
   spacer arithmetic only works if the two stay equal; there is no test that
   reads the CSS custom property, so a future edit could drift them silently.
   Weakest link — see below.
2. **The dirty indicator reads `project.dirty`.** That is the only dirty flag
   on the IPC contract. It does **not** update live in this worktree because
   `state/project.tsx` sets `project` once at `openProject()` and never
   subscribes to `onProjectChanged` — outside my scope to fix. So the indicator
   currently reads "saved" and will only become live once the shell wires
   `onProjectChanged` into `ProjectProvider`.
3. **Metric "band" is binary** (`met` / `violated`) because the core's `Metric`
   only carries `violated: boolean`; there is no per-metric three-way band. The
   three-band (green/amber/red) verdict is whole-design only, from
   `EstimateResult.verdict`, and is rendered separately.

## Placeholders

- `views/kit.tsx` mirrors `Button`/`IconButton`/`Panel`/`EmptyState`/`Spinner`
  the shell is adding. Replace with the real primitives when available.
- Schematic "pan" is native scroll of the canvas container (which is also what
  "wide content scrolls inside its own container" requires). No drag-to-pan was
  added.
- The metric-card grid uses `minmax(14rem, 1fr)`; there is no card-width token.

## What I could not verify

- The visual result in a real 1920x1080 window (no screenshot pipeline here;
  only jsdom tests + the Electron e2e smoke which does not assert styling).
- That `project.dirty` flips true on edit in the real main process.
- The dark-theme token values render as intended — they were not viewed, only
  written to the token names.

## What is weakest

- **The `.pane` theme vs. the shell chrome.** `views.css` sets
  `.pane { background: var(--gp-bg); color: var(--gp-text) }` so the views are
  self-consistent (light-by-default, dark via `data-theme`). Until the shell
  migrates `body`/`.app__*` off the legacy `--bg`/`--text` dark aliases in
  `styles.css`, there will be a light-pane-on-dark-chrome seam. That seam is the
  shell's migration, not a view defect.
- **The SVG selection highlight visuals.** The `gp-sel` class application is
  well tested (unit + component); the exact stroke/fill cascade
  (`.schematic__canvas g.gp-sel …`) is best-effort and was not eyeballed against
  a real netlistsvg render.
- **Virtualisation end-to-end.** The window arithmetic is unit-tested and the
  jsdom fallback (render all) is covered by the existing tests, but the real
  scroll-driven window is not exercised in jsdom (no layout). A browser-only
  behaviour.

## Suspicions to record

- `Metric.value` is typed `number` but the old code guarded `=== null`; I kept
  the guard so an uncomputed metric renders `—`. If the core ever emits a null
  value the contract says it cannot, the type is wrong rather than the view.
- The "spare-gate at a glance" story leans on `BomLine.gatesPerPackage` being
  accurate; if the core reports 1 for a multi-gate part, the BOM column and the
  `inert` claim would both go silently wrong (a false claim about the user's
  design — the exact failure this project has shipped before).
- No `chevronUp` / `plus` icon exists in the set; the sort indicator rotates
  `chevronDown` via CSS and the "+ state"/"+ transition" buttons stay text-only.

## Test counts

- Before: **180 pass** (28 files). After: **201 pass** (31 files) — 21 new
  tests, none existing removed. `tsc --noEmit` (both configs), `vite build`,
  and the Electron e2e suite (**12 pass**, incl. the M13 graph-edit regression)
  all pass.
