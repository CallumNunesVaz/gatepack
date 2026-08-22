# Package B — the selection spine becomes bidirectional and editable

Read `docs/handoff/delegation-rules.md` first. Every rule there applies.

## The state of play

§15.2 gives the application one selection, shared by every view
(`renderer/selection/bus.tsx`). A view *emits* with `setSelection` and *reflects*
with `useHighlights`. §15.1 provenance (`api.provenance()`) maps a spec pointer
to the nets and cells it produced. A pointer looks like

```
design.yaml:42:transitions[2]
```

— filename, **line number**, construct path. `renderer/selection/map.ts::parsePointer`
already splits it.

Today that spine runs one way only, and it stops at *description*: the Inspector
(`renderer/shell/Inspector.tsx`) says a cell links to some nets and shows a
confidence badge, and that is the end of the road. Selecting a gate never takes
you to the line of `design.yaml` that produced it, and nothing you select can be
edited from where you are looking at it.

Your job is to close both halves: **selection reveals its source, and the
Inspector edits it.**

`design.yaml` is the single source of truth. `renderer/state/project.tsx` holds
its text; `setSpecText(text)` debounce-writes it, re-parses the model and bumps
`revision`. Every view already derives from that, so an edit that lands in the
YAML updates the whole application for free.

## Your file scope — nothing outside it

* `app/renderer/shell/Inspector.tsx`
* `app/renderer/shell/Inspector.test.tsx` (new)
* `app/renderer/shell/Shell.tsx`
* `app/renderer/views/SpecEditor.tsx`
* `app/renderer/selection/specAnchor.ts` (new) + `specAnchor.test.ts` (new)
* `app/renderer/styles.css`
* `docs/BUILD-NOTES-inspedit.md` (new), `docs/handoff/notes-inspedit.md` (new)

**Off-limits** (another agent is in them right now): `renderer/views/Schematic*`,
`renderer/views/schematicEdit.ts`, `renderer/views/views.css`,
`renderer/design/model.ts`, `renderer/design/model.test.ts`.

That last one matters: you may **not** add new YAML editors to `model.ts`. Use
what is already exported — `setField`, `applyTopLevelEdit`, `renameState`,
`setPackingForceGroups` — and if an edit you want needs a new one, leave it out
and write it up rather than reaching into another agent's file.

## What to build

### 1. Selection reveals its line in the spec (`specAnchor.ts`)

A pure module: given a `Selection`, a `ProvenanceMap` and the spec text, return
the 1-based line in `design.yaml` that the selection came from, or `null`.

Two independent routes, and the difference must be visible to the user:

* **Provenance** — a `cell`/`net` selection matches provenance entries whose
  pointer carries a line number. Confidence is `exact` or `inferred`; carry it
  through, do not flatten it.
* **Structural** — a `state`/`transition`/`input`/`property` selection can be
  located directly in the YAML by parsing it. `renderer/design/yaml.ts::parseToJs`
  returns a `Map<string, Range>` of construct path → text range; that is the
  intended tool. This route is exact by construction.

`null` is a real answer and must render as one ("no link"), never as line 1.

Then: selecting anything anywhere reveals and highlights that line in the spec
editor. `SpecEditor.tsx` wraps Monaco (`renderer/views/spec/MonacoEditor.tsx`);
give it a way to reveal a line without stealing focus from the view the user is
working in. Revealing must never *modify* the text.

### 2. The Inspector edits the selection in place

Replace the read-only field list with the editable spec fields for whatever is
selected. Keep the existing link/confidence display — it is the evidence for the
edit, not clutter.

Cover at least:

* **`input`** — rename, toggle `sync`.
* **`state`** — rename (use the existing `renameState`, which already fixes up
  every reference), and set as `initial`.
* **`transition`** — edit its `when` guard.
* **`property`** — edit its expression.
* **`cell` / `net` / `package` / `minterm` / `cexStep`** — these have no directly
  editable spec field. Do **not** invent one. Show the provenance link and a
  control that takes the user to the responsible line. Saying "this is not
  directly editable, here is what produced it" is the correct answer.

Every edit goes through `setSpecText`. Do not write to disk yourself, do not
reformat the document, and do not round-trip through `modelToYaml` — that
rewrites the user's whole file and destroys their comments.

An edit that would produce invalid YAML or an invalid design must be **refused
with the reason shown**, and must leave the text untouched. `parseDesignText`
returns diagnostics; use them. A silent no-op is the worst outcome here: the
user believes the design changed and it did not.

### 3. Everything stays in sync

After an edit the model re-parses and the selection may no longer resolve — a
renamed state invalidates a `{kind:'state', id}` selection. Follow the rename
rather than dropping the selection or leaving it pointing at a state that no
longer exists. Test that.

## What you may NOT do

* No new `design.yaml` fields, and nothing stored outside the spec. No editor
  state, no positions, no selection history in the project file.
* Do not make the Inspector a second source of truth. It reads `specText` and
  writes `specText`; it holds no model of its own between edits.
* Do not touch the schematic. Another agent is making it an editing surface in
  the same window; your work must compose with theirs through the shared spine,
  not by reaching into it.

## Acceptance

1. `npx vitest run` — 334 pass at baseline, all still passing plus yours.
2. `npx tsc --noEmit -p tsconfig.json` and `-p tsconfig.main.json` clean.
3. A test that selecting a transition reveals the **right line number**, built
   from a spec where the naive answer (first match, or line 1) would be wrong —
   e.g. two transitions with identical `when` guards. A line-resolver that
   cannot be wrong on that input is not being tested.
4. A test that an edit preserves the user's comments and unrelated formatting.
5. A test that an invalid edit is refused with a visible message **and** leaves
   `specText` byte-identical.
6. A test that a `cell` selection offers no fabricated editable field.
7. A test that renaming a state keeps the selection pointing at that state.
8. `npx playwright test` — 24 pass, unchanged.

## The failure mode to avoid

This project has shipped nine pieces of machinery that reported a status while
measuring nothing, four of them with tests that could not have failed. The
version of that here is a line-reveal that is plausibly right on the one example
you tried and silently off by a few lines everywhere else, or an edit control
that renders, accepts a click, and writes nothing. **For everything you add,
build the input that makes it fail and keep that as a test.**

## Output

`docs/BUILD-NOTES-inspedit.md` and `docs/handoff/notes-inspedit.md`: what you
implemented, what you guessed, what you could not verify, and the three things
you are least confident about. Record suspicions as well as facts.
