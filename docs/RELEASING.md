# Releasing gatepack

How to cut a release of gatepack, v0.1.0 first. The core (Python, GPL-3.0-or-later)
and the desktop app (Electron) are versioned together and released from one tree.

## What exists and what does not

- **The desktop app packages and launches** — `app/electron-builder.yml` builds
  Linux (AppImage + deb), macOS (dmg, arm64 + x64) and Windows (nsis). A
  `--linux dir` build has been run here and starts.
- **The licence audit now sees the real tree and has found a real issue.**
  `spdx-exceptions` (CC-BY-3.0) ships inside the asar via netlistsvg's yargs CLI
  dependency subtree, so `scripts/licence_audit.py --require-node-tree` (and the
  `desktop-packaging` CI job) fails until it is remediated. See
  `docs/BUILD-NOTES-m18.md` for the analysis and the two options.
- **Signing is configured but not populated.** No identity, certificate or
  notarisation credentials exist in the tree, and none are fabricated. Until a
  maintainer supplies them, macOS/Windows builds are unsigned and will trip
  Gatekeeper / SmartScreen.
- **The Python core now ships inside the app.** `scripts/bundle_core.py` builds a
  self-contained `gatepack` binary (PyInstaller onefile, ~14.5 MB — no host
  Python, venv or gatepack required) at `app/resources/bin/gatepack`, the
  §17-reserved location `app/main/core.cts` prefers. The bundler smoke-tests the
  result under a scrubbed environment and refuses to install a stub; the
  acceptance test (`tests/toolchain/test_core_bundle.py`) re-proves it, and a
  packaging test greps the unpacked electron-builder tree for
  `resources/resources/bin/gatepack` (present, executable, outside the asar).
  This closes the one thing the earlier M18 round left open — see
  `docs/BUILD-NOTES-m18-core.md`.

## What CI does

- `test` — pure-Python core: pytest, shell harness, citation check,
  reproducibility, and the declared-manifest licence audit.
- `toolchain` — runs the real Yosys/sby/Icarus/z3 toolchain in a container and
  fails if any toolchain test *skips*.
- `desktop-packaging` — `npm ci`, version-consistency check, licence audit over
  the *installed* npm tree (`--require-node-tree`), app build, and an unsigned
  `electron-builder --linux dir` package. It does **not** yet run
  `scripts/bundle_core.py` (the core-bundle step is in the manual release
  steps above); wiring it in is a follow-up.

## Cutting v0.1.0

1. **Verify the tree is clean and green** (all CI jobs passing, including
   `desktop-packaging`). Do not cut from a tree where `desktop-packaging` or
   `toolchain` is red.
2. **Bump the version in both files, together** — `pyproject.toml` and
   `app/package.json`. `scripts/version_check.py` (run in CI) fails if they
   drift, so they cannot be released out of step. Update `CHANGELOG`-worthy
   notes if one exists.
3. **Run the licence audit yourself**, not just CI:
   `python3 scripts/licence_audit.py --require-node-tree`. It walks the real
   installed tree and fails on any unrecognised licence. If it reports one, add
   the licence to `POLICY` in `scripts/licence_audit.py` *by name, after
   review* — never by defaulting it to compatible.
4. **Build the bundled core**: `python3 scripts/bundle_core.py` (needs
   PyInstaller in the build environment). It refuses to install a broken binary,
   and the acceptance test (`tests/toolchain/test_core_bundle.py`) re-proves it.
5. **Build the app** from `app/`: `npm ci && npm run build`.
6. **Package the targets**:
   - Linux: `npx electron-builder --linux`
   - macOS: `npx electron-builder --mac` (on macOS, with signing set up — see
     below)
   - Windows: `npx electron-builder --win`
7. **Smoke-test the packaged app** (at minimum `--linux dir` into `.gpout/` and
   launch the unpacked binary), as a check that the config is valid and the
   renderer loads from the packaged layout — and confirm the unpacked tree
   contains `resources/resources/bin/gatepack` (see
   `tests/toolchain/test_packaging.py`).

