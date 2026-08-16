# BUILD NOTES — M18 (packaging + release readiness)

Scope: electron-builder configuration, a licence audit that actually sees the
installed npm tree, version-consistency checking, release documentation, and a
CI job that packages the app and runs the audit. No `gatepack/`, `app/main`,
`app/preload`, `app/renderer`, `app/shared/api.ts`, or `tests/` were edited; all
were read.

## Test commands and result

```
$ .venv/bin/python -m pytest tests -q           # 467 passed, 2 skipped  (unchanged)
$ bash scripts/tests/run.sh                     # 5/5 test scripts (was 3/5; +2 new)
$ cd app && npx tsc --noEmit -p tsconfig.json   # clean
$ cd app && npx tsc --noEmit -p tsconfig.main.json  # clean
$ cd app && npx vitest run                      # 125 passed  (unchanged)
$ cd app && npx electron-builder --linux dir    # EXIT 0, unpacked app launches
```

## What was built

### 1. electron-builder configuration (`app/electron-builder.yml`)

Targets Linux (AppImage + deb), macOS (dmg, arm64 + x64), Windows (nsis).
`asar: true`, `asarUnpack: resources/bin/**`, `extraResources: resources -> resources`,
`publish: null` (no auto-update, no telemetry — §5.2). `directories.output` is
`../.gpout/dist` so the build never collides with the compiled `app/dist/`.

- `files` ships `dist/**` + `package.json`, and relies on electron-builder's
  automatic collection of **production** `node_modules`. That is required: the
  main process requires `zod` at runtime (`dist/main/envelope.cjs` validates IPC
  payloads), so the tree cannot be excluded wholesale. Verified in the built
  asar: no `electron`/`typescript`/`vite`/`vitest`/`@testing-library` shipped;
  `zod` and the renderer's transitive deps are present.
- **Verified:** `npx electron-builder --linux dir` into `.gpout/` succeeds and
  the unpacked `gatepack-app` binary launches and stays up (`--no-sandbox
  --disable-gpu`, timeout kill = exit 124). The renderer loads from
  `dist/renderer/index.html` (the "not built yet" fallback is not triggered).
- **Not verified here:** the full AppImage/deb/dmg/nsis targets, macOS arm64,
  and Windows — this machine is Linux and unsigned. The `dir` target is the one
  real end-to-end check that does not need signing or a second OS.

### 2. Licence audit over the installed tree (`scripts/licence_audit.py`)

The audit now has two inputs against one `POLICY` table: the declared manifest
(unchanged behaviour, still 16 entries) and the installed npm tree (opt-in via
`--node-tree` / `--require-node-tree`).

- **Shipped vs dev** comes from `app/package-lock.json` (`lockfileVersion: 3`):
  a package is shipped unless its `packages` entry is `dev` or `devOptional`.
  This is authoritative and was chosen over re-deriving the graph from
  `dependencies`, because the closure heuristic silently drops *nested*
  production dependencies — the concrete case is `netlistsvg` → `yargs@6`
  (nested) hidden by a hoisted `yargs@17` (dev-only). When no lock file exists,
  a flat-tree fallback over `dependencies`/`optionalDependencies`/
  `peerDependencies` is used. Licences are read from each installed
  `package.json`; the lock's own `license` field is never consulted.
- SPDX `OR`/`AND` expressions are parsed and evaluated (an `OR` is acceptable
  when any alternative is; an `AND` when every part is). New policy entries were
  added only after being identified by name, never defaulted:
  `blueoak-1.0.0`, `mit-0`, `python-2.0`, `cc0-1.0`, `wtfpl` (compatible);
  `epl-1.0` (conditional); `cc-by-3.0`, `cc-by-4.0` (incompatible — FSF regards
  CC-BY as not GPL-compatible).
- **Failure semantics:** shipped + incompatible → fail; shipped + unrecognised →
  fail; *any* package + unrecognised → fail (a licence the table cannot name is
  a hole, not a pass); dev-only + incompatible → warning, non-blocking.
- The EPL distinction survives: `epl-2.0` is `conditional` (not permissive) and
  stays so, and the audit now also finds the *nested* `elkjs@0.3.0` under
  `EPL-1.0` (see findings).

### 3. Version consistency (`scripts/version_check.py`)

`pyproject.toml` `[project] version` must equal `app/package.json` `version`.
Fails on drift or missing files; paths overridable so the failure case is
testable. Wired into CI and the shell harness.

### 4. Docs + CI

- `docs/RELEASING.md` — the steps to cut v0.1.0, what a maintainer must supply
  (appId, macOS/Windows signing identities, notarisation env, deb maintainer,
  the bundled core), and what each CI job does.
- `.github/workflows/ci.yml` — a `desktop-packaging` job: `npm ci`, version
  check, licence audit (`--require-node-tree`), app build, `electron-builder
  --linux dir`. Modeled on the `toolchain` job's "a skip is a failure" rule.

