# BUILD NOTES — startup: first-launch showcase + faithful `.gpk`

Scope: `app/main/` (session, index), `app/tests/e2e/`, `gatepack/project/`
(serialize + `__init__`), the showcase golden, and `examples/pelican.gpk`.

## Test commands and result

```
$ .venv/bin/python -m pytest tests -q          # 408 passed, 2 skipped (was 403/2)
$ npx vitest run                               # 108 passed (was 98)
$ DISPLAY=:1 npm run test:e2e                  # 9 passed (was 7)
```

TypeScript typecheck is **not** clean at baseline and this is pre-existing, not
mine: `app/shared/api.ts` gained a `simulate` method (commit `dcbb84a`, "simulation
contract") but neither `app/preload/index.cts` nor the renderer's fake bridge
(`app/renderer/bridge/fake.ts`) implements it yet. That leaves

```
$ npx tsc --noEmit -p tsconfig.json    # 3 errors: FakeGatepack missing simulate
$ npx tsc -p tsconfig.main.json        # 1 error: preload missing simulate
```

These are in the simulation agent's scope (`gatepack/simulate.py`,
`app/renderer/`, `app/shared/api.ts` are all off-limits to me). `build:main`
still emits `dist/` despite the preload error (no `noEmitOnError`), which is how
the e2e suite runs. I did not touch `simulate`; my changes add zero new
typecheck errors.

## Part 2 — `.gpk` preserves source (§10.4)

The design document already identified the fix and I used it: carry the verbatim
`design.yaml` text through `DesignDocument.source` and emit it as the design
document body, falling back to canonical serialisation only when the project was
built in memory.

- `gatepack/project/__init__.py`:
  - `DesignDocument` gains `source: str | None = None`.
  - `_load_exploded` stores the raw text; `parse_gpk` recovers it via
    `serialize.split_documents` + `serialize.design_source`.
  - `gpk_text` emits the verbatim body when `source` is set; `design_text`
    returns it, so `explode_to_dir` writes it byte-for-byte.
- `gatepack/project/serialize.py`:
  - `dumps_documents_with_design_source`, `design_document`, `split_documents`,
    `design_source` — the emitter and its inverse. The `.gpk` stays plain
    multi-document YAML: `gatepack: 1` / `kind: design` header, then the
    `design.yaml` text verbatim (comments and key order intact), then the
    library/truth-table documents as before. **No block scalar was needed**, and
    I did not add one: emitting the source as the document body (as §10.4's own
    example already shows) is cleaner than a `source: |` block, and keeps
    `project.design.data` at the top level so `compile_design_file` and every
    downstream consumer are unchanged.
- `examples/pelican.gpk` regenerated from the new bundle — comments and key
  order are now in the file.

Round-trip acceptance: `explode_to_dir(bundle(examples/pelican))` reproduces
`design.yaml` exactly; pinned in `tests/golden/test_showcase.py`
(`test_showcase_gpk_round_trips_design_byte_for_byte`) plus
`test_showcase_gpk_preserves_comments_and_key_order`. Unit tests in
`tests/unit/test_project.py` pin the in-memory canonical fallback and that a
legacy canonical `.gpk` still explodes and re-bundles byte-faithfully.

**Old form**: still readable, not a breaking change. `parse_gpk` recovers the
design body of *any* `.gpk` (old canonical or new verbatim), so re-bundling an
old file reproduces it exactly. This is a deliberate property of the design: the
"source" is simply whatever body the file carried.

## Part 1 — showcase on first launch (§18.1)

`app/main/`:

- `session-store.cts` (+ test): last-opened-project persistence as a tiny JSON
  file in the session dir (`userData`, or `GATEPACK_SESSION_DIR` for tests).
- `session.cts`: `ProjectState.showcase` flag; `openBundledExample(name)` copies
  a bundled example into `os.tmpdir()` scratch and opens it as a directory
  project; `SHOWCASE_NAME = 'pelican'`; `saveProject()` on the showcase returns
  `GP4109` ("read-only; use Save As…"); `closeProject()` also removes showcase
  scratch dirs; `onProjectOpened` dep fires after non-showcase opens.
- `examples.cts` (+ test): `findExamplesRoot` (layered `projectRoot/examples` →
  `appRoot/examples` → `appRoot/resources/examples`) and `parseExamplesList`
  (parses `gatepack examples list` output; the core still owns discovery,
  ordering and summaries — I only locate the dir and parse names).
- `index.cts`: `bootstrap()` reads the stored session, opens the last project
  (falling back to the showcase), and does it **before** `loadURL` so the
  renderer's one-shot `readSpec()` on mount sees a real project; re-broadcasts
  `projectChanged` after load. Menu gains "Open Showcase" and an "Examples"
  submenu (populated from `gatepack examples list`); "Save" routes to Save As…
  when the showcase is open.

E2E (`app/tests/e2e/`): `launchApp` now sets a fresh `GATEPACK_SESSION_DIR` per
launch (hermetic sessions), plus two new specs — "first launch with a clean
session opens the showcase" (readSpec returns pelican with comments, served from
a scratch copy, and Save returns `GP4109`) and "a previously opened project is
reopened on the next launch" (same session dir across two launches).

## Guesses, placeholders, and what I could not verify

- **Packaging path for examples is a placeholder.** `findExamplesRoot` checks
  `resources/examples`, but no electron-builder config ships `examples/` yet, so
  a packaged app would fall back to the source-tree path. Not verifiable here.
- **Showcase name is hard-coded as `'pelican'`** in the main process rather than
  read from the core (the core needs to run `examples list` to report the
  showcase, and the first-launch path must work without the core). Acceptable
  coupling; flagging it.
- **Save-on-showcase → Save As** is implemented as an error envelope (`GP4109`)
  plus a menu-level route; the real renderer's Save button is out of scope and
  must handle `GP4109` (the renderer is another agent's).
- **Trailing-newline assumption**: byte-for-byte round trip assumes `design.yaml`
  ends with a newline (every file in this repo does). A file with no trailing
  newline gets one appended on re-emit; documented, not handled.
- **E2E does not click the menu**; "Examples" listing is only unit-tested
  (`parseExamplesList`). The menu is exercised indirectly via the showcase
  launch path.

## Weakest points

1. `split_documents` re-implements yaml_subset's document-boundary rule
   (`_has_content`) so its output stays aligned with `parse_documents`. It is
   tested via the round-trip suite but is a second copy of a subtle rule.
2. The e2e "valid ProjectInfo" assertion leans on `readSpec()` (deterministic)
   and `saveProject() === GP4109` rather than capturing the `onProjectChanged`
   broadcast, which fires before the page can subscribe; the ProjectInfo shape
   itself is pinned by the pre-existing directory-open test.
3. The `simulate` contract seam is unresolved at baseline (see top); I worked
   around it but it must be finished by the simulation agent.
