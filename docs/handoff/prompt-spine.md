# Package G — the editing spine, finished

Read `docs/handoff/delegation-rules.md` first. Every rule there applies.

## The state of play

`design.yaml` is the single source of truth. `renderer/state/project.tsx` holds
its text; `editSpec(update)` applies an edit to the *live* text and bumps
`revision`, and every view derives from that. Two packages landed on that spine
recently (`4f9ae1a`): the schematic and the Inspector both edit the spec, and the
whole application follows.

Four things were left unfinished, and one defect was found while briefing you.
They are ordered by how much they matter, and item 1 is not optional.

---

## 1. `renameState` destroys the user's comments and reformats their document

**Measured here, 2026-08-23, not suspected.** `renameState('RUN' -> 'ACTIVE')`
on this input:

```yaml
states:
  # IDLE is the power-on state; do not reorder, the encoder is stable on order
  - IDLE
  - RUN
transitions:
  # the operator's start button, debounced in hardware
  - {from: IDLE, to: RUN, when: "go"}
output_logic:
  # asserted only in RUN — safety-relevant, see review 2026-03
  busy: "state == RUN"
```

produces:

```yaml
states: [IDLE, ACTIVE]
transitions:
  - {from: IDLE, to: ACTIVE, when: go}
output_logic: {busy: "state == ACTIVE"}
```

**Nought of three comments survives**, and three block-style collections are
reflowed into flow style. A safety note explaining why an output is asserted,
deleted because someone renamed a state from the Inspector.

The cause is `applyEdits`, which re-serialises each whole top-level block
through `serializeTopLevelValue`. This is the same defect that was found and
fixed in `setInputSync` and `setTestPoints` during the last review — see
`docs/handoff/notes-editreview.md` §2 and §3. `renameState` is the one that was
missed, and it is the most destructive of the three because it rewrites four
blocks at once.

**Fix it the way those two were fixed: a line-level splice.** A rename changes
identifiers inside lines; it must not rewrite the lines around them, and it must
not touch a line that does not contain the name. Prove it by diffing line arrays
— exactly the lines you intended to change, and no others.

Then check whether `applyTopLevelEdit` and `setField` have the same problem for
the callers that still use them, and say what you find. Do not rewrite them
blind; report first, fix what you can prove.

## 2. `renameInput` does not exist

Renaming an input from the Inspector is currently *refused*, because renaming
`go` strands every `when: "go"` guard and the design goes invalid. The refusal
is correct behaviour for code that cannot fix up references; it is the wrong
answer for a user who wants to rename an input.

Add `renameInput(text, oldName, newName): EditOutcome`, line-spliced, following
the corrected `renameState`. It must rewrite the identifier in:

* `inputs[].name`;
* every `transitions[].when` guard;
* every `output_logic` expression;
* every `properties[].expr`;
* `expressions` values;
* `fundamental_mode.mutually_exclusive` groups;
* `safe_state` keys/values where they name an input.

**Identifier-aware, not textual.** `go` must not match `going`, `go_n`, or the
`go` inside a quoted string that is not an expression. The existing
`renameExprState` uses a `\b`-anchored regex; that is the right shape but it is
applied to whole expressions — check it is sound for input names too, and if it
is not, say so rather than reusing it.

Refuse, with the reason shown, when: the new name is not a valid Verilog
identifier; it collides with an existing input, output, state or expression
name; or the resulting document fails `parseDesignText`. A refusal leaves the
text **byte-identical**.

Then wire it into the Inspector, replacing the current refusal.

## 3. The reveal does not switch tabs

`SpecEditor.tsx` has three tabs — `yaml`, `form`, `graph` — and the §15.2 reveal
sets a line for Monaco. If the user is on `form` or `graph`, selecting a
transition reveals a line nobody can see, and the feature looks broken.

Make the reveal switch to the tab that can show what was revealed. Two rules:

* **Never steal focus.** The existing reveal is deliberately focus-preserving so
  the user can keep working in the view they selected from; switching tabs must
  not change that.
* A tab switch is a visible change to the user's workspace, so it happens only
  when there is something to reveal. `resolveSpecAnchor` returning `null` must
  not move anything.

Consider whether the `graph` tab can satisfy a `state`/`transition` reveal
directly (by selecting the node) rather than forcing the user to YAML. If it
can, prefer that — but only if you can test it.

## 4. The regroup refusal is unreachable by a click

The schematic refuses to write `packing.force_groups` when it has no stable
cone-hash names, and that refusal is unit-tested. It cannot be reached through
the UI, because an empty packed view offers no drop target
(`docs/handoff/notes-schemedit.md`, its own note 1). A refusal a user cannot
reach is a refusal that has never been seen.