## Findings (both are real, both were invisible to the old audit)

### F1 — the shipped elkjs is EPL-1.0, not the EPL-2.0 §4 records

`app/package.json` declares `elkjs@0.9.3` (EPL-2.0) as a direct dependency, but
nothing in `renderer/`/`main/`/`preload/` imports it. What actually ships is
netlistsvg's transitive `elkjs@0.3.0` under **EPL-1.0** (nested at
`netlistsvg/node_modules/elkjs`, resolved via `netlistsvg`'s `elkjs: ^0.3.0`).
The design doc §4 table says "elkjs | EPL-2.0". That is wrong for the version
that ships. I added `epl-1.0` as `conditional` (the same file-scope-copyleft
argument §4 already accepts for EPL-2.0) so the audit stays green on this point,
but the discrepancy itself is a §4 defect and must be resolved by whoever owns
the design doc: either accept the same argument for EPL-1.0, or pin netlistsvg
to a release whose elkjs is EPL-2.0.

### F2 — `spdx-exceptions` (CC-BY-3.0) ships in the asar

`netlistsvg` declares `yargs@^6` as a runtime dependency, and yargs@6 pulls a
whole CLI/package-validation subtree (`read-pkg` → `normalize-package-data` →
`validate-npm-package-license` → `spdx-expression-parse` → `spdx-exceptions`).
`spdx-exceptions` is CC-BY-3.0, which the FSF lists as not GPL-compatible, so
the audit fails on it. Two things are true at once and both are worth saying:

- It is in the packaged artifact (electron-builder packs it as a production
  dependency), so by the audit's conservative "in the artifact = ships" rule it
  is a real finding.
- It is **not** in the executable: vite tree-shakes the yargs subtree out of the
  renderer bundle (netlistsvg's library entry `built/index.js` only imports
  `elkjs`/`onml`; yargs is CLI-only), and I verified zero occurrences of
  `spdx-exceptions`/`decamelize`/`os-locale`/`read-pkg` in `dist/renderer/`.

Two remediation options, left to the maintainer: (a) exclude netlistsvg's nested
`node_modules` from the asar (it is dead weight — the renderer bundle already
embeds what netlistsvg needs), or (b) make a documented argument that a CC-BY
data list that is never executed is acceptable aggregation. I did neither,
because option (a) would make the audit's "shipped" definition diverge from what
electron-builder packs, and option (b) is a legal judgment I should not make
silently. The `desktop-packaging` CI job is therefore expected RED until this is
decided.

## What is stubbed / placeholders

- `appId: org.gatepack.desktop` and `maintainer` in `electron-builder.yml` are
  placeholders. Signing/notarisation are absent by design (nothing fabricated).
- `extraResources: resources -> resources` is inert until a maintainer creates
  `app/resources/`; the build logs `file source doesn't exist … app/resources`,
  which is expected, not a misconfiguration.

## What I did not solve

- **The Python core does not ship inside the app.** `app/main/core.cts` prefers
  `app/resources/bin/gatepack`, then `.venv/bin/gatepack`, then PATH. Nothing
  populates `app/resources/bin/`, so a packaged app falls through to the host
  (venv/PATH) or a visible error envelope. Bundling the core means a standalone
  `gatepack` executable **plus** native yosys/sby/espresso/iverilog per platform;
  the reproducible `Dockerfile` (pinned source builds) is unbuilt and unproven.
  That is a future milestone, not something I could fake here. `docs/RELEASING.md`
  "The core" states this plainly.
- Full macOS/Windows/AppImage/deb packaging and signing are unverifiable on this
  Linux box; the `--linux dir` build is the honest subset.

## Three things I am least confident about

1. **The EPL-1.0 call.** I accepted it as `conditional` by analogy with §4's
   EPL-2.0, but the FSF considers both EPL versions GPL-incompatible; the §4
   "weak copyleft at file scope, unmodified library" argument is the project's
   own, and I have extended it to EPL-1.0 without a maintainer's explicit
   sign-off. The discrepancy (shipped elkjs is EPL-1.0, §4 says EPL-2.0) is a
   design-doc defect I cannot fix in my scope.
2. **"Ships = in the asar" vs "ships = in the executable".** The audit counts a
   production dependency as shipped even when vite tree-shakes it out of the
   renderer bundle (the spdx-exceptions case). That is conservative and safe,
   but it can raise findings for dead weight that a stricter, executable-scoped
   analysis would clear — and the two definitions will disagree until the
   node_modules-bloat follow-up (only `zod` is genuinely needed at runtime) is
   done.
3. **The lock-file authority.** I trust `package-lock.json`'s `dev`/`devOptional`
   flags to mark what electron-builder packs, and I verified the top-level set
   matches the built asar, but I did not prove the two agree for every nested
   package. A divergence there would shift the shipped/dev boundary silently.
