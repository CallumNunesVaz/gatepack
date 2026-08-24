# Package N — dragging one edge in the FSM graph deletes the comments

Read `docs/handoff/delegation-rules.md` first. Every rule there applies.

## The gap, measured

`applyTopLevelEdit(text, key, transform)` re-serialises the whole block for
`key` from a parsed value. Everything *outside* the block survives; everything
*inside* it is regenerated from scratch. Adding one transition to the bundled
`examples/edge_detector/design.yaml`:

```diff
 transitions:
-  # S0: the input was low. A rise is the edge we are looking for.
-  - {from: S0,    to: PULSE, when: "din"}
-  - {from: S0,    to: S0,    when: "!din"}
-  # PULSE: the edge was just seen; emit for this cycle, then track the input.
-  - {from: PULSE, to: S1,    when: "din"}
+  - {from: S0, to: PULSE, when: din}
+  - {from: S0, to: S0, when: "!din"}
+  - {from: PULSE, to: S1, when: din}
+  - {from: S1, to: S0, when: "!din"}
```

Three losses, in descending order of seriousness:

1. **Both comments are gone.** The bundled examples teach through exactly those
   per-transition comments — `edge_detector` explains what each state *means*
   there and nowhere else. A user who drags one edge in the graph destroys the
   thing they were reading, silently, and the write is debounced so there is no
   obvious moment to undo.
2. **Quoting is normalised**: `when: "din"` becomes `when: din`.
3. **Alignment is lost**: the hand-aligned `{from: S0,    to: PULSE, ...}`
   columns collapse.

This is the same class of defect the spec editor's rename path already fixed by
switching from re-serialisation to line splicing. The graph never got it.

## What already exists — use it, do not reinvent it

`app/renderer/design/model.ts` already contains the line-splicing machinery,
built for the rename work:

- `splitBlockLine`, `itemStartLines`, `spliceBlockLines`, `applyRangeEdits`
  (private helpers)
- `spliceItemField`, `setItemField` (private)
- `setTransitionWhen(text, index, when)`, `setPropertyExpr(text, index, expr)`,
  `renameState`, `renameInput`, `setInputSync` (exported, splice-based)

So *modifying a field of an existing list item* is already solved and comment-
preserving. What is missing is **adding and removing list items**, and the graph
and form not using any of it.

**Read `setInputSync` before you write anything.** It is the same fix, already
done, for one field — and its comment records the same defect measured on a
different block:

> Measured: toggling input `b` deleted `# MUST stay synchronised —
> metastability` from input `a`. That is a safety note about metastability,
> removed by editing an unrelated field, and the user is never told.

Match that approach and that standard of evidence.

## The architecture to implement

### 1. Add splice-based list-item operations to `model.ts`

```ts
export function appendListItem(text: string, key: string, item: YValue): EditOutcome;
export function removeListItem(text: string, key: string, index: number): EditOutcome;
```

Rules these must follow, each of which is the point of the exercise:

- **Only the lines belonging to the affected item may change.** Every other
  line in the document — comments, blank lines, alignment, quoting — must be
  byte-identical.
- **Appending** inserts after the last item's last line, matching the indent and
  the inline/block style already in use in that block. If the existing items are
  written as `- {from: A, to: B, when: "x"}`, the new one is too.
- **Removing** takes out the item's own lines. A comment line sitting *directly
  above* an item, with no blank line between, belongs to that item and goes with
  it; a comment separated by a blank line, or at the top of the block, stays.
  State that rule in a comment where you implement it — it is a judgement call
  and the next reader needs to know it was made deliberately.
- An empty list, a block with no items yet, and a `key` that is not present are
  all real cases. Decide what each does and test it.

### 2. Use them from the editors

`app/renderer/views/spec/FsmGraph.tsx` — `setTransitions` currently rewrites the
whole `transitions` block for every operation, and `updateEdge` goes through it.
Replace with:

- `updateEdge` -> `setTransitionWhen` / `setItemField`-style splices (the `from`
  and `to` fields need the same treatment `when` already has; add exported
  helpers if they do not exist).
- `addTransition` -> `appendListItem`.
- `addState` -> already edits `states`, which is usually a one-line flow
  sequence, but check it against a `states:` written as a block list with
  comments and fix it if it destroys them.

**FsmGraph has no edge deletion** — I checked, there is no delete handler and no
`onEdgesDelete`. Do not add one; that is a feature, not this package.

`app/renderer/views/spec/StructuredForm.tsx` — the `×` buttons on inputs,
outputs and properties each call `setInput(model.inputs.filter(...))`, which
rewrites the whole block from the model and is where `removeListItem` earns its
place. `setInput`, `setOutput` and `setProperty` all rewrite whole blocks the
same way for every operation; give them the same treatment.

`setInputSync` is **already** splice-based (see above) — do not "fix" it. Check
`setInputName` rather than assuming either way.

## Acceptance criteria

1. **A test built from a real bundled example.** Use the actual text of
   `examples/edge_detector/design.yaml` (it has comments inside `transitions`,
   hand-aligned columns and quoted scalars — that is why it is the right
   fixture). For **each** editor operation — add a transition, change a
   transition's `from`/`to`/`when`, delete a transition, add a state, add an
   input — assert:
   - the comments that were inside the block are still there, verbatim;
   - every line not belonging to the changed item is byte-identical;
   - the result still parses with no new diagnostics.
2. **The failing case is kept.** Write the assertion so it fails against the
   current `applyTopLevelEdit` path. If your test passes before your change, it
   is testing nothing — this project has shipped nine pieces of machinery that
   reported a status while measuring nothing, and four had tests that could not
   have failed.
3. Baselines, all of which must still pass:
   `.venv/bin/python -m pytest -q` (**904 pass, 5 skip**);
   from `app/`: `npx tsc --noEmit -p tsconfig.json`,
   `npx tsc --noEmit -p tsconfig.main.json`, `npx vitest run` (**430 pass**),
   and after `npm run build`, `DISPLAY=:1 npx playwright test` (**51 pass**).

   `app/tests/e2e/examples-end-to-end.spec.ts` and `schematic-pointer.spec.ts`
   need the `gatepack-toolchain:m6` docker image and take about a minute; they
   are expected to pass, not skip.

## File scope

Yours: `app/renderer/design/model.ts`, `app/renderer/views/spec/FsmGraph.tsx`,
`app/renderer/views/spec/StructuredForm.tsx`, and their tests.

Off-limits: everything else. In particular `app/shared/api.ts`, anything under
`gatepack/`, `app/renderer/shell/`, and every file in the "do not edit" list in
the rules. Do not change any file under `examples/` — read the fixture, copy its
text into your test.

## Two things to be careful about

- **`applyTopLevelEdit` has other callers.** Do not change its behaviour to fix
  this; add the new functions alongside and move the callers that need them.
  Something else may depend on the canonicalising behaviour.
- **A splice that produces invalid YAML is worse than a re-serialisation that
  loses a comment.** Every one of these must re-parse and be checked for new
  diagnostics before it is returned — `EditOutcome` already carries
  `diagnostics` for this. Make sure a malformed splice is caught by a test.

Write `docs/BUILD-NOTES-speccomments.md`.