Give the schematic a package drop target that exists even when the packed view
is empty, so the refusal is reachable, visible, and testable through a real
click. Do not weaken the refusal to make it reachable — the point is that the
user is *told why*, not that the drop succeeds.

## 5. Widen the structural anchor route

`resolveSpecAnchor` has two routes: provenance (`cell`/`net`) and structural
(`state`/`transition`/`input`/`property`). Provenance coverage on the goldens
runs **0.36 to 0.88** (`docs/handoff/notes-provenance-ceiling.md`), so for a
`cell` selection `null` is the common case, and the Inspector's answer is "no
link" most of the time.

That is *correct* — a post-`abc` gate genuinely has no spec ancestor, and the
gap is real, not a bug. So do not paper over it. Instead:

* extend the **structural** route to the constructs it does not yet cover:
  `outputs`, `expressions`, `test_points`, `constraints`, `macros`, `packing`;
* for a `cell`/`net` with no provenance entry, you may add an explicitly
  `inferred` fallback — e.g. the output whose cone contains the net — **only if
  it is labelled `inferred` and the Inspector shows that label**. Never report
  `exact` for a derived answer, and never invent a link that is merely plausible.
  If you cannot build a fallback you trust, leave it `null`: "no link" is a
  correct and useful answer, and this project prefers it to a confident guess.

---

## Your file scope — nothing outside it

* `app/renderer/design/model.ts` + `model.test.ts`
* `app/renderer/selection/specAnchor.ts` + `specAnchor.test.ts`
* `app/renderer/shell/Inspector.tsx` + `Inspector.test.tsx`
* `app/renderer/views/SpecEditor.tsx`, `app/renderer/views/spec/**`
* `app/renderer/views/Schematic.tsx`, `schematicEdit.ts` and their tests
  (item 4 only)
* `app/renderer/views/views.css`, `app/renderer/styles.css`
* `docs/BUILD-NOTES-spine.md`, `docs/handoff/notes-spine.md`

**Off-limits**: `app/renderer/views/BomView.tsx` (do not change the BOM's own
regroup path — duplicate a guard and say so if you must), `app/renderer/state/**`,
`app/main/**`, `gatepack/**`, `libraries/**`, `examples/**`. Also always
off-limits: `app/shared/api.ts`, `gatepack-design.md`, `docs/*-FINDINGS.md`,
`docs/MILESTONE-AUDIT.md`, `docs/GUI-AUDIT.md`.

No new `design.yaml` fields. Nothing stored outside the spec — no editor state,
no positions, no selection history. The Inspector reads `specText` and writes
`specText`; it never becomes a second source of truth.

## Acceptance

1. From `app/`: `npx vitest run` — **388 pass** at baseline, all still passing
   plus yours; `npx tsc --noEmit -p tsconfig.json` and `-p tsconfig.main.json`
   clean; `DISPLAY=:1 npx playwright test --config playwright.config.cjs` —
   **24 pass**.
2. A test that `renameState` preserves **every** comment and the block/flow
   style of every collection it does not need to change. Build it from the input
   quoted in item 1 above — it currently loses three comments, so the test fails
   before your fix and passes after. Include that before/after in your notes.
3. A test that `renameInput` rewrites a guard, an output expression and a
   property expression in one edit, and that `going` is left alone by a rename
   of `go`.
4. A test that each refusal leaves `specText` **byte-identical** and shows a
   reason.
5. A test that selecting a transition while the `form` tab is active ends with
   the revealed line visible, and one that a `null` anchor moves nothing.
6. A test that reaches the regroup refusal **through a simulated click**, not by
   calling the handler.
7. Every structural route you add has a test built so that the naive answer
   (first match, or line 1) would be wrong.

## The failure mode to avoid

Nine pieces of machinery in this repo have reported a status while measuring
nothing, four with tests that could not have failed — and one of those four was
a test written specifically to prevent this. The version here is a rename that
"works" on a spec with no comments in it, or a tab switch asserted against a
debounced write that had not happened yet (the debounce is **400 ms** in
`project.tsx`; a synchronous assertion after a click proves nothing). **For
everything you add, build the input that makes it fail and keep that as a test.**

## Output

`docs/BUILD-NOTES-spine.md` and `docs/handoff/notes-spine.md`: what you
implemented, what you guessed, what you could not verify, what you found about
`applyTopLevelEdit`/`setField`, and the three things you are least confident
about. Record suspicions as well as facts.
