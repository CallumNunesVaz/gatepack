# Package: make the end-to-end tests real, and run them in CI

You are a test engineer whose first question about any green suite is "what
would have to break for this to go red?"

## The project

`gatepack` compiles a truth table or FSM specification into a bill of materials
and a schematic netlist built from discrete 74AUP logic packages, formally
verifying the result on every build. The Electron app in `app/` is strictly a
view over artefacts the CLI produces: it spawns `gatepack <cmd> --json`,
validates the envelope in the main process, and renders it.

Its distinguishing claim is that it never reports a status it has not measured.
Two failures of that principle are in your scope.

## Defect 1 — Playwright never runs in CI

`.github/workflows/ci.yml` has three jobs (`test`, `toolchain`,
`desktop-packaging`). None runs `app/tests/e2e/`. Fifteen e2e tests exist,
including the **§5.2 security-posture test** that asserts `require`, `process`
and `ipcRenderer` do not leak into the renderer and that the bridge exposes
exactly the documented method list. That check runs only when a human runs it.

Add it to CI. Electron needs a display — `xvfb-run` is the usual answer and the
repo already drives the suite locally with `DISPLAY=:1`. It must be a real
failure, not a soft one: if the e2e job cannot start Electron, the job fails
rather than skipping.

The build steps the suite needs are `npm run build:main && npx vite build`
from `app/`, then
`npx playwright test --config playwright.config.cjs`. Playwright browsers do not
need downloading — this drives Electron directly — but check that assumption
rather than trusting it.

## Defect 2 — the fake core implements two commands out of fifteen

`app/tests/e2e/helpers.ts` contains `FAKE_CORE_SCRIPT`, a shell script wired in
via `GATEPACK_CORE`. It implements `compile` and `project` and returns

```json
{"ok":false,"command":"unknown","schema":1,"error":{"code":"GP9999", ...}}
```

for everything else. So every e2e test that touches `estimate`, `verify`,
`build`, `analyse`, `provenance`, `simulate`, `mappedNetlist`, `packedNetlist`,
`doctor`, `checkLibrary`, `listExamples` or `openExample` is exercising an error
path and calling it coverage.

**This is not hypothetical.** The status bar shipped reading "no project" while
a project was open, and the tool that found it was a screenshot, not a test.
The renderer had been calling `openProject()` — the native file picker — on
mount; a cancelled dialog reports as an error, so the project stayed null. An
e2e suite that exercised the real surface would have caught it.

Extend the fake core to answer **every** command in `app/shared/api.ts` with a
well-formed, schema-valid envelope. Requirements:

- The envelopes must **validate against the zod schemas in
  `app/main/envelope.cts`** — that is the whole point. A fake that emits a shape
  main rejects tests nothing; a fake that emits a shape main accepts but which
  differs from what the real core emits is worse, because it is a lie that
  passes. Cross-check each payload against the real core's output:
  `./start cli <cmd> ... --json` (it runs the toolchain container automatically
  when yosys is missing).
- Keep it hermetic and fast. No network, no toolchain, no Python.
- Keep the existing `GATEPACK_FAKE_SLEEP_SECS` cancellation hook working.
- A shell script may no longer be the right vehicle for fifteen JSON payloads.
  A small Node script is fine if you justify it; `GATEPACK_CORE` just needs an
  executable.

Then **write the e2e tests that this unlocks** — the ones that could not have
been written before:

- every bridge method returns an envelope main accepts (a table-driven test)
- the doctor panel renders missing tools with their purpose
- a failing command surfaces its error to the user rather than an empty panel
- the status bar reflects the real project, and the design name agrees with it

## The acceptance criterion

For each new test, **break the thing it tests and confirm it goes red**, then
restore. Report what you broke and what the failure looked like. A test that has
never been observed failing is a claim, not a check. This project has shipped
**nine** pieces of machinery that reported a status while measuring nothing,
four of them with tests that could not have failed.

## Files you own

`.github/workflows/ci.yml`, `app/tests/e2e/**`, and new test files under
`app/tests/`.

## Off-limits — two other agents are in this repo right now

- `scripts/**`, `app/electron-builder.yml`, `docs/RELEASING.md`, `CHANGELOG.md`,
  `.github/workflows/release.yml` — the release agent.
- `gatepack/toolchain.py`, `gatepack/doctor.py`, `Dockerfile*` — the toolchain
  agent.
- `app/renderer/**`, `app/main/**`, `app/preload/**`, `app/shared/api.ts` — read
  them, do not edit them. If a defect in one blocks you, that is a finding:
  write it in your notes.
- `docs/MILESTONE-AUDIT.md`, `gatepack-design.md` — inputs.
