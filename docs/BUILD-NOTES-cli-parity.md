# BUILD-NOTES — CLI parity (panels + IPC)

Scope: make everything the CLI does reachable from the GUI, and make the
missing subcommands (`lib`, `examples`) real, not registry entries whose panels
do nothing.

## What I implemented

**Core (`gatepack/`)**
- `gatepack lib check --json` — emits the §C2 validation report
  (`LibraryCheckResult`): per-part citation status, eligibility/exclusion
  reason, `refsPresent`, `missingCitations`, counts. Deliberately a *report*,
  never a gate: a missing refs file or missing citations are findings in the
  payload, not an `ok:false` envelope, so the GUI can show *why* validation
  failed. Only a malformed CSV is a hard `ok:false` (GP1004). The human
  (non-`--json`) path keeps its exit-1 gating unchanged.
- `gatepack examples list --json` — emits `{ examples: [{name, summary,
  isShowcase}] }`.
- Payload builders `library_check_payload` / `library_part_payload` /
  `examples_list_payload` in `gatepack/api.py`.

**IPC contract (`app/shared/api.ts`)**
- Added `LibraryPart`, `LibraryCheckResult`, `ExamplesList` and three methods on
  `GatepackApi`: `checkLibrary(path)`, `listExamples()`, `openExample(name)`.
- **Tension I must flag:** the file header and the run rules say "do not edit
  api.ts"; the task brief explicitly says "add to api.ts" and lists it in "files
  you own". I added only, changed nothing existing, and treated it as
  append-only. If this was wrong, the additions are easy to strip, but the
  renderer cannot be typed without them.

**Main / preload**
- `envelope.cts`: `LibraryCheckResultSchema`, `ExamplesListSchema`,
  `CheckLibrarySchema`, `OpenExampleSchema`. The nullable fields (`function`,
  `citation`, `exclusionReason`) use `.nullable()` not `.optional()` — the core
  always emits the key, and "not cited"/"included" must be an explicit null.
- `session.cts`: new `CoreKind` cases `listExamples`/`checkLibrary`, matching
  cases in `buildCommandArgs` (which now accepts `ProjectState | null` and an
  optional `arg`), plus `listExamples()`, `checkLibrary(path)` (relative path
  scoped to the project root), `openExample(name)` (delegates to the existing
  `openBundledExample`), and an `invokeStandalone` helper that does not require
  a project.
- `ipc.cts` + `preload/index.cts`: the three handlers / bridge lines.

**Renderer**
- `bridge/fake.ts`: the three methods + `checkedLibraries`/`openedExamples`
  records for assertions.
- `renderer/panels/` — six panels, each with idle/loading/error/success states:
  - `ToolchainStatusPanel` (`inspect.doctor`) — found tools with version+path,
    missing tools with `purpose` ("Missing — formal property checking…"), and
    the bundled-resource checks. Publishes the report to `doctorStore` for the
    shell's status-bar slot.
  - `ProvenancePanel` (`inspect.provenance`) — coverage reported from the core
    (not recomputed), entries with `exact`/`inferred` confidence, filterable.
  - `MappedNetlistPanel` (`inspect.mappedNetlist`) — structured instance-name
    listing + raw `write_json`, with an explicit note that these are *instance*
    names vs stable names.
  - `PackedNetlistPanel` (`inspect.packedNetlist`) — per-package `cells`
    (STABLE) and `instanceCells` (instance) in two labelled columns + raw JSON.
  - `LibraryPanel` (`inspect.library`) — validates `ProjectInfo.libraryPath`,
    surfaces per-part citation status (verified/unverified/uncited) and
    exclusions.
  - `ExamplesPanel` (`project.examples`) — list with showcase marked, Open
    calls `openExample`.
  - `index.ts` maps the six registry ids to components (documented in the file).

## Command id → component

```
inspect.doctor        -> ToolchainStatusPanel
inspect.provenance    -> ProvenancePanel
inspect.mappedNetlist -> MappedNetlistPanel
inspect.packedNetlist -> PackedNetlistPanel
inspect.library       -> LibraryPanel
project.examples      -> ExamplesPanel
```

## What I guessed / decided

- **`openExample` does not spawn `gatepack examples extract`.** It reuses
  `session.openBundledExample` (the scratch-copy-and-open flow the showcase and
  the Examples menu already use), so discovery and opening share one
  implementation and opening works even when the core is missing. `examples
  extract --json` is therefore *not* implemented; I judged it dead surface.
- **`lib check <x>.gpk --json` is not implemented** — the GUI only ever checks
  the loaded CSV (`ProjectInfo.libraryPath`), never a `.gpk`; the `.gpk` check
  stays human-only. If `--json` is ever passed with a `.gpk`, the core prints
  human text and the session surfaces a GP9002 parse failure (honest, if crude).
- **Doctor's exit-code philosophy extended to `lib check`.** The human CLI still
  gates (exit 1 on missing citations); JSON is a report. This mirrors
  `doctor`'s documented "report, never a gate".

## Placeholders / weakest points

- **Panels are styled from `ui/tokens.css` only** (`panels/panels.css`), no
  literal colours/spacing. The committed `App.tsx`/`styles.css` still use the
  legacy `--bg`/`--text` aliases and do not set `data-theme`, so until the shell
  agent lands its token migration the panels may render light against the dark
  legacy shell. That is a transient visual mismatch, not a logic one.
- **Status-bar hand-off is `panels/doctorStore.ts`**, a module store the shell
  agent can subscribe to (no provider, mirrors `selection/linkData.ts`). The
  shell must actually consume it; I could not wire the bar myself (App.tsx is
  off-limits).
- **The build refusal ("synthesis unavailable … never faked here")** still
  surfaces through BomView's build error (owned by the views agent), which I
  could not touch. My half of that story is the doctor panel naming the missing
  binary + purpose; the two together give "yosys is missing, it does logic
  synthesis, install it". I did not add a test that a *build* failure envelope
  reaches a panel, because no build panel is in my scope.
- **`openBundledExample` does not call `onProjectOpened`**, so an example opened
  from the new panel is not persisted as the last-opened project (the showcase
  deliberately isn't; non-showcase examples arguably should be). I left that
  behaviour as-is rather than change the showcase semantics.

## What I verified

- Python: `.venv/bin/python -m pytest tests -q` → **561 passed, 5 skipped** (was
  557/5).
- App: `npx vitest run` → **204 passed** (was 180); `tsc` (both projects) clean;
  `npm run build:main` clean; `npx vite build` clean.
- E2E: `DISPLAY=:1 npx playwright test` → **12 passed**. The §5.2 posture test
  pins the exact `window.gatepack` key list, so it was updated to include the
  three new methods (`app/tests/e2e/app.spec.ts`) — a contract assertion must
  track the contract.
- Real core in `gatepack-toolchain:m6`:
  `python3 -m gatepack.cli lib check libraries/74aup.csv --json` → `ok, 22
  cells, 19 included, 0 missing`; `examples list --json` → `[('pelican', True)]`.
- New tests pin the failure inputs: the doctor failure-envelope path, the
  missing-citation finding, the nullable-vs-optional schema trap (dropping a
  nullable key fails), the stable-vs-instance name-space labelling, and the
  `buildCommandArgs` cases.
