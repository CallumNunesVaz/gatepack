# BUILD-NOTES — speccomments (Package N: dragging one edge deletes the comments)

## What this package fixed

`applyTopLevelEdit(text, key, transform)` re-serialises a whole top-level block
from a parsed value, so any edit inside a list regenerated the block from
scratch: every comment in it vanished, quoting was normalised (`"din"` -> `din`)
and hand alignment collapsed. The spec editor's rename path had already been
fixed with line splicing; the FSM graph and the structured form had not.

Measured on the bundled `examples/edge_detector/design.yaml`: adding one
transition through the old path deleted both teaching comments inside
`transitions`, unquoted `din`, and flattened the aligned `from`/`to` columns.

## What I implemented

### `app/renderer/design/model.ts` (new exported functions)

- `setTransitionFrom` / `setTransitionTo` — the `from`/`to` analogues of the
  existing `setTransitionWhen`, thin wrappers over `setItemField` (ED1028/ED1029).
- `setInputName` / `setOutputName` / `setPropertyName` / `setPropertyKind` —
  the same splice for the form's name/kind fields (ED1032–ED1035).
- `appendListItem(text, key, item)` — appends one item to a top-level list,
  spliced so only the end of the block changes. Matches the surrounding style:
  a flow sequence (`states: [S0, PULSE]`) gets an inline item; a block list of
  flow mappings gets another `- {…}`; a block list of block mappings gets
  another `- key: …` block; an empty/absent block becomes a one-item block
  (absent key uses the existing `setField` upsert, which is safe because there
  is nothing to destroy).
- `removeListItem(text, key, index)` — removes one item's own lines. Handles
  block lists and flow sequences. Refuses (byte-identical + diagnostic) on
  out-of-range index, missing key, or a non-list value.
- Private helpers: `inlineScalar`, `renderListItemLines`,
  `splitTopLevelCommas`, `isAttachedComment`.

Both append and remove re-parse the result and, if it no longer parses, return
the *original* text with the parse diagnostic rather than handing back broken
YAML (same guard as `setTestPoints`/`setInputSync`).

### `app/renderer/views/spec/FsmGraph.tsx`

`updateEdge` now splices the touched `from`/`to`/`when` fields;
`addTransition` and `addState` use `appendListItem`. No edge deletion was added
(none exists, and it is out of scope).

### `app/renderer/views/spec/StructuredForm.tsx`

`×` buttons use `removeListItem`; `+` buttons use `appendListItem`; input/output
name edits use `setInputName`/`setOutputName`; the sync checkbox uses the
already-splice-based `setInputSync`; property name/kind/expr use
`setPropertyName`/`setPropertyKind`/`setPropertyExpr`.

## Judgement calls (the ones the brief asked me to record)

1. **Comment-attachment rule for removal.** A comment line sitting *directly*
   above an item, with no blank line between, is treated as that item's
   annotation and removed with it; a comment separated by a blank line stays.
   A single blank line is the only boundary I reason about. This means the
   `# S0: …` comment in `edge_detector` — which actually *describes both* S0
   transitions — is deleted when the first of them is removed. That is a
   deliberate, documented simplification, not an oversight. A comment that sits
   at the very top of the block *and* is glued to the first item (no blank line)
   still goes with that item; "at the top of the block stays" is only realised
   when the header comment is separated from the items by a blank line.

2. **Quoting of new items.** `inlineScalar` quotes only what would not
   round-trip as a plain scalar (empty, `true/false/null/~`, numeric-looking,
   or anything outside `[A-Za-z_][A-Za-z0-9_./-]*`). So the new transition
   `when: "1"` is quoted (matches the example's quoted-`when` style, and avoids
   `1` parsing as an integer), while `from`/`to` state names stay plain. A
   hypothetical plain guard like `when: din` would come out unquoted — the
   bundled example never hits this because `addTransition` hardcodes `when: "1"`.

3. **Field splices always double-quote.** `setTransitionFrom`/`setTransitionTo`
   and the name setters go through `setItemField`, which quotes the new value
   (`from: "S1"`). That is the same treatment `setTransitionWhen` already has;
   it intentionally does *not* preserve the "was this field quoted before?"
   style that `renameState` does. The edited line is allowed to change; every
   other line stays byte-identical.

4. **Property-expression clearing still rewrites the block.** `setPropertyExpr`
   sets a value, but clearing an expression *removes the key*, which a value
   splice cannot express. That one case still re-serialises `properties`
   (losing its comments), exactly as `Inspector.tsx` already documents. It is
   narrower than before and is noted rather than hidden.

## What I could not verify

- No Yosys here, and none is needed: this is pure text editing. The real-core
  e2e run (docker `gatepack-toolchain:m6`) still passes, including
  `edge_detector` open -> compile -> estimate -> verify -> build.

## What is weakest

- **`transitions:  # comment` with no items** — the parser reads the value as
  empty, so the first append splices a newline+item after the colon and the
  inline comment ends up as a *trailing* comment on the first item (preserved,
  but reflowed). Not present in any bundled example.
- **Flow-sequence removal re-joins with `, `**, so `[A,B,C]` becomes `[A, B]`.
  No comments can live inside a flow sequence, so nothing is lost, but spacing
  is normalised on that one line. No editor currently removes flow-sequence
  items (`states` is read-only in the form), so this path is exercised by tests
  only.
- **`renderListItemLines` on an empty dict item** would throw (`keys[0]` is
  undefined). Every caller passes a non-empty dict; it is a caller-contract
  assumption, not a guarded failure.

## Tests

`app/renderer/design/model.test.ts` gained a block that pins the real
`examples/edge_detector/design.yaml` (copied verbatim — verified byte-identical
against the file at write time) and asserts, for add-transition /
change-from/to/when / delete-transition / add-state / add-input, that the
block's comments survive verbatim, that every non-edited line is byte-identical
(a common prefix/suffix line diff is empty except for the edited region), and
that the result re-parses with no error diagnostics. A "canary" test documents
that the old `applyTopLevelEdit` path drops the comments and normalises quoting
and alignment, so a revert is caught. Edge cases (absent key, empty block,
block-list `states` with comments, flow-sequence removal, refusal on empty /
missing / non-list, and a splice that would not re-parse) are each covered.
