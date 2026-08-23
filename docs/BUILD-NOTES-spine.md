# BUILD NOTES — spine (§G: the editing spine, finished)

Scope: `app/renderer/design/model.ts` (+test), `app/renderer/selection/specAnchor.ts`
(+test), `app/renderer/shell/Inspector.tsx` (+test), `app/renderer/views/SpecEditor.tsx`
(+new test), `app/renderer/views/spec/FsmGraph.tsx` (+new test),
`app/renderer/views/Schematic.tsx` (+test), `app/renderer/views/views.css`.

## Test commands and result

```
cd app && npx tsc --noEmit -p tsconfig.json        # clean
cd app && npx tsc --noEmit -p tsconfig.main.json   # clean
cd app && npx vitest run                           # 415 passed (was 388, +27)
cd app && DISPLAY=:1 npx playwright test           # 24 passed (unchanged)
.venv/bin/python -m pytest -q                      # 749 passed, 5 skipped (unchanged)
```

New tests: `model.test.ts` (+8), `specAnchor.test.ts` (+12), `Inspector.test.tsx`
(+2, one rewritten), `SpecEditor.test.tsx` (+3, new file), `Schematic.test.tsx`
(+1), `FsmGraph.test.tsx` (+1, new file). None weakened; the one rewritten test
(the input-rename refusal) was *correct* against the old code and now asserts the
opposite — the rename that used to be refused now succeeds and fixes its guards.

---

## 1. `renameState` no longer destroys comments / reformats

**Measured defect:** `renameState('RUN' -> 'ACTIVE')` on the brief's input deleted
all three comments and reflowed `states`, `transitions` and `output_logic` into
flow style. Cause: the old implementation built a `Map<key, YValue>` of whole
top-level blocks and re-serialised each through `serializeTopLevelValue`.

**Fix:** a line-level splice. `spliceBlockLines(text, range, transform)` splits a
block's value into lines, applies `transform` to the *code* part of each line
(before any `#`), and only rewrites lines that change — comments and every
untouched line stay byte-identical. `renameState` now:

- `states` — whole-identifier replace (`identifierPattern`, so `RUN` never
  matches `RUNNING`);
- `initial` — a scalar range splice (comment outside the value survives);
- `transitions` — `from:`/`to:` field values only (`when:` is an input guard and
  is never touched);
- `output_logic` / `macros[].enable` — `state == NAME` only.

The test diffs the before/after line arrays and asserts exactly three lines
changed (`  - RUN`, `- {from: IDLE, to: RUN, when: "go"}`, `  busy: "state == RUN"`).

### `applyTopLevelEdit` / `setField` — what I found (reported, not blindly rewritten)

`applyTopLevelEdit` re-serialises the whole top-level block via
`serializeTopLevelValue`; `setField` is `applyTopLevelEdit` plus an append. For a
**scalar** field (`name`, `timing_model`, `encoding`, `initial`) that is safe —
the value is replaced in place and surrounding comments survive. For a **list** or
**mapping** block it is *not*: intra-block comments are dropped and the block is
reflowed to canonical flow style. That is the same bug the last review already
fixed in `setInputSync`/`setTestPoints`. Callers still affected:

| caller | block | loses |
|---|---|---|
| `Inspector.editTransitionWhen` | `transitions` | every comment inside the transitions block |
| `Inspector.editPropertyExpr` | `properties` | every comment inside the properties block |
| `FsmGraph.setTransitions`/`addState` | `transitions`/`states` | intra-block comments |
| `StructuredForm.edit`/`editField` | `inputs`/`outputs`/`properties`/`constraints` | intra-block comments |

What I fixed, because it was provable and in the spine's own path: the Inspector's
**input name** now goes through `renameInput` and its **input sync** through
`setInputSync` (both line-spliced), so the Inspector no longer re-serialises
`inputs`. I did *not* rewrite `editTransitionWhen`/`editPropertyExpr`/`FsmGraph`/
`StructuredForm`: the brief said report first, and a correct line-splice for a
single transition's `when` (or a property's `expr`) needs a *per-item* splice that
targets the right item among possibly-same-keyed items — more than a blind edit.
Left as a documented gap with a recommendation below.

