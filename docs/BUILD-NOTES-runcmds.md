# BUILD-NOTES — runcmds (Package M)

## What was the gap

The palette and the shortcuts sheet advertised `Build`, `Verify`, `Compile` and
`Estimate` (plus the palette-only `Analyse` and `Simulate`), but no `bus.register`
handled any `run.*` id. Every shortcut landed in the command bus's `onUnhandled`
path and produced a "… is not wired yet" toast. The views could already run the
tasks through their own buttons (`api.verify()` via `useRevisionedTask`); the
*advertised route* was dead.

## What I implemented

### 1. A run-request bus — `app/renderer/shell/runRequests.tsx` (new)

A context holding, per command id, a nonce plus a `pending` flag:

- `request(id)` bumps the nonce and marks the id pending, then notifies
  subscribers.
- `useRunRequest(id, fn)` fires `fn` when the nonce changes **after mount**,
  and — for the switch-then-request ordering — drains a *pending* request once
  on mount. It never fires on a plain mount.

The pending flag exists because React 18 batches the shell's
`setActiveView(…)` and `request(…)` into one render: the target view mounts
*after* the nonce has already been bumped, so a "fire on change only" hook
would silently miss the request. Draining the pending flag on mount closes the
race without a `setTimeout`.

### 2. Shell registers every `run.*` id — `Shell.tsx`

| command | action |
|---|---|
| `run.build` | switch to `packing`, `request('run.build')` |
| `run.verify` | switch to `verify`, `request('run.verify')` |
| `run.estimate` | switch to `analysis`, `request('run.estimate')` |
| `run.analyse` | switch to `analysis`, `request('run.analyse')` |
| `run.simulate` | switch to `truthtable`, `request('run.simulate')` |
| `run.compile` | runs here (no owning view), see below |
| `run.cancel` | `api.cancel` on every registered in-flight token |

Each view calls `useRunRequest(<id>, <its task's run>)`:
`BomView` → `build.run`, `VerificationPanel` → `run`,
`AnalysisView` → `estimate.run` and `analysis.run`,
`TruthTable` → `cover.run`.

### 3. `run.compile` — Shell-owned, toast-reported, cancellable

Nothing called `api.compile` before. It is implemented as a Shell handler that:

- calls `api.compile(token)` with a fresh token registered in the in-flight
  registry (so `run.cancel` can stop it mid-flight);
- on success toasts the counts the envelope carries —
  `Compiled N states, M flops (encoding encoding)`;
- on a failure envelope toasts the diagnostic's message;
- on rejection toasts `Compile cancelled` (info). `api.compile` only rejects on
  cancellation: main re-throws `CancelledError` and wraps every other failure in
  an error envelope, so the rejection path is unambiguously the cancel path.

The `Compile cancelled` toast is load-bearing for the test: without a positive
"the cancel happened" signal, asserting cancellation end-to-end is impossible
(see "Least confident" below).

### 4. `run.cancel` — a shared in-flight-token registry

`useRevisionedTask` now registers its token in a module-level `Set` while a call
is in flight and clears it on completion (success, error, re-run, or unmount —
the cancel-on-unmount behaviour is unchanged and still exercised by the
existing hook tests). `run.cancel` snapshots the set and calls `api.cancel` on
every token. Cancelling all of them is correct and simpler than tracking the
active view; one task is normally in flight.

## Decisions and guesses

- **`run.simulate` runs the truth table's `cover` (an `api.estimate`), not
  `api.simulate`.** The task mapping said "TruthTable's task", and the truth
  table's only `useRevisionedTask` is `cover` (the minimised-cover preview).
  Its divergence data comes from `simulate()` via the shared `useLinkContext`
  spine, not from a revisioned task. I wired the literal mapping rather than
  inventing a new revisioned `simulate` task, because adding one would create a
  second source of simulation data alongside the link spine. **Suspicion:**
  this may be the wrong call — "Simulate truth table" (cli `simulate`) firing
  `estimate` is a semantic mismatch worth revisiting.
- **`useRunRequest` is a no-op without `RunRequestsProvider`.** The four view
  components are unit-tested in isolation (`ApiProvider` + `ProjectProvider` +
  `SelectionProvider`, no shell), and those test files are out of my scope.
  Throwing (as `useCommandBus` does) would break them. The hook therefore
  degrades gracefully; the dedicated `runRequests.test.tsx` exercises the real
  behaviour, and the e2e spec exercises it through the real shell.
- **Compile toasts `Compile cancelled` on cancel.** Honest and informative (the
  user asked for it), and it is the only robust positive signal that
  cancellation reached the renderer. A bare "no success toast" assertion is
  racy and cannot distinguish "cancelled" from "still sleeping".

## Tests

- `app/renderer/shell/runRequests.test.tsx` (new, 5 tests): not-fire-on-mount,
  fire-on-request, no fire on a *different* id, drain-on-mount exactly once,
  no drain for an unrelated pending id.
- `app/renderer/hooks/useRevisionedTask.test.tsx` (+2 tests): token registered
  while running and cleared on completion; `run.cancel` (simulated) rejects the
  call, leaves `running`, and clears the registry.
- `app/tests/e2e/run-commands.spec.ts` (new, 2 tests): presses each `run.*`
  shortcut / palette command and asserts both the view/task effect and no
  "not wired yet" toast; and starts a slow compile, presses Escape, and asserts
  the `Compile cancelled` toast.

The cancel e2e test was verified to **fail without the change** (temporarily
removing the `run.cancel` registration makes it time out looking for
`Compile cancelled`).

## Numbers

- `.venv/bin/python -m pytest -q` — **904 pass, 5 skip** (unchanged).
- `npx tsc --noEmit -p tsconfig.json` — clean.
- `npx tsc --noEmit -p tsconfig.main.json` — clean.
- `npx vitest run` — **437 pass** (was 430; +5 run-request, +2 hook).
- `DISPLAY=:1 npx playwright test` — **52 pass, 1 skip** (the pre-existing
  `showcase-build` skip — bundled core not built; +2 run-commands).

## What I could not verify / weakest parts

1. **`run.simulate` → `estimate`** is the weakest point (see above). It is the
   literal mapping but smells wrong; flagging for review.
2. **The drain-on-mount ordering relies on React batching behaving as assumed.**
   The e2e test presses the shortcut against a *cold* view (switching from
   `spec`), which exercises exactly the batched switch+request path, and it
   passes — but this is an observation of one React version's batching, not a
   guarantee. The pending-request design is correct even if batching changes.
3. **`Compile cancelled` as an `info` toast is a UX choice**, not a
   requirement. If a reviewer wants cancellation silent, the e2e cancel test
   needs a different positive signal and should be reworked rather than left
   green.
4. The `run.cancel` handler cancels tokens but does not itself clear the
   registry; tokens are cleared when each task's promise settles. If the real
   bridge ever stopped rejecting on cancel, a cancelled token could linger —
   the unit test (`leaves running …`) pins the reject-on-cancel behaviour that
   this depends on.
