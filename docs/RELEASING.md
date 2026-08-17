# Releasing gatepack

How to cut a release of gatepack. The core (Python, GPL-3.0-or-later) and the
desktop app (Electron) are versioned together and released from one tree, one
version number in two files (`pyproject.toml` and `app/package.json`), enforced
by `scripts/version_check.py`.

A release is: the tagged source, a self-contained Python core bundle per
platform, one installer per OS/arch (AppImage + deb on Linux, dmg on macOS arm64
and x64, nsis on Windows), a `SHA256SUMS` file (optionally GPG-signed), a
CycloneDX SBOM per platform, and release notes that say plainly whether the
installers are signed — **and, if they are signed, that the workflow verified
them** rather than assumed it.

## Signing: verified, not assumed

The whole point of the release machinery is that a build that *claims* to be
signed and is not, is caught. The release workflow does not trust
electron-builder's "I signed it" log line:

- **macOS** — `scripts/verify_signing.py macos` runs
  `codesign --verify --deep --strict --verbose=2` (the code signature),
  `spctl --assess --type execute` (the Gatekeeper verdict), and
  `xcrun stapler validate` (the notarisation ticket). Any failure fails the
  job, so an unsigned `.app` cannot ship as "signed".
- **Windows** — `scripts/verify_signing.py windows` runs
  `signtool verify /pa /v` (the Authenticode signature, chained to a trusted
  root). A missing or broken signature fails the job.
- **Linux** — no OS code signing exists; `scripts/verify_signing.py linux` runs
  `sha256sum -c SHA256SUMS` so every artefact is checksum-covered, and a
  detached GPG signature over `SHA256SUMS` (produced and self-verified by
  `scripts/gpg_sign_sums.py`) is supported when a `GPG_PRIVATE_KEY` secret is
  present.

A signed build that does not pass verification is the same class of defect as a
status reported by something that did not measure it. The workflow refuses to
publish it.

## The release workflow

`.github/workflows/release.yml` is tag-triggered (`v*`):

- **A build matrix, not a cross-compile flag.** PyInstaller does not
  cross-compile, so the workflow builds the core bundle on each target itself:
  `ubuntu-latest` (x64), `macos-13` (x64), `macos-14` (arm64), and
  `windows-latest` (x64). Each job runs the bundle's own acceptance test
  (`tests/toolchain/test_core_bundle.py`) on that OS.
- **Two structurally distinct paths.** Every job detects whether `CSC_LINK` is
  set, then runs exactly one of two clearly-named steps: `Build installer —
  UNSIGNED …` or `Build installer — SIGNED + notarized`. There is no quiet
  conditional; reading the step name tells you which path ran, and each writes
  its own job-summary banner.
- **The signed path is verified.** On macOS/Windows a `Verify signature` step
  runs `scripts/verify_signing.py` and fails the job if the artefact is not
  actually signed.
- **The unsigned path is honest.** Absent secrets the build succeeds, writes an
  unmistakable UNSIGNED banner to the job summary, and ships a
  `SIGNING-STATUS.txt` marker beside the artefacts. `scripts/assemble_release.py`
  carries that marker into `SHA256SUMS.txt` and the release notes, so a user
  learns "unsigned" from the project, not from Gatekeeper / SmartScreen.
- **Verifiable artefacts.** A `publish` job flattens the per-platform artefacts,
  writes `SHA256SUMS` (`sha256sum -c`-verifiable), optionally GPG-signs it,
  verifies the checksum coverage, and creates the GitHub release with `gh`.

`scripts/lint_workflows.py` (run in CI and in `scripts/tests/test_workflows.sh`)
parses both workflow files and asserts the release workflow still has its
verification and unsigned-marker machinery, so a YAML edit that drops a signing
step is caught before it ships.

## Secrets a maintainer must supply for a *signed* release

These are values only a maintainer can produce. The tree leaves them empty and
never fabricates them. Without them, the release succeeds and is explicitly
unsigned. They are read from the environment (or CI secrets); they are never
committed and never printed.

