# Handoff notes — the editing spine, finished (§G)

## What changed

- `design/model.ts` — `renameState` rewritten as a line-level splice (only the
  lines carrying the name change; comments and block/flow style elsewhere survive
  byte-identical). New `renameInput(text, old, new)`, line-spliced and
  identifier-aware, with byte-identical refusals (bad identifier, name collision,
  unknown input, unparseable result). Both sit on shared helpers
  (`identifierPattern`, `spliceBlockLines`, `renameInField`, `renameInMappingValues`).
- `selection/specAnchor.ts` — widened the structural route into
  `resolveStructuralLine(specText, ref)` over outputs/expressions/test_points/
  constraints/macros/packing (plus the existing four), and added an explicit
  `inferred` fallback for a `net` whose name exactly matches a declared
  output/input. Cells get no fallback.
- `shell/Inspector.tsx` — input *name* goes through `renameInput`, input *sync*
  through `setInputSync` (no more block re-serialisation of `inputs`). The
  `editInputs` helper is gone.
- `views/SpecEditor.tsx` — the reveal switches to the tab that can show it (form
  -> YAML; graph stays for state/transition; anything else -> YAML; null anchor
  moves nothing). Focus is never stolen.
- `views/spec/FsmGraph.tsx` — moved the `onNodesChange` `useCallback` above the
  `if (!model)` early return (a latent hooks-mismatch crash when the spec parses
  after first mount).
- `views/Schematic.tsx` — a dashed empty drop target when the packed view is
  empty, so the "run a build before regrouping" refusal is reachable by a real
  drop (and `views.css` styles it).

## Tests added / changed

- `model.test.ts` (+8): renameState preserves the three comments from the brief
  and diffs line arrays; renameState identifier-boundary; renameInput rewrites a
  guard + output + property + expression + fundamental_mode group in one edit,
  leaves `going`/`go_n`/a quoted non-expression alone, and refuses three ways
  byte-identical.
- `specAnchor.test.ts` (+12): every widened construct located by identity (naive
  "first match / line 1" would be wrong); the inferred fallback labelled
  `inferred`, never `exact`, and null for a cell/no-match; provenance still wins.
- `Inspector.test.tsx` (+2, one rewritten): the input-rename refusal test now
  asserts the rename *succeeds and fixes its guards*; + inferred-label test;
  + invalid-rename refusal test.
- `SpecEditor.test.tsx` (+3, new): form+transition ends on the revealed line;
  null anchor moves nothing; graph+state stays on graph. `FsmGraph.test.tsx`
  (+1, new): no hooks-mismatch on null->non-null model.
- `Schematic.test.tsx` (+1): the regroup refusal reached through mouseDown/
  mouseUp on the empty drop target.

## The `applyTopLevelEdit` / `setField` finding (item 1's second half)

They are safe for **scalar** fields and destructive for **list/mapping** blocks —
the same mechanism the earlier `setInputSync`/`setTestPoints` fix already
removed. Still affected: `Inspector.editTransitionWhen` (`transitions`),
`Inspector.editPropertyExpr` (`properties`), `FsmGraph.setTransitions`/`addState`,
`StructuredForm.edit`/`editField`. I fixed the input paths (provable, in the
spine) and left the rest reported rather than blind-rewritten. See
`BUILD-NOTES-spine.md` §1 for the table and a recommendation.

## Test results

- Before: 388 passed (vitest); 24 passed (playwright); 749 passed + 5 skipped (pytest).
- After: 415 passed (vitest, +27); 24 passed (playwright, unchanged); 749 + 5 (pytest, unchanged).
- `npx tsc --noEmit -p tsconfig.json` and `-p tsconfig.main.json` both clean.

## Not verified / unfinished

- The inferred fallback's net-name assumption (a net named like an output/input
  *is* that port) is unverified here — no Yosys. Verify in `gatepack-toolchain:m6`.
- The regroup drop is jsdom-dispatched, not Electron pixel hit-tested.
- `renameState` does not rewrite state references in `properties[].expr` (parity
  with the old code); `renameInput` does not touch `macros[].enable` or
  `clock/reset.signal`. Both are reference sites a rename could strand.

## Three things I am least confident about

1. The field-scoped rename regexes are not a full YAML-aware rewrite; pathological
   names (`to`/`when`/`sync`) could confuse a field matcher — untested.
2. The name-match fallback is narrower than the brief's cone-based example and
   rests on the unverified net-name assumption.
3. The remaining re-serialising callers (`editTransitionWhen` et al.) still lose
   intra-block comments — reported, not fixed.