---

## 2. `renameInput` (new)

`renameInput(text, oldName, newName)` is line-spliced like the corrected
`renameState`, and rewrites the identifier in `inputs[].name`, every
`transitions[].when`, every `output_logic` expression, every `properties[].expr`,
`expressions` values, and `fundamental_mode.mutually_exclusive` groups.

Identifier-aware, not textual: `go` does not match `going` or `go_n` (lookahead
over `[A-Za-z0-9_]`), does not match inside a `#` comment, and does not match a
quoted string that is not an expression (e.g. `reset.source: "go button"` is
untouched because the reset block is never processed). Inside expressions the
rename leaves `state == go` alone — a state reference, not an input reference —
by matching `state == NAME` first and only replacing the bare identifier.

Refusals (all byte-identical, with a reason): the new name is not a valid Verilog
identifier (`ED1025`); it collides with an existing input/output/state/expression
name; the old name is not an input; or the spliced result fails to parse. The
Inspector's input field is wired to it, replacing the old refusal, and the sync
checkbox is wired to `setInputSync`.

**Deliberate omissions, recorded:** `safe_state` is untouched — its keys are
output names and its values are `0`/`1`/`any`, so an input name can never
legitimately appear there (renaming would be wrong, e.g. an input literally named
`any`). `macros[].enable` and `clock.signal`/`reset.signal` are also not covered:
they are not in the brief's list, but an input referenced from a macro enable
would be stranded by a rename. Both are flagged below, not hidden.

---

## 3. The reveal now switches tabs

`SpecEditor`'s reveal effect (`[selection]`) now moves the tab when the current
tab cannot show what was revealed:

- current tab `form` — moves to `yaml` (the reveal is a Monaco line);
- current tab `graph` + `state`/`transition` — stays (the graph already selects
  the node/edge);
- current tab `graph` + anything else — moves to `yaml`;
- a `null` anchor — moves nothing.

Focus is never touched (the reveal was already focus-preserving; switching tabs is
a navigation, not a focus steal). I did **not** route `state`/`transition`
reveals *to* the graph tab even though the brief says "prefer that if testable":
React Flow needs a `ResizeObserver` jsdom does not provide, so the graph path
cannot be asserted in a test, and the acceptance's "revealed line visible" is a
line — YAML is the tab that shows it. The graph-stay guard keeps a node click
inside the graph from yanking the user to YAML.

## 4. The regroup refusal is reachable by a click

An empty packed view has no `[data-refdes]` boundary, so a regroup drag was
silently swallowed and `NO_BUILD_REFUSAL` was unit-tested but unreachable. The
schematic now draws a dashed **empty drop target** (`data-gp-drop-zone`,
`data-testid="schematic-drop-zone"`) when `editMode && showPacked` and the packed
view is empty; dropping a gate on it shows `NO_BUILD_REFUSAL` (the same string the
unit test asserts) and writes nothing. The refusal is not weakened — the drop
still does not succeed; the user is now *told why*.

## 5. Widened structural anchor route + inferred fallback

`specAnchor.ts` now exposes `resolveStructuralLine(specText, ref)` over a
`StructuralRef` union covering `state`, `input`, `output`, `property`,
`transition`, `expression`, `testPoint`, `macro`, `constraint`, `packing`. The
existing `state`/`input`/`property`/`transition` route now dispatches through it
(identical lines), and a new `mappingEntryLine` locates mapping entries
(`expressions`, `output_logic`, `constraints`, `packing`).

For a `cell`/`net` with no provenance entry, an explicitly `inferred` fallback is
attempted: a **net** whose name exactly matches a declared output (then input)
resolves to that construct's line with `confidence: 'inferred'` — never `exact`.
A **cell** gets no fallback; its `$abc$…` name never matches a spec construct, and
a cone/nearest-construct guess would be fabricated provenance. The Inspector
renders the badge (`SelectionBadge confidence={anchor.confidence}`) so "inferred"
is visible next to the line.

