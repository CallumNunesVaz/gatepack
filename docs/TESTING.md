# TESTING.md — gatepack test architecture

gatepack is tested in layers, modeled on the `reqmesh` project: an API-contract
layer, a golden layer, a shell harness over a built artefact, and a future GUI
layer. Each layer tests a different contract and is run differently.

## Layers

```
tests/unit/       pure-Python behaviour: models, emitters, verdict logic
tests/golden/     §18 reference designs — passing and must-fail
tests/contract/   the CLI contract (exit codes, artefact shape)
scripts/tests/    shell harness — post-build functional checks
(app/e2e/)        future GUI layer — see "GUI tests" below
```

### 1. Unit (`tests/unit/`)

Tests the pure-Python core with no subprocess and no Yosys: the parts model,
the Liberty generator/validator, the C1 front-end (schema, expression language,
YAML subset parser, Verilog emitter), the C3 script *generation*, and the §6
verdict logic.

```
.venv/bin/pytest -q tests/unit
```

The synthesis script and verdict are unit-testable because Yosys script
*generation* is a pure function and `gatepack.estimate.assess` is a pure
function. Nothing here requires Yosys.

### 2. Golden (`tests/golden/`)

The §18 reference designs, stored in `tests/golden/designs/`. Passing designs
(`traffic_light.yaml`, `xor2.yaml`, `decoder_3to8.yaml`) run through C1 and
assert concrete output (one-hot state bits, `src` attributes, combinational
`assign`s). The must-fail designs assert the front-end *rejects* them:

| Design | Rejected by |
|---|---|
| `overlapping_guards.yaml` | SAT-style guard-overlap check |
| `unreachable_state.yaml` | reachability (BFS from `initial`) |
| `non_exhaustive.yaml` | non-exhaustive transition set |
| `async_handshake.yaml` | async refusal (§7.3, exit 3) |
| VCC-incompatible macro (74HC `CNT4` @ 1.8 V) | §9.4 [R4-8] check in `estimate` |
| single-sourced cell | §10.1 [R4-9] exclusion in C2 |

Two entries are skipped with an explicit reason because they need a toolchain
that is not installed here: `property_violating.yaml` (needs sby, M6) and
`latch_inferring.v` (needs a real Yosys run to trip the §9.2 latch ban).

```
.venv/bin/pytest -q tests/golden
```

### 3. Contract (`tests/contract/`)

gatepack's public API is its CLI plus the JSON/CSV artefacts it emits. The
contract is pinned here:

- exit codes — `0` success, `1` error, `2` usage, `3` async-refused (the codes
  are named constants in `gatepack/cli.py`);
- stable `manifest.json` keys (`schema_version`, `tool`, `tool_version`,
  `design`, `timing_model`, `encoding`, `yosys`, `verdict`);
- deterministic sorted output and **no timestamps** in the payload (§C6).

A change in output shape must fail a contract test, because downstream tooling
and the future GUI both depend on it.

```
.venv/bin/pytest -q tests/contract
```

### 4. Shell harness (`scripts/tests/`)

Mirrors `reqmesh`'s `scripts/tests/`. `harness.sh` is sourced and provides
`ok` / `bad` / `check` / `check_code` / `check_eq` / `check_file` assertions
with no test framework; `run.sh` executes every `test_*.sh` and aggregates.

`test_cli_e2e.sh` drives the *built* CLI end to end on the traffic-light golden
— the "works after a full build" check. It is safe on a developer machine: no
sudo, no package installs, no ports bound, no network.

```
scripts/tests/run.sh
```

## Toolchain-dependent tests (`tests/toolchain/`)

**Superseded 2026-08-16.** This section used to say Yosys was not installed and
everything needing it skipped. That floor is exactly how three defects reached
`integration` with a full green suite:

- generated Verilog that Yosys rejected outright (`M0-FINDINGS.md` §1);
- properties asserted over undriven wires, which prove nothing at all
  (`M6-FINDINGS.md` §6);
- an equivalence check that errored out before comparing anything, on every
  design, always (`M0-FINDINGS.md` §6).

Every one passed unit tests, because unit tests drive a **fake runner**. A fake
runner cannot reject your Verilog. The only cure is running the binaries.

The container is `Dockerfile.probe`, and it carries Yosys 0.23, ABC, Icarus,
SymbiYosys, z3 **and pydantic** — that last one so the CLI itself runs inside
it, not just the tools:

```bash
docker build -f Dockerfile.probe -t gatepack-toolchain:m6 .

# the toolchain test layer
docker run --rm -v "$PWD:/repo" -w /repo gatepack-toolchain:m6 \
    python3 -m pytest tests/toolchain -q

# the real thing, end to end
docker run --rm -v "$PWD:/repo" -w /repo gatepack-toolchain:m6 \
    python3 -m gatepack verify tests/golden/designs/xor2.yaml \
      --library libraries/74aup.csv --build .gpout/xor2
```

Two rules for this layer, both learned the hard way:

1. **A skip is a failure here.** A toolchain test that skips is
   indistinguishable from one that does not exist, so the CI job fails if any
   test in `tests/toolchain` skips. Skipping is correct on a developer laptop
   without Docker; it is not correct in CI.
2. **Fixtures are recorded, never invented.** `tests/fixtures/sby/*.recorded.log`
   was captured from real sby runs. The previous parser was tested only against
   hand-written fixtures that used the bare SVA label, while real sby brackets
   the task *name* — every check silently degraded to `not_run` and the tests
   stayed green. If you add a fixture, record it and label it as recorded.

Write build output to `.gpout/` (gitignored) rather than `/tmp`.

## GUI tests — built, and what they cover

§20's "do not build yet" no longer applies: M12–M15 exist.

```
app/renderer/**/*.test.tsx    component tests (vitest + jsdom, fake bridge)
app/main/**/*.test.ts         session manager, IPC, path scoping (vitest, node)
app/tests/e2e/*.spec.ts       Playwright driving the real Electron main process
```

```bash
cd app
npx vitest run                 # both projects via vitest.workspace.ts
npm run build:main             # e2e needs dist/main/index.cjs
DISPLAY=:1 npm run test:e2e
```

Notes that will save time:

- **`vitest.workspace.ts` is load-bearing.** `vitest.config.ts` takes
  precedence over `vite.config.ts`, so without the workspace file `vitest run`
  silently runs only the main-process project — 54 renderer tests vanished that
  way during a merge while the command still reported green.
- **The Playwright config is `.cjs` and lives in `app/`.** `app/package.json`
  is `"type": "module"`, so a `.ts` config is loaded as ESM, where
  `@playwright/test` exposes no named `defineConfig` and `__dirname` is
  undefined. The specs live in `app/tests/e2e` rather than the repo-root
  `tests/` because Node resolves `node_modules` by walking up from the
  importing file, and nothing above the repo-root `tests/` has one.
- **The e2e tests drive the bridge, not the markup.** They call
  `page.evaluate(() => window.gatepack...)` rather than clicking, which keeps
  them independent of renderer changes and lets both halves be developed in
  parallel. The §5.2 posture test is the important one: it asserts from inside
  the renderer that `window.require` and `process` are unavailable and that
  `contextIsolation` and `sandbox` are genuinely on.
- Renderer component tests run against an **injectable fake bridge**, never a
  real process.
