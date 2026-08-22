# Finding — the schematic never notices a spec edit

Measured in the main tree at `327e712`, while the two editing packages were
running, so it is an independent "before" rather than a restatement of either
agent's result.

## The defect

`renderer/views/Schematic.tsx` contains **zero** references to `revision`. It
fetches `mappedNetlist()`, `packedNetlist()` and `analyse()` in effects keyed on
`[api]` alone, so they run once at mount and never again.

Every other expensive view is revisioned. `BomView`, `TruthTable`,
`AnalysisView` and `VerificationPanel` all take
`useRevisionedTask(revision, …)`, whose contract is explicit: *"a stale result
against edited source is a correctness bug, so the UI must never present one as
live."* The schematic is the one view outside that rule.

## The measurement

A probe rendered the view against `FakeGatepack`, waited for the layout, edited
the spec through `setSpecText` (the same path every editing view uses), and
counted bridge calls:

```
mappedNetlist calls: before=2 after=2
stale indicator present: false
```

No refetch, and nothing anywhere in the rendered output tells the user the sheet
no longer matches their design. It keeps drawing the netlist it loaded at mount,
indefinitely.

## Why it matters more now than it did yesterday

Until this session the schematic was read-only, so the window in which it could
mislead was small. Two things changed it:

1. The §24.2 value overlay now draws *live signal values* on that netlist. A
   stale sheet does not merely show old topology — it shows confidently
   coloured 0/1 values for a design that no longer exists.
2. `deepseek/schemedit` makes the schematic itself an editing surface. Toggling
   `sync` on an input from the schematic changes the spec, changes the
   synchroniser the next build emits, and leaves the schematic showing the old
   one with no indication. The view would be the only one that does not respond
   to its own edits.

This is the failure mode the repo keeps hitting — machinery presenting a status
it did not re-measure — in the view that is now the most visual.

## What the fix is not

Not an auto-rebuild. `mappedNetlist()` reads `build/mapped.json` off disk, so
after an edit that file is stale too; refetching alone would re-read the same
stale artefact and *look* fresher while being exactly as wrong. Synthesis is
seconds, and no other view auto-runs its expensive task either — `AnalysisView`
is the only one that calls `run()` on mount, and even it does not re-run on
every keystroke.

The honest shape, matching the rest of the application:

* Take `revision` from `useProject()`.
* When it changes, mark the sheet stale and **say so** — the netlist on screen
  was built from an earlier version of the spec.
* Offer the rebuild explicitly rather than performing it; a build is the user's
  call, as it is everywhere else.
* While stale, the value overlay must stop claiming measured values, because it
  is evaluating a netlist that no longer corresponds to the spec.

## Ownership

`Schematic.tsx` is inside `deepseek/schemedit`'s scope, so this was deliberately
**not** added to that brief mid-run and must not be fixed in parallel with it.
It is integration work for whoever merges that package. The probe above is the
regression test to keep, adapted into `Schematic.test.tsx`.
