# Finding — the packed view already carries the instance → stable mapping

Recorded while `deepseek/schemedit` was running, as a review point for that
package. It corrects an assumption in its own brief.

## The brief's assumption

`prompt-schemedit.md` told the package to reuse `BomView::handleRegroup`'s
guard, which reads the instance → stable map from a **build result**:

```ts
const stable = build.state.status === 'success' ? build.state.data.stableCellNames : {};
if (Object.keys(stable).length === 0) { /* refuse */ }
```

That is right for `BomView`, which already runs `useRevisionedTask(revision,
api.build)`. It is the wrong shape for the schematic, which runs no build task —
following it literally would mean either adding a build task to the schematic
(so opening the view kicks off synthesis) or refusing every regroup until some
*other* view happens to have built.

## What is actually available

`gatepack/api.py::packed_view_payload` builds the two arrays like this:

```python
"cells": list(group.cells),                                     # STABLE names
"instanceCells": [stable_names.to_instance(s) for s in group.cells],
```

`instanceCells[i]` is *derived from* `cells[i]` by a single reverse lookup, so
the two arrays are **index-parallel by construction**, not incidentally. The
schematic already fetches `packedNetlist()` for its packed layer, so it already
holds a complete instance → stable mapping:

```
instanceCells[i]  ->  cells[i]
```

No build task, no second source, and no dependence on another view having run.
`CellNames.to_instance` raises `KeyError` on an unknown stable name rather than
returning a guess, so a package whose cells are not in the map cannot be built
at all — the payload either has the pair or does not exist.

## What this does not remove

The *reason* for the guard is unchanged and still the point: `force_groups` is
resolved against stable names, ABC instance names are renumbered by every
synthesis, and writing one is refused by the packer on the next build — or worse,
would name a different gate. Four defects have come from conflating them.

So the refusal still has to exist; it just has a different trigger. Refuse when
the packed view is **absent or stale** (no build has produced one, or the
`packedError` path fired), not when a build *result* is missing. A cell in the
mapped netlist that appears in no package has no stable name available and must
also be refused rather than written as its instance name.

## Review position

Either implementation is acceptable if it refuses correctly. Reject any that:

* writes an ABC instance name into `packing.force_groups` under any
  circumstance;
* derives the stable name by string manipulation of the instance name rather
  than by the mapping (they are unrelated name spaces — a cone hash is not a
  transformation of `$abc$148$…`);
* assumes `cells` and `instanceCells` correspond *by name* rather than by index;
* silently does nothing when the mapping is unavailable, instead of saying so.

The index correspondence above is the licence for the fourth point being the
only safe read of the pair — it is guaranteed by the producer, and this note is
the evidence for it.
