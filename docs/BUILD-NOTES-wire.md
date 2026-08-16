# BUILD-NOTES — wire (panels + three renderer defects)

Scope: `app/renderer/shell/**`, `app/renderer/panels/**`,
`app/renderer/state/**`, `app/renderer/keys/registry.test.ts`,
`app/renderer/views/AnalysisView.tsx` (+ test), `app/tests/e2e/status-bar.spec.ts`.

## What I implemented

### Defect 1 — the six panels are now reachable

- `app/renderer/panels/index.ts` now exports `PANEL_COMMANDS`: a single table
  mapping each command id (`inspect.doctor`, `inspect.provenance`,
  `inspect.mappedNetlist`, `inspect.packedNetlist`, `inspect.library`,
  `project.examples`) to its title and component. It also exports
  `panelCommandById`.
- `app/renderer/shell/PanelHost.tsx` (new) registers a handler for every
  `PANEL_COMMANDS` entry on the command bus and mounts the chosen panel in a
  modal dialog. `Shell.tsx` renders it after the palette/shortcuts sheet.
- **Presentation decision (dialog, not a tab or docked pane):** the shell
  already has a modal vocabulary (palette, shortcuts sheet) with
  Escape-dismiss + focus-restore; the right inspector already means "selection
  context" and repurposing it would make two different surfaces share a slot;
  the panels are tall (netlists, tables) and a dialog gives them room without
  reshuffling the six-view grid. It is keyboard-dismissible (Escape, close
  button) and returns focus to the invoking element.
- `app/renderer/panels/panels.css` gained `.gp-panel-host-*` (tokens only).

### Registry test made sufficient

- `registry.test.ts` gained `resolves every panel command to a mounted handler`
  — for every `inspect.*` command and `project.examples`, there must be a
  `PANEL_COMMANDS` entry, and the reverse (no handler entry without a registry
  entry). `shell/PanelHost.test.tsx` (companion) proves the entries are
  actually registered and that dispatching opens a panel rather than reporting
  "not wired". Together: a cli-tagged panel command that dispatches to nothing
  fails the suite.

### Defect 2 — design name no longer goes stale

- `project.tsx` re-reads the spec inside `onProjectChanged` (clearing any
  pending write, which belonged to the previous project), so `model.name` — and
  `status-design` — follow `openProjectPath`. The initial mount load does *not*
  bump `revision` (see "Least confident" below); project switches and external
  edits do, so revisioned results go stale.

### Defect 3 — `onFileChanged` is now consumed

- `project.tsx` subscribes to `onFileChanged`. **Policy (deliberate):** if a
  debounced write is pending (`pendingRef !== null`), the external change does
  NOT overwrite the editor — local edits are kept and `specStale` is set.
  Otherwise the on-disk content is authoritative and the spec is re-read.
  `specStale` is exposed in the context and surfaced as a `status-stale` item
  in the status bar. It clears on the next authoritative apply (fresh local
  edit, or a re-read with nothing pending). Both directions are tested in
  `state/project.test.tsx`.

### Defect 4 — AnalysisView error state

- `AnalysisView.tsx` renders `estimate-error` and `analysis-error` notes
  (`role="alert"`, the same `error-note` treatment as Verification) for a
  failing `estimate()`/`analyse()`, naming the tool via the core's message.
  Tested with a seeded `ok:false` envelope.

### e2e

- `status-bar.spec.ts` restored the strict flow: open project A, then project B
  in one session, asserting the design name follows. (Previously downgraded to
  the reopen-on-launch path — see docs/BUILD-NOTES-e2e.md finding #2.)

## Fail-verification (each new test made to go red, then restored)

- Removed `project.examples` from `PANEL_COMMANDS` → registry test red:
  `project.examples must map to a mounted panel handler`.
- Made `PanelHost` register no-op handlers (`() => {}`) → 3 PanelHost tests red:
  `Unable to find an element by: [data-testid="doctor-view"]` (the handler was
  registered but dispatched to nothing — the exact defect).
- Removed the `readSpecFromDisk(true)` re-read from `onProjectChanged` →
  `project.test.tsx` red: `Expected beta, Received alpha`.
- Removed the stale policy from `onFileChanged` → red: `Expected true, Received
  false` on `specStale`.
- Removed the error blocks from `AnalysisView` → both error tests red:
  `Unable to find an element by: [data-testid="estimate-error"]`.
- The e2e `status-bar` strict test was already observed red against the buggy
  renderer by the previous agent ("pelican" vs "myproj", BUILD-NOTES-e2e.md #2).

## Test counts

- Renderer+main vitest: 252 → **262 passed** (42 files). 3 new files:
  `shell/PanelHost.test.tsx` (4), `state/project.test.tsx` (3), plus 2 added in
  `AnalysisView.test.tsx` and 1 added in `registry.test.ts`.
- `npx tsc --noEmit -p tsconfig.json` and `-p tsconfig.main.json`: clean.
- Playwright e2e: **19 passed** (was 12 at the e2e agent's baseline; the suite
  had grown), including the restored `status-bar` strict test.
- Python suite untouched (557 pass / 5 skip at baseline, not re-run — no
  `gatepack/**` changes).

## Guesses / placeholders

- The `specStale` flag is surfaced only in the status bar (`status-stale`),
  which I own; the ideal place is a banner in the SpecEditor (owned by the
  views agent). The state/logic is testable regardless.
- The "unsaved local edits" boundary is "a debounced write is still pending",
  not "project.dirty" — the latter lives in main and I can't watch it from the
  renderer. The debounce window (400 ms) is the only genuinely unsaved window
  in this auto-save design.

## Least confident

1. **`PanelHost` focus restoration relies on sibling effect ordering.** When a
   panel opens via the palette, the palette's close-effect restores focus to
   the invoking element and the panel's open-effect captures `document.activeElement`
   afterward. I placed `PanelHost` after the palette in the shell so its effect
   runs later, but this is an implicit ordering guarantee, not an explicit one.
   The direct-dispatch path (shortcuts, tests) is deterministic; the palette
   path is the fragile one.
2. **`readSpecFromDisk(false)` (no revision bump) on mount** is a deliberate
   deviation from "every spec change bumps revision". Bumping there races a task
   started just after mount (it cancels an in-flight `build` — I saw `BomView`
   go flaky once before I added the flag). The distinction is documented in the
   code but it is subtle: initial load is not a "change", project switch/edit is.
3. **A pending debounced write still auto-saves over the external change.**
   When `specStale` is set because of an external edit, the user's debounced
   write (400 ms) still flushes and overwrites the external change on disk. The
   flag warns, but we do not *prevent* the clobber. Blocking auto-save while
   stale would be safer but changes the existing save contract; I left it.

## Suspicions I could not reach

- `run.*` commands (`run.compile`/`build`/`verify`/`estimate`/`simulate`/
  `analyse`) and `project.open`/`save`/`saveAs`/`close` also carry no command
  handler, so dispatching them from the palette still shows "not wired". They
  are reached through view-internal buttons today, but the palette entries lie
  the same way the six panels did. This is out of my scope and worth a follow-up.
- The `doctor-panel.spec.ts` note ("once the panels are wired, the UI assertion
  belongs here") is now unblocked, but that file is outside my owned scope.
