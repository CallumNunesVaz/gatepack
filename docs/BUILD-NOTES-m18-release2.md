# BUILD NOTES — M18 release 2 (cross-platform bundles, signing wiring, verifiable artefacts)

Scope: `.github/workflows/release.yml`, `app/electron-builder.yml`,
`app/signing/entitlements.mac.plist`, `scripts/bundle_core.py`,
`scripts/repro_installer.py`, `scripts/sbom.py`, `scripts/assemble_release.py`,
`scripts/version_check.py`, `docs/RELEASING.md`, `CHANGELOG.md`, and tests under
`tests/unit/` + `tests/toolchain/`. Also two minimal cross-scope touches,
recorded here rather than hidden: `app/main/core.cts` (the Windows `.exe`
resolution the brief explicitly allowed) and `app/package.json` (a `homepage`
placeholder — the `deb` target refuses to build without one).

## Test counts

```
baseline (measured this session):   .venv/bin/python -m pytest tests -q   568 passed, 5 skipped
after:                              .venv/bin/python -m pytest tests -q   (see final run below)
bundle acceptance:                  pytest tests/toolchain/test_core_bundle.py -q   5 passed
app vitest (before/after):          250 passed  ->  250 + 2 (binaryName) = 252 passed
```

New unit tests, each built so it *can* fail:

- `tests/unit/test_bundle_core.py` — the `.exe` naming and the scrub detecting
  `python.exe`/`gatepack.exe`.
- `tests/unit/test_sbom.py` — the SBOM lists shipped-vs-dev from the lock file,
  bundle licences come from the audit's table, require-flags fail on missing
  inputs, output is deterministic.
- `tests/unit/test_repro_installer.py` — the compare verdict + the NOT-MEASURED
  path.
- `tests/unit/test_assemble_release.py` — checksums are `sha256sum -c`-real,
  unsigned announces itself, signed does not claim unsigned, missing marker →
  `unknown`, mixed → `mixed`, deterministic.
- `tests/unit/test_version_check.py` — `--tag` agrees/fails.

## 1. Cross-platform core bundles

`scripts/bundle_core.py` gained a `binary_name()` (`.exe` on Windows) and the
scrub now removes any PATH directory containing `gatepack`/`python` in either
bare or `.exe` form. `app/main/core.cts` resolves the bundled core as
`gatepack.exe` on Windows (a pure `binaryName()` helper + a `platform` option on
`LocateOptions` so the win32 path is unit-tested on a POSIX host).
`tests/toolchain/test_core_bundle.py` is platform-aware (`.exe` naming, `.exe`-
aware scrub) so the acceptance test can run on Windows/macOS runners.

**Not verified here:** I cannot run Windows or macOS on this box. The acceptance
test passes on Linux; the release workflow runs it on each runner precisely so a
platform that cannot produce a working bundle fails CI rather than shipping
untested. That is the honest division of labour.

## 2. Signing — wired but unpopulated

`app/electron-builder.yml` now sets `hardenedRuntime`, `gatekeeperAssess:
false`, `entitlements`/`entitlementsInherit` (`app/signing/entitlements.mac.plist`,
the standard Electron JIT/executable-memory entitlements), and `notarize: true`.
`identity` is deliberately **unset** (not `null`) so signing is a pure
secrets-supply step. I verified against the installed `app-builder-lib` source
that: `identity: null` would hard-disable signing; `notarize: true` with no
Apple secrets logs "skipped macOS notarization" and continues (not a failure);
absent `CSC_LINK` Windows logs "no signing info identified, signing is skipped";
and macOS absent an identity logs "skipped macOS application code signing".
That is the exact "absent secrets → succeed and say so" behaviour the brief
demands, so the yml leaves `notarize: true` and drives signed-vs-unsigned from
the workflow instead of from a file edit.

The entitlements live at `app/signing/` rather than electron-builder's
conventional `app/build/` because `app/build/` is matched by the pre-existing
`.gitignore` `build/` pattern (which I may not edit), so a file there would
never be committed — and a signing config that vanishes on checkout is exactly
the kind of silent failure this milestone exists to prevent.

