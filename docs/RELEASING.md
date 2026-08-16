# Releasing gatepack

How to cut a release of gatepack, v0.1.0 first. The core (Python, GPL-3.0-or-later)
and the desktop app (Electron) are versioned together and released from one tree,
one version number in two files (`pyproject.toml` and `app/package.json`), enforced
by `scripts/version_check.py`.

A release is: the tagged source, a self-contained Python core bundle per
platform, one installer per OS/arch (AppImage + deb on Linux, dmg on macOS arm64
and x64, nsis on Windows), a `SHA256SUMS` file, a CycloneDX SBOM per platform,
and release notes that say plainly whether the installers are signed.

## The release workflow

`.github/workflows/release.yml` is tag-triggered (`v*`). It does not assume
anything it can run instead:

- **A build matrix, not a cross-compile flag.** PyInstaller does not
  cross-compile, so the workflow builds the core bundle on each target itself:
  `ubuntu-latest` (x64), `macos-13` (x64), `macos-14` (arm64), and
  `windows-latest` (x64). Each job runs the bundle's own acceptance test
  (`tests/toolchain/test_core_bundle.py`) on that OS, so a platform that cannot
  produce a working bundle fails the release rather than shipping an untested one.
- **Signing is wired but unpopulated.** Every job first detects whether
  `CSC_LINK` is set. If it is, the installer is signed (and notarized on macOS);
  if not, the installer is built *unsigned*, the build prints "UNSIGNED", and a
  per-platform `SIGNING-STATUS.txt` is uploaded. Absent secrets the build must
  succeed and say so — never fail obscurely, never silently skip.
- **Verifiable artefacts.** Each platform uploads its installer, its core
  bundle, its SBOM, and its signing status. A `publish` job flattens them,
  writes `SHA256SUMS` (`sha256sum -c`-verifiable), `SHA256SUMS.txt` (same
  checksums plus the signing status), and the release notes, then creates the
  GitHub release with `gh`.

## Secrets a maintainer must supply for a *signed* release

These are values only a maintainer can produce. The tree leaves them empty and
never fabricates them. Without them, the release succeeds and is explicitly
unsigned.

| Secret | Used by | What it is | Where to get it |
|---|---|---|---|
| `CSC_LINK` | macOS + Windows codesign | base64-encoded PKCS#12 (`.p12`/`.pfx`) code-signing certificate, or a path to that file | macOS: export your **Developer ID Application** certificate from Keychain Access as `.p12`. Windows: your Authenticode certificate (from your CA, or an OV/EV cert, or an Azure Trusted Signing account) exported as `.pfx` |
| `CSC_KEY_PASSWORD` | macOS + Windows codesign | the password protecting that `.p12`/`.pfx` | the password you chose when exporting |
| `APPLE_ID` | macOS notarization (`notarytool`) | your Apple ID account (email) | an Apple Developer account (developer.apple.com) |
| `APPLE_APP_SPECIFIC_PASSWORD` | macOS notarization | an app-specific password for that Apple ID | appleid.apple.com → Sign-In and Security → App-Specific Passwords → generate one |
| `APPLE_TEAM_ID` | macOS notarization | your Developer Team ID (10 characters) | developer.apple.com → Membership details |

To add them: GitHub → repository Settings → Secrets and variables → Actions →
New repository secret. They are only *read* (injected into `env:` of the signed
build step and the signing-detection step); they are never committed.

Mechanics you should understand, so you know why "supply the secret" is the only
step: electron-builder reads `CSC_LINK`/`CSC_KEY_PASSWORD` directly for both
macOS codesign and Windows Authenticode (with `WIN_CSC_LINK` as an optional
override), and reads `APPLE_ID`/`APPLE_APP_SPECIFIC_PASSWORD`/`APPLE_TEAM_ID`
for `notarytool`. `app/electron-builder.yml` sets `hardenedRuntime`, the
entitlements (`app/signing/entitlements.mac.plist`), and `notarize: true`; with
`notarize: true` and *no* Apple secrets, electron-builder logs "skipped macOS
notarization" and continues (verified against app-builder-lib's
`getNotarizeOptions`), which is exactly the absent-secret behaviour the release
depends on.

### Identity placeholders to replace (independent of signing)

`app/electron-builder.yml` and `app/package.json` carry clearly-marked
placeholders that are *not* signing but must be real before a public release:

- `appId: org.gatepack.desktop` → your organisation's reverse-DNS id.
- `maintainer: gatepack maintainers <maintainers@gatepack.example>` → a real name/email.
- `homepage: https://example.invalid/gatepack` (in `app/package.json`) → the real
  project URL. The `deb` target refuses to build without a `homepage`, so this
  placeholder exists to make the Linux build run; `example.invalid` is the
  RFC-reserved non-resolving TLD, not a fake URL.

## Cutting v0.1.0 — end to end

