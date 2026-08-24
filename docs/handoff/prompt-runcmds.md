# Package M — the four things the tool is for are dead on the keyboard

Read `docs/handoff/delegation-rules.md` first. Every rule there applies.

## The gap, measured

The command palette and the shortcuts sheet advertise Build, Verify, Compile and
Estimate. I pressed each shortcut in the running application and captured the
toast stack:

```
Ctrl+B        -> "Build" is not wired yet
Ctrl+E        -> "Estimate viability" is not wired yet
Ctrl+Shift+C  -> "Compile" is not wired yet
Ctrl+Shift+V  -> "Verify" is not wired yet
Ctrl+S        -> (no toast; the Electron File menu accelerator handles it)
Ctrl+3        -> (no toast; view switch works)
```

The features themselves work — the views call `api.verify()` and friends
directly through `useRevisionedTask`. It is the advertised route to them that
does nothing. `app/renderer/shell/commands.tsx` states the rule this breaks:

> A reachable command that does nothing is a lie; a reachable command that says
> so is a promise.

The toast keeps the second half of that promise, which is why this is a gap and
not a disaster. But these are the four things the tool is for.

Every `run.*` id is in `app/renderer/keys/registry.ts` and **no `bus.register`
call anywhere in the renderer handles any of them**. Handlers exist only for:

- `view.*` — `VIEWS.map(...)` in `Shell.tsx`
- `inspect.*` and `project.examples` — `PANEL_COMMANDS` in `PanelHost.tsx`
- `app.*` and `project.new` — `Shell.tsx`

`project.open/save/saveAs/close` are also unregistered, but they are **not in
scope**: the Electron File menu owns those accelerators and they work. Leave
them alone.

## The architecture to implement

A command must work from any view, and the code that can run a task lives inside
the view that owns it. So the handler switches to the owning view and *requests*
a run; the view performs it.

### 1. A run-request bus — `app/renderer/shell/runRequests.tsx` (new)

A context holding a nonce per command id:

```ts
request(id: string): void            // bumps the nonce for `id`
useRunRequest(id: string, fn: () => void): void   // fires fn when it changes
```

`useRunRequest` must **not** fire on mount — only on a change after mount.
Switching to a view must not be indistinguishable from asking it to run, or
every view switch silently launches a toolchain job.

Provide it from the same place the command bus is provided.

### 2. Shell registers the `run.*` ids

Each handler switches to the owning view, then calls `request(id)`:

| command | owning view | what runs |
|---|---|---|
| `run.build` | `packing` | `BomView`'s build task |
| `run.verify` | `verify` | `VerificationPanel`'s verify task |
| `run.estimate` | `analysis` | `AnalysisView`'s estimate task |
| `run.analyse` | `analysis` | `AnalysisView`'s analyse task |
| `run.simulate` | `truthtable` | see the correction below |

**CORRECTION, found after this brief was issued.** The table above is wrong
about `run.simulate`, and the error is worth stating precisely because it is the
shape of mistake that produces a command which appears to work:

`TruthTable` does **not** own a simulate task. Its `useRevisionedTask` runs
`api.estimate`. The simulation data reaches it as `ctx.simulation` from
`useLinkContext()`, which calls `api.simulate()` **once in a mount effect with
no refresh path**. So wiring `run.simulate` to TruthTable's existing task would
re-run *estimate* while the command said "Simulate truth table" — a command that
reports success having done something else.

Doing it properly means giving `useLinkContext` a refresh, and
`app/renderer/selection/useLinkContext.ts` is **not in the file scope below**.
Either extend the scope to that one file and say so in the build notes, or leave
`run.simulate` unwired and record why. Do not wire it to the estimate task.

The view is switched **before** the request so the target view is mounted and
subscribed when the nonce changes. If that ordering turns out not to hold in
React's batching, say so in the build notes and solve it explicitly (a pending
request the view drains on mount is fine) rather than adding a `setTimeout`.

### 3. `run.compile` has no owner — give it one

Nothing in the renderer calls `api.compile` at all. Its registry hint says
"Front end only: specification to Verilog", which is a genuinely useful thing —
a fast check without a full verify — so implement that rather than deleting the
command:

- Call `api.compile()`.
- On success, toast the counts the envelope carries (`stateCount`, `flopCount`,
  `encoding`) — a compile that reports nothing is indistinguishable from one
  that did not run.
- On failure, toast the diagnostic's message.

Do not delete `run.compile` from the registry: `registry.test.ts` asserts every
CLI subcommand is reachable through some command's `cli` tag, and `compile` is
only reachable through this one.

### 4. `run.cancel` (Escape)

`useRevisionedTask` holds the in-flight token in a ref and already cancels on
unmount and on re-run. Add a small shared registry of in-flight tokens that the
hook registers into and clears on completion, and have `run.cancel` call
`api.cancel` on every registered token. One task is normally in flight;
cancelling all of them is correct and simpler than tracking which view is
active.

If you conclude a token registry is the wrong shape, implement what you think is
right and justify it in the build notes — but `run.cancel` must actually cancel,
and there must be a test that fails if it does not.

## Acceptance criteria

1. **A test that presses the keys.** Extend or add an e2e spec that, for each of
   `run.build`, `run.verify`, `run.estimate`, `run.analyse`, `run.simulate`,
   `run.compile`, presses its shortcut (or dispatches it through the palette
   where it has no key) and asserts **no toast matching `is not wired yet`**
   appears. Assert the *effect* too, not only the absence of the toast — the
   view became active, or the task reached `running`/`success`. A test that only
   checks for the absence of a toast passes if you delete the toast.
2. **`run.cancel` cancels.** Start a task, press Escape, and assert the task
   left `running`. Build the case that fails without your change and keep it.
3. `useRunRequest` does not fire on mount — test it.
4. Baselines, all of which must still pass:
   `.venv/bin/python -m pytest -q` (**904 pass, 5 skip**);
   from `app/`: `npx tsc --noEmit -p tsconfig.json`,
   `npx tsc --noEmit -p tsconfig.main.json`, `npx vitest run` (**430 pass**),
   and after `npm run build`, `DISPLAY=:1 npx playwright test` (**51 pass**).

   Note: `app/tests/e2e/examples-end-to-end.spec.ts` and
   `schematic-pointer.spec.ts` need the `gatepack-toolchain:m6` docker image and
   take about a minute; they are expected to pass, not skip.

## File scope

Yours: `app/renderer/shell/runRequests.tsx` (new, + its test),
`app/renderer/shell/Shell.tsx`, `app/renderer/hooks/useRevisionedTask.ts`,
`app/renderer/views/VerificationPanel.tsx`, `app/renderer/views/BomView.tsx`,
`app/renderer/views/AnalysisView.tsx`, `app/renderer/views/TruthTable.tsx`,
and one new e2e spec.

Off-limits: everything else. In particular `app/shared/api.ts` (the IPC
contract), `app/renderer/keys/registry.ts` (do not add or remove commands —
wire the ones that are there), anything under `gatepack/`, and every file in
the "do not edit" list in the rules.

## One thing to be careful about

`useRevisionedTask` is used by several views and its cancel-on-unmount behaviour
is load-bearing: a view that unmounts mid-run must still cancel. Do not break
that while adding the token registry. There are existing tests for the hook —
read them before changing it.

Write `docs/BUILD-NOTES-runcmds.md`.
