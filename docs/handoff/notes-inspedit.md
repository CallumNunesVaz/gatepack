# Handoff notes — the selection spine becomes bidirectional and editable

## What changed

The Inspector no longer stops at *description*. Selecting anything now shows
where it came from in `design.yaml`, and the constructs that have a spec field
(`input`, `state`, `transition`, `property`) can be edited right there.

- `app/renderer/selection/specAnchor.ts` (new) — pure
  `resolveSpecAnchor(selection, provenance, specText)` returning
  `{ line, route: 'provenance' | 'structural', confidence: 'exact' | 'inferred' }`
  or `null`. Provenance resolves `cell`/`net` via pointer lines (exact beats
  inferred, then lowest line); structural parses the `YamlNode` tree to locate
  `state`/`transition`/`input`/`property` by identity, not by text search.
- `app/renderer/shell/Inspector.tsx` — read-only field list replaced by per-kind
  editable fields, an anchor readout (`line + route + confidence + "reveal"
  control`), the provenance pointers kept as evidence, and `role="alert"`
  refusals. `cell`/`net`/`package`/`minterm`/`cexStep` render an explicit
  "not directly editable" note, never a fabricated field.
- `app/renderer/views/SpecEditor.tsx` — reflects the selection spine and reveals
  the anchored line in the YAML editor (selection-driven, ref-based so typing
  never re-scrolls).
- `app/renderer/views/spec/MonacoEditor.tsx` — new optional `reveal` prop
  (`revealLineInCenter` + whole-line decoration; no focus/cursor move).
- `app/renderer/styles.css` — anchor + edit-field styles and the reveal highlight.
- Tests: `specAnchor.test.ts` (13) and `Inspector.test.tsx` (11), new.

## What I guessed / flagged

1. **The anchor route split is by selection kind.** `cell`/`net` → provenance;
   `state`/`transition`/`input`/`property` → structural; the rest → `null`
   ("no link", never line 1).
2. **A `{from, to}` transition selection cannot disambiguate two transitions
   that share *both* endpoints.** The `Selection` type has no index. The
   resolver (and the Inspector's `when` editor) key on from/to and take the
   first match. The twin-guard acceptance test uses identical guards but
   *different* from/to, which is the case that must be correct — and is.
3. **Property expressions are validated with the client-side `expr` parser**,
   because `parseDesignText` does not check them; otherwise a garbage property
   expression would be a silent no-op-looking "success".
4. **The reveal button only dispatches `view.spec`.** If the user is already on
   the spec view's form/graph tab, it does not switch to the YAML tab (tab state
   is local to SpecEditor). Reveal is correct on view-switch and on
   switch-to-YAML-tab.

## Not verified / unfinished

- **Nothing was run.** This worktree has no `node_modules/` and no `.venv/`, and
  `npm install` is forbidden. `tsc`, `vitest` and `pytest`/playwright were all
  un-runnable. The code is written to existing exports and test idioms but has
  not been executed — treat the type-level correctness as unverified.
- The Monaco reveal decoration has not been seen live (dark theme, both surface
  tints).
- The reveal-button → YAML-tab gap (above) is not wired; recorded, not fixed.

## Test results

- Before: 334 renderer vitest (baseline) — **not re-run** (no `node_modules`).
- After: unknown; 24 new tests added (13 `specAnchor.test.ts`, 11
  `Inspector.test.tsx`), none of the existing 334 touched.