1. **Verify the tree is clean and green.** All CI jobs green (including
   `desktop-packaging` and `toolchain`). Do not cut from a red tree.

2. **Set the version in both files together** — `pyproject.toml` and
   `app/package.json`. `scripts/version_check.py` fails on drift, and
   `scripts/version_check.py --tag vX.Y.Z` (run by the release workflow) fails
   if the tag and the version disagree. Update `CHANGELOG.md`.

3. **Build the bundled core** (one per target OS, on that OS — PyInstaller does
   not cross-compile):
   ```bash
   python scripts/bundle_core.py          # -> app/resources/bin/gatepack[.exe]
   python -m pytest tests/toolchain/test_core_bundle.py -q   # acceptance test
   ```
   The bundler refuses to install a broken binary; the acceptance test re-proves
   it under a scrubbed environment.

4. **Run the licence audit yourself**, not just in CI:
   ```bash
   python scripts/licence_audit.py --require-node-tree --require-bundle
   ```
   It walks the installed npm tree *and* the bundled core and fails on any
   unrecognised or incompatible licence.

5. **Build the app**: from `app/`: `npm ci && npm run build`.

6. **Tag and push.** `git tag -a v0.1.0 -m "gatepack v0.1.0" && git push origin v0.1.0`.
   The release workflow runs the matrix, builds and signs (or announces
   unsigned), assembles checksums + SBOM + notes, and creates the release.

7. **Verify the release yourself** — download the artefacts, then:
   ```bash
   sha256sum -c SHA256SUMS
   ```
   and confirm the release notes say either "signed" or "unsigned" — a silent
   release is a bug, whichever way it went.

### Release checklist (copy-paste)

```bash
# 1. green tree
#    (CI must be green incl. desktop-packaging and toolchain)

# 2. version
.venv/bin/python scripts/version_check.py          # 0 = agree
#    bump pyproject.toml + app/package.json + CHANGELOG.md, then re-check

# 3. core bundle (per target OS; shown for the host)
.venv/bin/python scripts/bundle_core.py
.venv/bin/python -m pytest tests/toolchain/test_core_bundle.py -q

# 4. licence audit
.venv/bin/python scripts/licence_audit.py --require-node-tree --require-bundle

# 5. app
(cd app && npm ci && npm run build)

# 6. tag
git tag -a v0.1.0 -m "gatepack v0.1.0" && git push origin v0.1.0

# 7. verify (after the release workflow completes)
sha256sum -c SHA256SUMS
```

If `scripts/bundle_toolchain.py` exists by then (a parallel milestone), add a
step between 5 and 6: run it per platform to place the native toolchain under
`app/resources/bin/` alongside the core, then re-run the licence audit and the
package step. If it does not exist, the native toolchain is **not bundled** and
nothing below is affected — the packaged app reports each missing tool honestly
(`gatepack doctor`) and everything except synthesis/verification works without
host tools.

## Reproducibility — measured, not assumed

Two different things are reproducible to different degrees:

- **The core build is byte-reproducible** (`scripts/repro_check.py`): two clean
  builds produce identical netlist, BOM and manifest (10 artefacts), verified in
  the toolchain container.
- **The packaged *unpacked tree* is reproducible** (`scripts/repro_installer.py
  --targets dir`): two electron-builder `--linux dir` runs produced 75/75
  byte-identical files.
- **The packaged *installers* are NOT reproducible** — measured, not assumed:
  the `AppImage` and the `deb` each differ between two otherwise-identical
  builds (1 of 76 files), because electron-builder embeds non-deterministic
  metadata (timestamps). `scripts/repro_installer.py` records this rather than
  guessing.

So a `SHA256SUMS` published with a release is a fixed checksum of *that* build,
not a reproducible-build guarantee — and the docs say so rather than implying
otherwise.

## The native toolchain (separate from the core bundle)

The Python core ships. yosys / sby / iverilog / z3 do not yet: a packaged app
with no host toolchain still works for everything that does not need them and
fails legibly when it does (`gatepack build` names the missing binary and its
purpose; `gatepack doctor` reports each tool as found-with-version or missing).
See `docs/BUILD-NOTES-m18-core.md` for the per-tool licence clearance. When the
toolchain bundling lands (another milestone), it drops into the same
`app/resources/bin/` location and the `extraResources`/`asarUnpack` entries pick
it up with no further config.

## Known packaging notes

- **The asar is large** (~160 MB) because production `node_modules` ships whole
  while the vite renderer bundle already embeds React/monaco/elkjs/netlistsvg/
  reactflow. Only `zod` is genuinely required at runtime by the main process.
  This is a size optimisation, not a correctness fix.
- **`electron-builder` warns** `file source doesn't exist … app/resources` when
  the core bundle has not been built. Run `python scripts/bundle_core.py` first.
- **The deb target requires `homepage` and a real `maintainer`.** The
  placeholders above make it build; replace them before a public release.
