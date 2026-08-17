# Handoff notes — failed check carries its `detail` to the GUI

## What changed

The core already emits a failed/bounded check's reason as `detail` in
`gatepack/api.py::check_payload` (and `skippedReason` for `not_run`). The IPC
seam dropped `detail`; this change carries it through.

- `app/shared/api.ts` — `Check` gains an optional `detail?: string`.
- `app/main/envelope.cts` — `CheckSchema` gains `detail: z.string().optional()`.
  Optional, so an older core that omits it still validates (per the brief).
- `app/renderer/views/VerificationPanel.tsx` — `CheckRow` now renders
  `check.detail` in a full-width `<pre data-testid="check-detail">` below the
  status row, visible without any interaction, and passes `detail` through to
  `StatusBadge`. The `<pre>` is styled inline (`white-space: pre-wrap`,
  `overflow-wrap/word-break: break-word`, `max-height` + `overflow: auto`) so a
  long sby stack wraps and scrolls inside the row instead of blowing out the
  layout. `views.css` was left untouched (off-limits; another engineer is in
  it), hence inline styles.
- `app/renderer/components/StatusBadge.tsx` — new optional `detail` prop,
  surfaced in the badge tooltip (`failed: <detail>`) mirroring the existing
  `skippedReason` handling.

## Tests added / changed

- `app/main/envelope.test.ts` (+2): `CheckSchema` accepts and preserves
  `detail`; a `verify` envelope round-trips through `parseEnvelope` with
  `VerifyResultSchema` and keeps `detail`.
- `app/renderer/components/StatusBadge.test.tsx` (+1): a failed badge carries
  its `detail` in the tooltip.
- `app/renderer/views/VerificationPanel.test.tsx` (+1): a failed check with a
  `detail` renders the reason with no interaction.
- `app/renderer/views/spec/fsmRouting.test.ts` (+6, new): `nearestSides`
  right/left/above/below, target-always-opposite-source, and the diagonal
  half-extent case.

No existing assertion asserted `detail` was absent, so none had to change.

## What I guessed / flagged

**The brief's diagonal example is wrong for the helper as it stands.** The brief
says a target "60px right and 30px down comes off the right face, not the
bottom". The helper actually returns `{ source: 'b', target: 't' }` for that
input: it compares `|dx|/(NODE_W/2)` vs `|dy|/(NODE_H/2)`, and with
`NODE_W = 112`, `NODE_H = 40` that is `60/56 ≈ 1.07` vs `30/20 = 1.5`, so the
vertical axis dominates and the bottom face wins. The code comment in
`FsmGraph.tsx` states this exact intent ("does not get an edge off its long face
just because dx happens to be numerically larger"), so the code is internally
consistent and the brief's example is the error.

I tested the helper as it stands (per the brief and the "do not touch
`FsmGraph.tsx`" rule): the diagonal test asserts `{60,20} → right` and
`{60,30} → bottom`. If the maintainer wants the `{60,30} → right` behaviour, the
helper's comparison is what must change, not the test.

## Not verified / unfinished

- The long-text wrap/scroll behaviour is only exercised by the inline CSS; no
  visual/layout assertion (jsdom does not lay out). The test pins that the full
  text renders, not that it wraps.
- Only the TypeScript/Electron side was touched; the Python core already emitted
  `detail` and was left as-is.

## Test results

- Before: 263 passed, 1 skipped (264 total).
- After: 273 passed, 1 skipped (274 total) — 10 new tests, none weakened.
- `npx tsc --noEmit -p tsconfig.json` clean; `npx tsc -p tsconfig.main.json --noEmit`
  clean (envelope.cts is in the main project).
