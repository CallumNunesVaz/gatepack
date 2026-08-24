# BUILD-NOTES — Package O (build outputs are written, never offered)

Closes the last boundary in `docs/MILESTONE-AUDIT.md` [GUI-1]: the build wrote
`bom.csv`/`netlist.net`/`report.md` into `.gatepack/out` and the GUI offered no
route to them. `gatepack build` already did its job; this package adds the two
routes out of it — reveal and export — and pins them.

## What was implemented

Two new bridge methods, exactly as specified in the delegation (no redesign —
the shape was not wrong):

- `revealOutputs(): Envelope<{ path: string }>` — opens `.gatepack/out` in the
  OS file manager, or errors when there is nothing to reveal.
- `exportOutputs(): Envelope<{ path: string; files: string[] }>` — copies the
  manufacturing artefacts into a directory the user picks in a native dialog.

The full chain, following the `newProject` shape (`session.cts` → `ipc.cts` →
`index.cts` → `preload/index.cts` → `shared/api.ts`):

- `api.ts`: the two members added verbatim (the one allowed edit to this file).
- `session.cts`: `SessionManager.revealOutputs()` / `exportOutputs(destination)`.
- `ipc.cts`: `gatepack:revealOutputs` + `gatepack:exportOutputs` (the latter via
  `exportViaDialog`, the twin of `newViaDialog`).
- `preload/index.cts`: both exposed on `window.gatepack`.
- `main/index.cts`: `Reveal Outputs` / `Export Outputs…` in the File menu next
  to Save As, plus the injected shell seam.
- `renderer/keys/registry.ts`: `project.revealOutputs` / `project.exportOutputs`
  in the `project` group so they appear in the palette.
- `renderer/shell/Shell.tsx`: handlers registered (see "the palette lie" below).
- `renderer/bridge/fake.ts`: both implemented, with call tracking.
- `tests/e2e/app.spec.ts`: the two names added to the pinned bridge surface.
- New unit tests: `app/main/session-outputs.test.ts` (10 tests).

## Decisions I made (the reviewer asked for each)

### `openPath` on the directory, not `showItemInFolder`

Chose `shell.openPath(outDir)` over `showItemInFolder`. `showItemInFolder`
takes a *file*, opens its parent, and selects it — the user still has to pick
the file out afterwards. `openPath` on the directory opens the folder directly,
which is what "reach the files" means; the three deliverables sit side by side.
`openPath` also resolves to a **string** (empty on success, an error message on
failure) rather than rejecting, so the return value is checked and an empty
result is never reported as `ok` — that check is pinned by a test.

### Which files to copy

Exactly `bom.csv`, `netlist.net`, `report.md` — the three things a person hands
to a fabricator. The intermediates are deliberately **not** copied:

| file | why excluded |
|---|---|
| `mapped.json`, `premap.json`, `cells.lib`, `yosys.ys`, `generated.v`, `mapped.v` | the core's own scratch for `analyse` / `provenance` / `mappedNetlist`; re-runnable, not deliverables |
| `refdes.json` | reference designators are already inside `netlist.net` |
| `netlist.unpacked.net` | the pre-packing netlist; the manufacturable one is `netlist.net` |

The weakest of these is `netlist.unpacked.net`: a case exists that a fabricator
wanting the *unpacked* netlist should get it too. I excluded it because the
task named three files and "the netlist" handed on is the packed one — but it is
the judgment call I am least confident about, and it is trivial to add later by
extending `EXPORT_ARTEFACTS`.

### Overwrite policy: refuse, whole-export

Chose **refuse** (`GP4115`) over suffix or overwrite. Suffixing silently
renames a file the user may then not notice; overwriting silently destroys a
file the user already had. Refusing is deterministic, names the conflicts, and
matches the project's existing refusal (`project new` refuses an existing
`design.yaml`). It is all-or-nothing: if any of the three targets exists, none
are written. Pinned by a test that pre-creates `bom.csv` and asserts the other
two are not copied either.

## The one thing I was told to fix, fixed

`commands.tsx` says a reachable command that does nothing is a lie, and another
package in this branch is fixing exactly that for `run.*`. Both new palette
commands are **wired** in `Shell.tsx`, not just listed in the registry:

- `project.revealOutputs` → `api.revealOutputs()`; error toasted.
- `project.exportOutputs` → `api.exportOutputs()`; success toasted with the file
  count and destination; `GP4201` (cancelled) swallowed rather than toasted,
  because cancelling a dialog is the user changing their mind, not an error.

The palette titles are `Reveal outputs` / `Export outputs…` (matching the File
menu) **without** the word "build". Deliberate: the palette filter and the
`CommandPalette`/`filter` tests pin that typing `build` ranks `run.build` first,
and "Reveal **build** outputs" would have stolen that top slot (title match +
the `project` group sorts before `run`).

## Error surfacing

The File-menu path is fire-and-forget like every other menu action, but the
*refusal* is not silent: `revealOutputsMenu`/`exportOutputsDialog` surface an
`ok: false` result in a native `dialog.showErrorBox` rather than doing nothing.
This matters because a menu click that opens no folder and says nothing is the
very "small lie" the package exists to avoid.

## GP codes

`envelope.cts` types codes as free strings and registers only the `GP9xxx`
bridge codes, so there is no registry to update. Chosen to read as part of the
existing family (`GP41xx` project, `GP42xx` cancelled/refused):

- `GP4200` — reused for "no project open" (same meaning as in `invoke`).
- `GP4113` — nothing built / a required artefact is missing; message says "run a
  build first", not merely what went wrong.
- `GP4114` — `shell.openPath` returned a failure string.
- `GP4115` — overwrite refusal.
- `GP4116` — copy failure.
- `GP4201` — reused for a cancelled export dialog (same shape as cancelled open).

## The §5.2 boundary

Writing outside the project root is a genuine widening, acceptable only because
a **native dialog** picked the destination. The renderer passes no path:
`exportOutputs()` takes no argument on the bridge, and the destination reaches
`session.exportOutputs(destination)` only from `dialog.showOpenDialog`. No
renderer-supplied destination is ever accepted. Recorded on the pinned bridge
surface in `app.spec.ts` with the same kind of comment `newProject` carries.

## What I could not verify

- The actual OS file-manager reveal and the native export dialog are not driven
  by any automated test: clicking them would spawn a file manager / native
  dialog in a headless run. The reveal seam and the copy logic are unit-tested
  at `SessionManager`; the dialog glue (`exportViaDialog`, the menu items) is
  untested beyond existing (it mirrors `newViaDialog`, which is likewise only
  exercised for the "cancelled" shape indirectly).
- The export refusal is not atomic against a TOCTOU race (a file dropped into
  the destination between the conflict check and the copy). Accepted because
  the destination was just picked by the user in a dialog and the window is
  minuscule; noted, not fixed.

## Test counts (measured, not asserted)

| suite | before | after |
|---|---|---|
| `pytest -q` | 904 pass / 5 skip | 904 pass / 5 skip (unchanged) |
| `npx vitest run` | 454 | **464** (+10: `session-outputs.test.ts`) |
| `npx tsc --noEmit -p tsconfig.json` | clean | clean |
| `npx tsc --noEmit -p tsconfig.main.json` | clean | clean |
| `DISPLAY=:1 npx playwright test` | 53 | 53 (incl. the two docker specs) |
| `contract-commands.spec.ts` | 4 pass | 4 pass (unaffected — reveal/export invoke no core subcommand) |
