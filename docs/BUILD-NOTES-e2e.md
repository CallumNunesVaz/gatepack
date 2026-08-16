# BUILD-NOTES — e2e (real Electron end-to-end tests + fake core)

Scope: `.github/workflows/ci.yml`, `app/tests/e2e/**`, and new test files under
`app/tests/`. This package made the Electron e2e suite run in CI and made its
fake core answer the whole bridge surface instead of two commands.

## What I implemented

1. **`app/tests/e2e/fake-core.cjs`** — a standalone Node fake `gatepack` core
   (replacing the old shell script). It answers every command the bridge can
   dispatch:
   - the 12 JSON commands: `compile`, `estimate`, `verify`, `build`, `analyse`,
     `provenance`, `simulate`, `mapped-netlist`, `packed-netlist`, `doctor`,
     `lib check`, `examples list`;
   - the raw `project explode` / `project bundle` verbs (so the `.gpk`
     open/save specs keep working);
   - the non-`--json` `examples list` form the Examples menu reads.
   Each payload is hand-copied from the real core's `--json` output (verified
   against `./start cli ... --json`, which runs `gatepack-toolchain:m6` when
   yosys is missing) and against the payload builders in `gatepack/api.py`, so
   every envelope validates against the zod schemas in `app/main/envelope.cts`.
   Hooks: `GATEPACK_FAKE_SLEEP_SECS` (compile sleeps first, for the cancellation
   test) and `GATEPACK_FAKE_FAIL=<cmd,...>` (commands that answer with a
   well-formed `ok:false` envelope, for the error-surfacing test).

2. **`app/tests/e2e/helpers.ts`** — `getFakeCore()` now copies `fake-core.cjs`
   into a per-run temp dir and chmods it 0o755, instead of embedding a shell
   script in a template literal. Kept the `GATEPACK_SESSION_DIR` / env-passing
   behaviour unchanged.

3. **Four new specs** (the ones the fake core unlock):
   - `bridge-envelope.spec.ts` — table-driven: every core-backed bridge method
     returns an envelope main accepts (`ok:true`, `schema:1`, correct `command`,
     a `data` payload).
   - `doctor-panel.spec.ts` — `doctor()` reports missing tools, each with a
     non-empty `purpose`, and the status bar's toolchain indicator reflects it.
   - `error-surfacing.spec.ts` — a failing `verify` renders `verification-error`
     instead of an empty pane.
   - `status-bar.spec.ts` — the status bar shows the reopened project's
     `design.yaml` path and an agreeing design name.

4. **`.github/workflows/ci.yml`** — a new `e2e` job: node+python, `npm ci`,
   `pip install -e .` (so the real-core GUI-audit specs don't skip), build
   main+renderer, then `xvfb-run -a npx playwright test`. A skipped test fails
   the job (grep for `skipped`), matching the toolchain job's rule; Electron
   failing to start is already a hard failure (the launch throws, no `|| true`).

## Cross-check (real core output)

Each fake payload was checked field-for-field against `./start cli <cmd> --json`
run against `tests/golden/designs/traffic_light.yaml` + `libraries/74aup.csv`
(`build`/`estimate`/`verify`/`simulate`/`analyse`/`provenance`/
`mapped-netlist`/`packed-netlist` ran inside `gatepack-toolchain:m6`). Notable
observations: the real `verify` checks carry `durationMs: 0`; the real `doctor`
payload carries an extra `version` key that `DoctorReportSchema` strips (no
`.passthrough()`); the real `lib check` envelope uses `command: "lib"`, not
`"lib check"` — the fake mirrors all of these.

## Findings (defects I cannot fix — `app/renderer/**` is out of scope)

1. **The inspector panels are not mounted in the shell.** `ToolchainStatusPanel`,
   `ProvenancePanel`, `MappedNetlistPanel`, `PackedNetlistPanel`, `LibraryPanel`
   and `ExamplesPanel` are defined and unit-tested (`panels.test.tsx`) but no
   component imports them, and no handler is registered for `inspect.doctor`,
   `inspect.provenance`, etc. Dispatching any `inspect.*` command shows a
   "not wired yet" toast. Consequence: the *panel* half of the "doctor panel
   renders missing tools with their purpose" requirement is unreachable in e2e;
   `doctor-panel.spec.ts` therefore pins the bridge report + the status-bar
   toolchain indicator instead, and the purpose-text rendering remains covered
   only by the renderer unit test. Once the panels are wired, the UI assertion
   belongs in `doctor-panel.spec.ts`.

2. **`openProjectPath` mid-session leaves `status-design` stale.** The renderer
   reads the spec once on mount (`renderer/state/project.tsx`);
   `onProjectChanged` updates `project` (so `status-project` updates) but never
   re-reads the spec, so `model.name` — and thus `status-design` — stays at the
   previous project's name. My first version of `status-bar.spec.ts` exercised
   exactly this and went red ("pelican" vs "myproj"); I switched the test to the
   reopen-on-launch flow (the path that works) and recorded this as a bug.

3. **`onFileChanged` is not consumed anywhere in the renderer.** Main broadcasts
   debounced file-change events (C9) but no renderer code subscribes, so
   external edits never refresh the editor. Related to #2: the renderer's model
   of the spec is effectively frozen after mount.

4. **`AnalysisView` renders no error state.** A failing `estimate()`/`analyse()`
   leaves the Analysis view blank (no error element exists); only the
   Verification panel surfaces an `ok:false` envelope. The error-surfacing test
   therefore targets `verify`.

## Guesses and unverifiable points

- `xvfb-run` is assumed present on GitHub `ubuntu-latest` (it is standard, but
  this sandbox has only `DISPLAY=:1` and no `xvfb-run` binary, so I could not
  run the exact CI command). I verified the YAML parses (`js-yaml`) and the
  suite passes locally under `DISPLAY=:1`.
- "Playwright browsers do not need downloading" is confirmed: the config defines
  no `projects`/`browserName` and the tests only `_electron.launch`; the local
  run (no network) succeeded without any browser install.
- Electron's OS sandbox on the runner: local runs are non-root and sandboxed
  fine; if the runner ever needs it, `ELECTRON_DISABLE_SANDBOX=1` is the knob —
  not set by default because it would weaken §5.2.
- The fake core's values are small canned examples, not derived from a real
  design, and it does not write artefact files (`generated.v`, `bom.csv`, …) —
  the e2e specs don't read them. The real run only lives in my manual
  cross-check, not in the test.

## Weakest points

- The "doctor panel renders purpose" requirement is only reachable at the
  bridge level because the panel is unwired (finding #1).
- The CI fail-on-skip is a substring `grep -i skipped`; a test title containing
  "skipped" would false-positive (none does today).
- Latent divergence I could not touch: `api.py`'s `estimate_payload` emits
  `packageCount: null` when synthesis has not run, but `EstimateResultSchema`
  (and `api.ts`) type it `number`. The fake always emits a number, so it never
  trips this; a real no-yosys estimate would surface as GP9003.

## Side effect worth recording

The cancellation spec (`app.spec.ts`) dropped from ~30s to <1s. The old shell
script ran `sleep 30` as a *child* process, which survived the SIGKILL of the
shell and held the stdout pipe open, so `child.on('close')` did not fire until
`sleep` finished. The Node fake sleeps in-process (`setTimeout`), which dies
with the process, so cancellation settles immediately.