## What a maintainer must supply before a real release

These are values only a maintainer can produce; the tree deliberately leaves
them empty.

- **`appId`** — `app/electron-builder.yml` uses the placeholder
  `org.gatepack.desktop`. Replace it with the organisation's real reverse-DNS id
  *before* anyone relies on macOS identity or Windows uninstall/GUID behaviour.
- **macOS signing** — an Apple Developer ID Application certificate, an Apple ID
  (with the certificate installed in the keychain), and a signing identity name
  for `electron-builder` (`CSC_LINK` / `CSC_KEY_PASSWORD` env, or a
  `mac.identity`). Add `mac.notarize: true` with `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`
  and `APPLE_TEAM_ID` to pass notarisation.
- **Windows signing** — a code-signing certificate (`CSC_LINK` /
  `CSC_KEY_PASSWORD`, or an Azure Trusted Signing / cert-key pair), otherwise
  SmartScreen will warn.
- **Linux deb `maintainer`** — `app/electron-builder.yml` uses a placeholder;
  set a real name and email.
- **The native toolchain** — see below (the Python core is already bundled).

## The core and the native toolchain

The Python core is bundled: `scripts/bundle_core.py` produces
`app/resources/bin/gatepack`, `app/main/core.cts` prefers that location (both in
the dev tree and, via `process.resourcesPath`, in the packaged app where
electron-builder's `extraResources` lands it at
`<package>/resources/resources/bin/gatepack`), and `app/electron-builder.yml`
already carries the matching `extraResources` + `asarUnpack` entries. The
bundler is a **build-only** step — PyInstaller must be installed in the build
environment (`pip install pyinstaller`) but is deliberately not a runtime
dependency in `pyproject.toml`.

The **native toolchain does not ship yet.** A packaged app with no host `yosys`/
`sby`/`iverilog` still works for everything that does not need them, and fails
legibly when it does: `gatepack build` without yosys reports
`yosys is not on PATH (logic synthesis: …)`, and `gatepack doctor` reports each
required tool as found (with version) or missing. Closing this means, per
platform, a source-built yosys/sby plus iverilog (and z3 for sby, reached
indirectly), each with its licence cleared (yosys ISC, sby ISC, iverilog
GPL-2.0-or-later, z3 MIT — all compatible with the app's GPL-3.0-only; the
chipsalliance espresso fork has **no top-level licence file** and is not needed
until the async backend, so it is not a blocker today). See
`docs/BUILD-NOTES-m18-core.md` for the full licence write-up.

To finish bundling, a future milestone must, in order of difficulty:

1. Build the native toolchain for each platform from the reproducible pinned
   `Dockerfile` (yosys 0.23, sby, espresso, Debian-packaged iverilog/z3) — the
   image has not been built end to end (see `docs/BUILD-NOTES.md`).
2. Place those under `app/resources/bin/` alongside the Python core; the
   `extraResources`/`asarUnpack` entries pick them up automatically.
3. Re-verify §5.2's "bundled binaries hash-pinned and verified at launch"
   requirement, which currently has no implementation to pin against.

Until then the packaged app's core location falls through to host toolchain for
synthesis/verification, `GATEPACK_CORE` remains the integration/test override,
and `gatepack doctor` is the honest status report.

## Known packaging inefficiencies (not bugs)

- **The asar is large** (~160 MB) because production `node_modules` is shipped
  whole. The renderer bundle (vite) already embeds React, monaco, elkjs,
  netlistsvg and reactflow, so those packages are present twice. Only `zod` is
  genuinely required at runtime by the main process. Excluding the renderer-only
  packages (or bundling the main process) is a size optimisation, not a
  correctness fix, and is deliberately left for later.
- **`electron-builder` logs** `file source doesn't exist … app/resources` when
  `app/resources/` is absent. With the bundler run, `app/resources/bin/gatepack`
  exists and the entry is live; the warning now means the core was not built
  (run `python3 scripts/bundle_core.py`), not a misconfiguration.
