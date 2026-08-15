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

## Yosys-dependent tests

Yosys is **not installed** in this environment, and results are never faked.
Script generation and the verdict are unit-tested; anything that needs a real
`yosys`/`sby`/`iverilog` run is `pytest.skip(...)` with an explicit reason. When
the M0 pinned container exists, the skipped golden entries and the `dfflibmap`/
`abc` smoke test will run against it.

## GUI tests — the seam (do not build yet)

§20 forbids starting the GUI before M12, so there is no Electron test layer
today. The seam is defined now so it lands without a redesign when C10–C15
exist:

- **Playwright drives the built Electron app**, never a dev server. Tests load
  `app/dist/` (the packaged bundle) exactly as a user would, mirroring
  `reqmesh`'s `frontend/e2e/*.spec.ts` + `playwright.config.ts`.
- The GUI is a view over CLI-produced artefacts (§14), so GUI tests assert that
  the CLI contract above holds through the app: open a `design.yaml`, mutate it,
  and confirm the renderer reflects the same `manifest.json`/`generated.v` the
  CLI would emit. GUI tests *never* re-derive synthesis results; they verify the
  view is faithful to the artefacts.
- Selection/provenance (§15) is tested by asserting that a rendered gate
  highlights the correct source YAML line — the `src` attributes pinned by the
  unit and golden layers are the input to that assertion.

When C10–C15 land: add `frontend/e2e/*.spec.ts`, `playwright.config.ts`, and a
`test_gui` entry to the harness; add npm/Playwright as a **dev-only** dependency
(justified in `docs/BUILD-NOTES.md` per the no-new-deps rule). Nothing in CI
depends on the GUI (§§7, 14).