I did **not** implement the brief's cone-based example ("the output whose cone
contains the net"): cone analysis lives in `map.ts` (`coneCells`), outside my
file scope, and `resolveSpecAnchor` receives no netlist. The name-match subset is
the trustworthy fallback I could build and test here.

## 6. Latent hook-order bug in `FsmGraph` (found while testing item 3, fixed)

`FsmGraph` called `useCallback(onNodesChange)` *after* its `if (!model) return`
early return, so a spec that parsed after first mount (model null -> non-null)
re-rendered with more hooks than the previous render and React threw "Rendered
more hooks than during the previous render". Moved the hook above the early
return. `FsmGraph.test.tsx` (new) pins it with a `ResizeObserver` stub.

---

## What I guessed / decided

1. **The reveal switches to YAML, not to the graph.** The graph tab *does*
   already reflect a `state`/`transition` selection (it selects the node/edge), so
   the tab-switch logic leaves it there; but for the "switch *to* graph" variant
   the brief asks me to prefer only if testable, and React Flow is not testable in
   jsdom (no `ResizeObserver`). YAML is the tab that shows a *line*.
2. **`renameInput` is field-scoped, not block-scoped.** A whole-block textual
   replace would hit `when:` guards and `name:` fields in the wrong places (and a
   quoted non-expression). The per-field regexes (`\bwhen\s*:`, `\bname\s*:`,
   `\bexpr\s*:`, mapping values) assume the schema's realistic YAML shapes.
3. **The inferred fallback is name-match, not cone.** Narrower than the brief's
   example, but the only fallback I could build that is genuinely trustworthy
   rather than "merely plausible".

## Placeholders / could not verify

- **No Yosys here**, so the mapped-netlist assumption behind the inferred fallback
  (a net whose name equals an output/input name *is* that port's net) is not
  verified against a real build. `tests/toolchain/docker_runner.py` + the
  `gatepack-toolchain:m6` container would verify it.
- The drop-zone drag is exercised by jsdom `fireEvent.mouseDown`/`mouseUp`, not by
  Electron pixel hit-testing (the overlay flips `pointer-events: auto` mid-drag;
  real-browser hit-testing is not visually verified).
- `renameInput` on a spec that quotes an input name (`name: "go"`) is handled by
  the field regex, but I did not add a dedicated test for quoted input names.

## Pre-existing defects observed (not fixed — out of scope)

1. `editTransitionWhen` / `editPropertyExpr` / `FsmGraph` / `StructuredForm`
   still re-serialise their block and lose intra-block comments (see §1 table).
   A per-item line-splice (rename one transition's `when` in place, keyed on its
   from/to index) is the follow-up; it needs to agree with the model's
   `findIndex` "first match" semantics.
2. `buildGroups` mixes instance-name `cells` and stable-name `force_groups` (also
   flagged in `BUILD-NOTES-schemedit.md`); the schematic regroup inherits it.

## Three things I am least confident about

1. **The `renameInput`/`renameState` field regexes are not a full YAML-aware
   rewrite.** They match the schema's realistic flow/block and quoted/unquoted
   shapes, and the identifier-boundary cases are tested, but a pathological name
   (a state literally named `to`, an input literally named `sync`/`name`/`when`)
   could in principle confuse a field matcher. I did not test those.
2. **The name-match inferred fallback rests on an assumption I cannot verify here**
   (net name == port name in the mapped netlist) and covers only outputs/inputs,
   not the brief's cone-based example. If that assumption is wrong, the fallback
   is still *labelled inferred*, but it would be wrong rather than conservative.
3. **The rename coverage has known holes** (properties[].expr for `renameState`,
   macros[].enable and clock/reset.signal for `renameInput`). Those are either
   pre-existing or not in the brief's list, but a rename across a spec that uses
   them strands a reference silently.
