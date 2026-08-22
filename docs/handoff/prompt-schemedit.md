# Package A — the schematic edits the spec (§C12 → design.yaml)

Read `docs/handoff/delegation-rules.md` first. Every rule there applies.

## The state of play

`design.yaml` is the single source of truth. `renderer/state/project.tsx` holds
its text; `setSpecText(text)` debounce-writes it through `api.writeSpec`,
re-parses the model, and bumps `revision`. **Every view already derives from
that**, so an edit that lands in `design.yaml` updates the whole application for
free. You do not need to notify anything.

Two views already edit through that spine, and they are your templates:

* `renderer/views/BomView.tsx::handleRegroup` — drag-regroup writes
  `packing.force_groups`.
* `renderer/views/spec/FsmGraph.tsx` — graph edits mutate the YAML, and node
  positions are deliberately **never** written into `design.yaml`.

The schematic (`renderer/views/Schematic.tsx`) is the one view that is still
read-only. Close that.

## What you may NOT do, and why it is not pedantry

§24.3 declines **interactive schematic capture**: "Editable schematic state is
exactly the lock-in gatepack exists to avoid. C12 renders; it never edits."

That is not a style preference — the schematic renders a *post-`abc` synthesised
netlist*, and the map from gates back to the FSM spec is **not invertible**.
There is no `design.yaml` that means "this NAND2 is now an AND2", and there is
no correct place to store one. So:

* **Never** write gate-level state anywhere: no netlist edits, no gate types, no
  wire topology, no coordinates, no positions, no separate schematic file.
* **Never** add a field to `design.yaml` that only the schematic understands.
* Every edit you add must be a **field that already exists in the spec** and
  that a human could have typed by hand.

You are making the schematic an *input surface for spec facts*, not a capture
tool. If you find yourself wanting to store something the spec has no home for,
stop and write it up in the notes instead of inventing a field.

## Your file scope — nothing outside it

* `app/renderer/views/Schematic.tsx`
* `app/renderer/views/schematicEdit.ts` (new) + `schematicEdit.test.ts` (new)
* `app/renderer/views/Schematic.test.tsx`
* `app/renderer/design/model.ts` + `app/renderer/design/model.test.ts`
* `app/renderer/views/views.css`
* `docs/BUILD-NOTES-schemedit.md` (new), `docs/handoff/notes-schemedit.md` (new)

**Off-limits** (another agent is in them right now): `renderer/shell/**`,
`renderer/selection/**`, `renderer/views/SpecEditor.tsx`, `renderer/styles.css`.
Also off-limits as always: `app/shared/api.ts`, `gatepack-design.md`, the
`docs/*-FINDINGS.md` and audit files.

## What to build

Three edits, all landing in `design.yaml`. Each needs a surgical **text** editor
in `renderer/design/model.ts` in the style of the existing
`setPackingForceGroups` / `setField` — edit the YAML text in place, preserve the
user's comments and formatting, return an `EditOutcome`. Do **not** round-trip
through `modelToYaml`, which would reformat the user's file.

### 1. Test points — click a net, toggle it

`test_points:` is a list of `{net: <name>}`. The schematic already renders them
(`showOverlay` layer) and already knows which net is under the pointer
(`data-gp-net`, set by `renderer/views/schematicDecorate.ts`).

Add `setTestPoints(text, nets: string[]): EditOutcome` to `model.ts`. Clicking a
net with the edit affordance active toggles that net's membership.

Watch the name space: `data-gp-net` carries the *display* name chosen by
`netNameClasses` (it prefers a written name like `match` over Yosys's generated
`$abc$133$new_n12_`). A generated name is not a stable identifier and must never
be written into `design.yaml` — refuse those with a visible reason, exactly as
`handleRegroup` refuses when it has no stable names. Test that refusal.

### 2. Input `sync` — click an input port, toggle its synchroniser

`inputs:` is a list of `{name, sync}`. Toggling `sync` is a real spec change
with a visible schematic consequence: the §9.3 two-flop synchroniser appears or
disappears on the next build. Add `setInputSync(text, name, sync): EditOutcome`.

The schematic knows its input ports from `parsed.inputs`, and the rendered
`inputExt` symbols carry `id="cell_<portname>"`.

### 3. Package regrouping — drag a gate between package boundaries

Only meaningful with the packed layer on. This is the *same* operation
`BomView::handleRegroup` performs, driven spatially instead of from a list.

**Reuse its logic, do not re-derive it.** In particular reuse the stable-name
guard verbatim in spirit: the rendered SVG is keyed by ABC *instance* names
(`$abc$148$…`) which are renumbered by every synthesis, while
`packing.force_groups` is resolved against **stable cone-hash** names. Writing
an instance name is refused by the packer on the next build, and if it were not
it would name a *different gate*. With no build result there is nothing safe to
write — say so, do not write a lesser thing. Four defects in this repo have come
from conflating those two name spaces; `renderer/panels/MappedNetlistPanel.tsx`
documents them.

If `handleRegroup`'s logic needs to be shared, move the pure part into
`renderer/views/schematicEdit.ts` and have BomView import it — but BomView.tsx
is **not** in your scope, so if that requires touching it, do not; duplicate the
guard and say so in the notes instead.

## Interaction requirements

* Editing must be **opt-in and visible**: a toggle in the schematic toolbar
  (label it plainly — "edit"), off by default. With it off the view behaves
  exactly as it does today. A schematic that silently rewrites the user's spec
  because they clicked to inspect a net is a defect, not a feature.
* Every edit affordance must show what it will do *before* the click (title/
  tooltip naming the field and the new value).
* Every refusal must state the reason in the UI, not the console, and never
  fall back to writing something weaker.
* Keyboard-reachable: these are buttons, not bare click handlers on SVG.

## Acceptance

1. `npx vitest run` — 334 pass at baseline, all still passing plus yours.
2. `npx tsc --noEmit -p tsconfig.json` clean.
3. A test that toggles a test point from the schematic and asserts the **YAML
   text** gained the entry, with the user's comments and unrelated formatting
   intact. Round-tripping through the model would destroy those; prove it does
   not happen.
4. A test that a *generated* net name (`$abc$…`) is **refused** with a visible
   message and that `design.yaml` is unchanged.
5. A test that regrouping with no build result refuses rather than writing an
   instance name.
6. A test that with the edit toggle **off**, clicking a net changes nothing.
7. `npx playwright test` — 24 pass, unchanged.

## The failure mode to avoid

This project has shipped nine pieces of machinery that reported a status while
measuring nothing. The version of that failure here is an edit affordance that
appears to work, writes something the next build silently ignores, and leaves
the user believing their design changed. **Build the input that makes each of
your checks fail and keep it as a test.** If you cannot make a check fail, it is
not a check.

## Output

`docs/BUILD-NOTES-schemedit.md` and `docs/handoff/notes-schemedit.md`: what you
implemented, what you guessed, what you could not verify, and the three things
you are least confident about. Record suspicions as well as facts — notes from
previous runs have caught defects the agent could not reach itself.
