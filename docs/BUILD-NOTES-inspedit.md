# BUILD NOTES — inspedit (bidirectional, editable selection spine)

Scope: close both halves of §15.2 for the Inspector — **selection reveals its
source line** and **the Inspector edits it in place**. `design.yaml` stays the
single source of truth; every edit goes through `setSpecText` and the model
re-parses from the text, so an accepted edit updates the whole application for
free. No new spec fields, no editor state persisted anywhere, no `model.ts`
changes.

## Files added / changed

- `app/renderer/selection/specAnchor.ts` (new) — pure `resolveSpecAnchor(selection,
  provenance, specText) → SpecAnchor | null`. Two routes, kept distinct:
  **provenance** (`cell`/`net` → pointer line, `exact`/`inferred` carried through)
  and **structural** (`state`/`transition`/`input`/`property` located by parsing
  the `YamlNode` tree, exact by construction). `null` is a real answer, never
  line 1.
- `app/renderer/selection/specAnchor.test.ts` (new) — 13 cases, including the
  twin-guard transition test (two transitions with identical `when` guards but
  different from/to pairs; the anchor keys on from/to, so B→C lands on line 14,
  not 13 and not 1).
- `app/renderer/shell/Inspector.tsx` — replaced the read-only field list with an
  editable field per kind (`input` name/sync, `state` name/initial, `transition`
  `when`, `property` `expr`), an anchor display (`line + route + confidence + a
  "reveal" control), and kept the provenance-confidence badge and pointer list.
  `cell`/`net`/`package`/`minterm`/`cexStep` render an explicit "not directly
  editable" note — no fabricated field. Refusals are shown as an `role="alert"`
  error note and leave `specText` byte-identical.
- `app/renderer/shell/Inspector.test.tsx` (new) — 11 cases: transition anchor
  line, no-link for package, state rename-follows-selection, set-as-initial,
  input rename/sync, property expr, invalid guard/property refusal with
  byte-identical text, cell has no editable field, and a surgical-edit test that
  asserts the comment + unrelated prefix/suffix survive byte-identically.
- `app/renderer/views/SpecEditor.tsx` — reflects the shared selection spine:
  computes the anchor and passes a `reveal` to Monaco. Reveal is driven by the
  **selection** only (latest spec/link context read via refs), so typing in the
  editor never re-triggers a scroll.
- `app/renderer/views/spec/MonacoEditor.tsx` — added an optional `reveal` prop:
  `revealLineInCenter` + a whole-line decoration, no cursor move and no focus.
- `app/renderer/styles.css` — anchor/edit field styles + `.spec-editor__reveal-line`.

## Test commands and result

```
$ .venv/bin/python -m pytest -q                  # NOT RUN — see "could not verify"
$ cd app && npx tsc --noEmit -p tsconfig.json    # NOT RUN
$ cd app && npx tsc --noEmit -p tsconfig.main.json  # NOT RUN
$ cd app && npx vitest run                       # NOT RUN
$ DISPLAY=:1 npx playwright test ...             # NOT RUN
```

**The checkout this worktree was handed to me on has no `node_modules/` and no
`.venv/`** (the delegation rules say both are pre-populated, but `find` shows
neither, and `npm install` is forbidden by both the rules and the no-network
environment). I therefore could **not** run any of the test/typecheck commands.
This is the single biggest risk in this package: the code is written against the
existing exports and test idioms, but has not been executed.

## What was built (and why)

### Anchor (specAnchor.ts)

- The structural route walks the **parsed `YamlNode` tree** (`parse()` from
  `design/yaml.ts`), not `ranges` — `ranges` is keyed by *top-level* key only and
  cannot tell two transitions with the same guard apart. `itemLine` reads
  `item.line` per sequence item, which is what makes the twin-guard test fail a
  text-search resolver and pass the from/to resolver.
- The provenance route reuses `parsePointer` and picks **exact over inferred**,
  then lowest line, deterministically. Pointers with no line are skipped (a
  pointer is not a line).

### Edits (Inspector.tsx)

- Edits are built with the sanctioned helpers only — `applyTopLevelEdit`,
  `renameState`, `setField` — never `modelToYaml`, never a whole-document
  rewrite. Each helper re-serialises only the affected top-level value, so
  unrelated lines, blank lines and comments survive byte-for-byte.
- `decide()` is the refusal gate: any `error` diagnostic on the candidate text
  refuses the edit and keeps the original text. A **property** expression is not
  validated by `parseDesignText`, so I additionally parse it with the same
  client-side `expr` parser the truth table uses before accepting.
- State rename uses the existing `renameState` (which fixes up every reference)
  and, on success, the Inspector **follows** the rename by re-emitting the
  selection at the new id — the renamed state stays selected rather than going
  stale. Input rename follows the same way.

### Reveal (SpecEditor.tsx / MonacoEditor.tsx)

- Reveal is reflected, not pushed: SpecEditor reads the same selection bus and
  computes the same anchor. The Inspector's "reveal" control only dispatches
  `view.spec` (already registered by the shell), which mounts SpecEditor; the
  editor then reveals the anchored line on mount. No focus is stolen.

## Guesses / decisions

1. **Reveal is driven by selection, not by spec text.** Depending on `specText`
   (or the re-parsed model) would re-reveal on every keystroke while the user
   types in Monaco. A ref keeps the latest text/link context so the effect only
   runs when the selection identity changes.
2. **The reveal button dispatches `view.spec`, nothing more.** If the user is
   *already* on the spec view but on the form/graph tab, the button does not
   switch to the YAML tab (tab state is local to SpecEditor). Switching to the
   YAML tab then applies the still-set reveal. This is the one UX seam I did not
   close.
3. **`package`/`minterm`/`cexStep` have no anchor and no editable field.** The
   two anchor routes are defined for the other kinds; these render "no link"
   honestly. `cexStep`/`property` *could* point at counterexample pointers, but
   those are whole-list `states`/`properties` tokens, not a spec line to edit.
4. **`transition` selections with identical from/to cannot be disambiguated.**
   The `Selection` type carries `{from, to}` only. `resolveSpecAnchor` (and the
   Inspector's `when` editor) key on the from/to pair and take the first match;
   two truly identical transitions would be edited/anchor to the first. The
   acceptance test uses identical guards but *different* from/to, which is the
   case the resolver must get right. Recorded, not guessed: a per-index
   transition selection would be a `Selection`-type addition (out of scope).

## Placeholders / could not verify

- **No test run.** As above: `node_modules/` and `.venv/` are absent and
  `npm install` is forbidden. Everything is untested at the type level and at
  runtime.
- **`OnMount` export from `@monaco-editor/react`.** I typed the Monaco reveal
  with `Parameters<OnMount>[0]`/`[1]` on the assumption `OnMount` is exported
  (it is in the package's public API). I could not compile to confirm; if it is
  not, replace the two `type StandaloneEditor`/`MonacoApi` aliases with
  `import type { editor as MonacoNs } from 'monaco-editor'`.
- **Real Monaco reveal behaviour.** `revealLineInCenter` + `createDecorationsCollection`
  are standard APIs, but I could not run the app to confirm the decoration
  class renders under the dark theme (`--gp-select-bg` is semi-transparent gold).
- **Playwright baseline unchanged.** The e2e suite does not assert on Inspector
  internals (I grepped), so removing the read-only field list should not regress
  it, but I could not run it.

## Three things I am least confident about

1. **The code has not been compiled or executed.** Without `node_modules`/`.venv`
   I wrote against the existing exports and idioms, but a single typo or a wrong
   type-name would only surface at `tsc`/`vitest`. This is the dominant risk.
2. **The Monaco reveal seam** — depending on `OnMount`'s export shape, the
   `StandaloneEditor`/`MonacoApi` aliases, and the whole-line decoration actually
   painting under both themes. Not verified live.
3. **The reveal button does not switch to the YAML tab** when the user is
   already on the spec view's form/graph tab. It reveals correctly in the
   common path (switch into the spec view, or switch to the YAML tab), but the
   in-view tab switch is a gap I chose not to wire across SpecEditor's local
   state.
