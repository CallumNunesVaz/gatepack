# Review notes — the two editing packages

Both delivered against `327e712`. Everything below was measured in this tree,
not taken from either agent's report.

## schemedit — accepted after four fixes

The package is good: an opt-in edit toggle, three edits that all land in
`design.yaml`, and an honest self-report that named two of its own defects. Four
things had to change before merge.

### 1. It wrote ABC instance names into `packing.force_groups`

`regroupToPackage` ended with

```ts
group.map((name) => stableNames[name] ?? name)
```

guarded only by an all-or-nothing `Object.keys(stableNames).length === 0` check.
A *partial* map — a packed view that does not cover every gate — fell straight
through. Built the input and ran it:

```yaml
    - [NAND2__stable_a, "$abc$148$bbb"]
```

A stable cone-hash name and an ABC instance name in one group, written with
`refusal: null`. The packer refuses that on the next build, and ABC renumbers
instance names every synthesis, so if it did not it would name a different gate.

The agent flagged this itself. **The same line exists in `BomView.tsx:112`** —
it was copied from there — so this is a pre-existing defect that the new path
inherited. Both now refuse per cell and name the offending gate. The comment
directly above the BomView original already said "Persisting the instance name
is not a lesser option"; the code just did not do it.

### 2. `setInputSync` deleted comments from the block it edited

It rebuilt the whole `inputs:` list from the model and called `setField`, which
re-serialises. Measured — toggling input `b` deleted this from input `a`:

```
  # the operator's push-button, debounced in hardware
  - {name: a, sync: true}    # MUST stay synchronised — metastability
```

A metastability note removed by editing an unrelated field, silently. Now a
line-level splice: exactly one line changes, verified by diffing line arrays.

### 3. `setTestPoints` had the same bug, latent

Same re-serialisation. It looked clean only because the agent tested against a
spec with no `test_points:` block, where it appends. Given an existing block it
destroyed the comments in it. Also now spliced line-wise.

### 4. Its "edit off does nothing" test could not fail

The test clicked a wire with edit mode off and asserted synchronously that
nothing was written. But the write path is debounced 400 ms, so the assertion
was taken before any write could have happened either way. Proven: forcing the
guard to `if (true)` left all 28 tests passing. It now waits past the debounce,
and fails when the guard is removed.

This is the failure mode the rules name — machinery that reports a status while
measuring nothing — in a test written specifically to prevent it.

## inspedit — accepted after one fix, and one correction to its own test

It could not run anything: its worktree had no `node_modules` (schemedit
symlinked the main tree's; this one did not) and `npm install` is forbidden. So
it delivered code that had never been compiled or executed. Linked and run here:

* both `tsc` configs clean, first try;
* 355 of 356 passing, the skip environmental (`core.real` needs the bundled core).

That is a strong result for unexecuted code. The single failure was real but the
diagnosis inverted the blame.

### The failing test was wrong; the implementation was right

`renames an input and follows the selection` renamed `go` → `start` in a spec
whose transitions read `when: "go"` and `when: "!go"`. The rename strands both
guards, the design goes invalid, and the Inspector refused — correctly. There is
no `renameInput` that fixes up references the way `renameState` does, and the
brief forbade adding one.

Replaced with a test that asserts the **refusal**, plus a complement that renames
an input nothing references and checks the selection follows. The complement
matters: without it the refusal test would also pass on an Inspector that
refused every rename.

### `specAnchor` is genuinely tested

The twin-guard case is real — two transitions with identical `when` strings,
resolved to lines 13 and 14 by their from/to pair. Falsified by making the
matcher `() => true`: two tests fail. The null paths are covered too, which
matters more than it looks — see `notes-provenance-ceiling.md`, where coverage
on `sequence_detector` is 0.36, so `null` is the common case.

### Scope

`MonacoEditor.tsx` was outside its listed scope. It is a reasonable extension —
the reveal has to reach Monaco — it collided with nothing, and the agent flagged
it. Accepted.

## Integration work, owned here

1. **The schematic never noticed a spec edit** (`6509426`). Fixed: it tracks
   `revision`, says so when the sheet predates the current spec, and offers the
   rebuild rather than performing it. While stale the value overlay **stops
   drawing** — a value on a stale sheet is a measurement of a netlist that no
   longer corresponds to the spec. Falsified by forcing `stale = false`.
2. **All ten `setSpecText` call sites migrated to `editSpec`** (`84d6628`), so
   the schematic and the inspector — which sit in adjacent panes and edit the
   same file — cannot discard each other's edits.
3. The two packages compose: zero file overlap, 388 vitest, 24 playwright.

## What is still not done

* No `renameInput`. Renaming a referenced input is refused rather than
  propagated; `renameState` shows the shape a fix would take.
* The reveal control does not switch tabs within the spec view (inspedit's own
  note 3).
* The regroup refusal for an absent packed view is unit-tested but not reachable
  by a UI click, because an empty packed view offers no drop target
  (schemedit's own note 1).