The release workflow detects `CSC_LINK` per job, prints an explicit
SIGNED/UNSIGNED banner, sets `CSC_IDENTITY_AUTO_DISCOVERY=false` on the unsigned
path, and passes the Apple secrets only on the signed path.

**What I could not verify:** actual codesigning and notarization (no credentials
exist and none may be fabricated). The entitlements plist is the standard
Electron set; if the PyInstaller core refuses to launch under hardened runtime,
`com.apple.security.cs.disable-library-validation` is the documented next step —
it is deliberately left out (a real relaxation, not a default) and called out in
the plist comment.

## 3. Verifiable artefacts

- **`scripts/sbom.py`** produces a CycloneDX 1.4 JSON SBOM that imports
  `scripts/licence_audit.py` and calls its `iter_installed_packages`,
  `shipping_paths_from_lock`, `electron_builder_excludes`, `_enumerate_bundle`
  and classification helpers, so the SBOM and the audit cannot disagree.
  Deterministic (sorted, no timestamp). Measured against the real tree + bundle:
  678 npm components + 20 bundle components = 698.
- **`scripts/assemble_release.py`** turns the per-platform `SIGNING-STATUS.txt`
  markers into `SHA256SUMS`, `SHA256SUMS.txt` (checksums + signing status) and
  the release body. The unsigned notice is the point: a user learns "unsigned"
  from the project, not from Gatekeeper.
- **Installer reproducibility, measured** (`scripts/repro_installer.py`):
  `--linux dir` = **reproducible** (75/75 identical); `AppImage` = **NOT**
  (1/76 differs); `deb` = **NOT** (1/76 differs). The installers embed
  non-deterministic metadata; the unpacked tree does not. This is recorded in
  `docs/RELEASING.md` rather than assumed either way.

## 4. Docs

`docs/RELEASING.md` rewritten end-to-end: the workflow, the secrets table (what
each secret is and where to get it), the cutting procedure in order (core bundle
before audit before app build before tag), a copy-paste checklist, the measured
reproducibility statement, and a native-toolchain section that degrades
gracefully if `scripts/bundle_toolchain.py` has not landed yet. `CHANGELOG.md`
"Known limitations" now carries the true list, including the two new ones (16 of
22 placeholder cells; unverified `gates_per_pkg`).

## Guesses / placeholders

- `homepage: https://example.invalid/gatepack` is a placeholder (the
  RFC-reserved non-resolving TLD) added so the `deb` target builds; a maintainer
  must replace it, and it is listed alongside `appId`/`maintainer` in the docs.
- The entitlements are the standard Electron template; unverified under a real
  Developer ID.
- macOS runners: `macos-13` (x64) / `macos-14` (arm64) is the current
  GitHub-hosted split; if `macos-13` is retired the matrix row moves to whatever
  x64 runner remains, not to cross-compiling on arm64.

## Weakest parts / suspicions

1. **The workflow has never executed.** I validated both YAML files parse
   (js-yaml) and ran every command the workflow runs (bundle, acceptance test,
   licence audit, sbom, electron-builder AppImage/deb, version check) on this
   Linux host, but the job graph has not run on GitHub. The signing steps and the
   Windows/macOS runners are entirely unexercised here.
2. **`gh release create` is not idempotent** — re-running a tag that already has
   a release fails. Acceptable for now; a `--draft`/idempotency guard is worth
   adding if releases get re-run.
3. **Windows nsis artefact filename** is renamed in the staging step rather than
   trusted from electron-builder (whose default `gatepack Setup 0.1.0.exe` has
   spaces). If the nsis `artifactName` changes upstream, the `*.exe` glob still
   catches exactly one file, but I have not seen the actual Windows output to
   confirm there is never more than one `.exe` in `.gpout/dist`.
4. **The `homepage` placeholder is a fabricated-looking value** in a project
   whose discipline is "never fabricate". It is the RFC-reserved `.invalid` TLD,
   deliberately non-resolving, and it is documented as a placeholder — but it is
   the one new value in this work that is not measured, and I flag it as the
   thing most likely to be objected to.