| Secret | Used by | What it is | Where to get it |
|---|---|---|---|
| `CSC_LINK` | macOS + Windows codesign | base64-encoded PKCS#12 (`.p12`/`.pfx`) code-signing certificate | See the Apple / Windows sections below |
| `CSC_KEY_PASSWORD` | macOS + Windows codesign | the password protecting that `.p12`/`.pfx` | the password you chose when exporting |
| `APPLE_ID` | macOS notarization (`notarytool`) | your Apple ID account (email) | an Apple Developer account |
| `APPLE_APP_SPECIFIC_PASSWORD` | macOS notarization | an app-specific password for that Apple ID | appleid.apple.com → Sign-In and Security → App-Specific Passwords |
| `APPLE_TEAM_ID` | macOS notarization | your Developer Team ID (10 characters) | developer.apple.com → Membership details |
| `GPG_PRIVATE_KEY` | Linux checksum signing (optional) | ASCII-armored GPG private key | your own GPG key (`gpg --armor --export-secret-keys`); used only to detach-sign `SHA256SUMS` |

To add them: GitHub → repository Settings → Secrets and variables → Actions →
New repository secret. The workflow reads them only via `env:` on the signed
steps; nothing is ever committed or echoed.

Mechanics worth knowing (verified against `app-builder-lib`'s source):
electron-builder reads `CSC_LINK`/`CSC_KEY_PASSWORD` directly for both macOS
codesign and Windows Authenticode (with `WIN_CSC_LINK` as an optional override),
and reads `APPLE_ID`/`APPLE_APP_SPECIFIC_PASSWORD`/`APPLE_TEAM_ID` for
`notarytool`. `app/electron-builder.yml` sets `hardenedRuntime`, the entitlements
(`app/signing/entitlements.mac.plist`), and `notarize: true`; with `notarize:
true` and *no* Apple secrets, electron-builder logs "skipped macOS notarization"
and continues — the absent-secret behaviour the unsigned path depends on.

### Apple, concretely

1. **Join the Apple Developer Program** (paid, ~USD 99/year). You cannot get a
   Developer ID certificate without membership.
2. **Create a Developer ID Application certificate** — *not* "Mac App Store"
   and *not* "Apple Development". In Xcode (Settings → Accounts → Manage
   Certificates) or on developer.apple.com → Certificates, Identifiers &
   Profiles → Certificates → create a **Developer ID Application** certificate.
   This is the certificate that signs apps for distribution *outside* the App
   Store; a Mac App Store certificate is useless for this release.
3. **Export it as `.p12`.** In Keychain Access, find the Developer ID
   Application certificate (with its private key), right-click → Export 2 items
   → save as `.p12` with a strong password. That password becomes
   `CSC_KEY_PASSWORD`.
4. **Base64-encode it for `CSC_LINK`.** `base64 -i your-cert.p12 -o cert.b64`
   (or `openssl base64 -in your-cert.p12`). Paste the whole base64 text (one
   line) into `CSC_LINK`. electron-builder decodes and imports it at build time.
5. **Create an app-specific password** at appleid.apple.com. *Apple relabels and
   moves this page regularly* — the current path is Sign-In and Security →
   App-Specific Passwords; if it is not there, search the Apple support docs
   rather than trusting this page's wording. Put the generated value in
   `APPLE_APP_SPECIFIC_PASSWORD` (it is tied to the Apple ID, not the cert).
6. **Find your Team ID** (10 characters) at developer.apple.com → Membership
   details. Put it in `APPLE_TEAM_ID`.

Notarisation (required for a usable macOS installer) is done by
electron-builder's `notarytool` integration using the Apple ID + app-specific
password + Team ID above; the ticket is then stapled to the `.dmg`, and the
release workflow's `xcrun stapler validate` confirms the staple.

### Windows, concretely

1. **Buy an Authenticode code-signing certificate** from a public CA (DigiCert,
   Sectigo, SSL.com, or a reseller). It is an *Authenticode* (code signing)
   cert, not a TLS/SSL cert.
2. **OV vs EV — know before you buy.** OV (Organization Validation) certs are
   delivered as a downloadable key/cert that you can export as `.pfx` and use in
   CI directly. EV (Extended Validation) certs require the private key to live
   on a hardware token (SafeNet eToken / YubiKey). **A hardware token does not
   work in CI** — there is no way to unlock a USB token from a headless runner.
   If you buy an EV cert expecting to sign from GitHub Actions, you will not be
   able to. For CI signing you want OV, or a service like Azure Trusted Signing
   where the key lives in Azure rather than on your machine.
3. **Export as `.pfx`** with a password (that becomes `CSC_KEY_PASSWORD`),
   base64-encode it, and set it as `CSC_LINK` (electron-builder reads `CSC_LINK`
   with a `WIN_CSC_LINK` override).

SmartScreen reputation is a separate, time-based thing: a valid signature does
not immediately silence SmartScreen for a brand-new certificate; it builds
reputation with installs. That is expected, not a signing failure.

## Local signing — for a maintainer with credentials on their own machine

Not everyone releases from CI. `scripts/sign_local.py` reads credentials from
the environment (never a file in the repo, never printed), runs the signed
build, then runs `scripts/verify_signing.py` — the exact verification CI runs —
and **refuses** to call the result "signed" if it cannot verify it.

```bash
# macOS (on the mac that will sign):
export CSC_LINK="$(cat cert.b64)"
export CSC_KEY_PASSWORD="..."
export APPLE_ID="you@example.com"
export APPLE_APP_SPECIFIC_PASSWORD="..."
export APPLE_TEAM_ID="ABCDE12345"
.venv/bin/python scripts/sign_local.py --platform darwin

# Windows:
export CSC_LINK="$(cat cert.b64)"
export CSC_KEY_PASSWORD="..."
.venv/bin/python scripts/sign_local.py --platform win32

# Linux (no OS signing; checksums + optional GPG):
.venv/bin/python scripts/assemble_release.py <staging> .gpout/release --version 0.1.0
GPG_PRIVATE_KEY="$(cat key.asc)" .venv/bin/python scripts/gpg_sign_sums.py .gpout/release/SHA256SUMS
.venv/bin/python scripts/verify_signing.py linux --sums-dir .gpout/release
```

If `CSC_LINK` (and friends) are missing, `sign_local.py` prints which names are
missing and exits non-zero; it never invents an identity. If the verification
step fails, it prints that the build is **not verified signed** and exits
non-zero. A "signed" artefact you cannot verify is refused, not produced.

## How to confirm a release really is signed

Do not trust the release notes alone — they are generated, and a generation bug
is the failure this project exists to catch. Verify the artefacts yourself:

```bash
# checksum coverage (every artefact):
sha256sum -c SHA256SUMS
# and, if the maintainer GPG-signed it, the signature:
gpg --verify SHA256SUMS.sig SHA256SUMS   # against the maintainer's published public key
```

macOS (download the `.dmg` and open the mounted app, or unzip and inspect):

```bash
codesign --verify --deep --strict --verbose=2 path/to/gatepack.app
spctl --assess --type execute path/to/gatepack.app        # expect "accepted"
xcrun stapler validate path/to/gatepack-0.1.0.dmg         # expect "The validate action worked!"
codesign -dv --verbose=4 path/to/gatepack.app             # expect "Authority=Developer ID Application: ..."
```

Windows:

```bat
signtool verify /pa /v gatepack-0.1.0-windows-x64-setup.exe
```

If any of these fails on a build the release notes call "signed", that is a bug
in the release machinery — report it, and treat the artefacts as unsigned.

## Identity placeholders to replace (independent of signing)

`appId` is now `io.github.callumnunesvaz.gatepack` and `homepage` is the real
repository URL. One placeholder remains, clearly marked in
`app/electron-builder.yml`:

- `maintainer: gatepack maintainers <maintainers@gatepack.invalid>` → a real
  name/email. Publishing a personal address in a public package is the
  maintainer's call, not a default; leave it as the marked TODO until someone
  chooses one.

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
4. **Run the licence audit yourself**, not just in CI:
   ```bash
   python scripts/licence_audit.py --require-node-tree --require-bundle
   ```
5. **Build the app**: from `app/`: `npm ci && npm run build`.
6. **Supply the signing secrets** if this release is to be signed (see the table
   above). If you supply none, the release is unsigned and says so — which is a
   valid release for v0.1.0; the maintainer has confirmed no credentials exist
   yet, so **0.1.0 will ship unsigned**.
7. **Tag and push.** `git tag -a v0.1.0 -m "gatepack v0.1.0" && git push origin v0.1.0`.
   The release workflow runs the matrix, builds and signs (or announces
   unsigned), **verifies** the signed result, assembles checksums + SBOM +
   notes, and creates the release.
8. **Verify the release yourself** (see "How to confirm a release really is
   signed" above), and confirm the release notes say either "signed" or
   "unsigned" — a silent release is a bug, whichever way it went.

### Release checklist (copy-paste)

```bash
# 1. green tree (CI green incl. desktop-packaging and toolchain)

# 2. version
.venv/bin/python scripts/version_check.py          # 0 = agree

# 3. core bundle (per target OS; shown for the host)
.venv/bin/python scripts/bundle_core.py
.venv/bin/python -m pytest tests/toolchain/test_core_bundle.py -q

# 4. licence audit
.venv/bin/python scripts/licence_audit.py --require-node-tree --require-bundle

# 5. app
(cd app && npm ci && npm run build)

# 6. signing secrets (optional; absent -> unsigned) — see the table above

# 7. tag
git tag -a v0.1.0 -m "gatepack v0.1.0" && git push origin v0.1.0

# 8. verify (after the release workflow completes)
sha256sum -c SHA256SUMS
#    and, for a signed release, the codesign/spctl/stapler or signtool checks above
```

If `scripts/bundle_toolchain.py` exists by then (a parallel milestone), add a
step between 5 and 6: run it per platform to place the native toolchain under
`app/resources/bin/` alongside the core, then re-run the licence audit and the
package step. If it does not exist, the native toolchain is **not bundled** and
nothing below is affected — the packaged app reports each missing tool honestly
(`gatepack doctor`) and everything except synthesis/verification works without
host tools.

## Reproducibility — measured, not assumed

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

A `SHA256SUMS` published with a release is a fixed checksum of *that* build, not
a reproducible-build guarantee — and a code signature is a signature of *that*
build's bytes; the two are complementary, not interchangeable.

## The native toolchain (separate from the core bundle)

The Python core ships. yosys / sby / iverilog / z3 do not yet: a packaged app
with no host toolchain still works for everything that does not need them and
fails legibly when it does (`gatepack build` names the missing binary and its
purpose; `gatepack doctor` reports each tool as found-with-version or missing).
See `docs/BUILD-NOTES-m18-core.md` for the per-tool licence clearance. When the
toolchain bundling lands, it drops into the same `app/resources/bin/` location
and the `extraResources`/`asarUnpack` entries pick it up with no further config.

## Known packaging notes

- **The asar is large** (~160 MB) because production `node_modules` ships whole
  while the vite renderer bundle already embeds React/monaco/elkjs/netlistsvg/
  reactflow. Only `zod` is genuinely required at runtime by the main process.
- **`electron-builder` warns** `file source doesn't exist … app/resources` when
  the core bundle has not been built. Run `python scripts/bundle_core.py` first.
- **The deb target requires a real `maintainer`.** The placeholder makes it
  build; replace it before a public release.
- **`gh release create` is not idempotent** — re-running a tag that already has
  a release fails. Re-run a tag only after deleting the old release.
