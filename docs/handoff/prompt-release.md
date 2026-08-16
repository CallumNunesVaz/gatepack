# Package: M18 — everything a signed, reproducible v0.1.0 needs

You are a release engineer preparing a first public release of a GPL-3.0
desktop application with a native core.

## The project

`gatepack` compiles a truth table or FSM specification into a bill of materials
and a schematic netlist built from discrete 74AUP logic packages, formally
verifying the result on every build. The Python core ships inside the Electron
app as a PyInstaller binary. Versions are locked together (`pyproject.toml` and
`app/package.json`, both 0.1.0, enforced by `scripts/version_check.py`).

M18 is the last open milestone. Read `docs/MILESTONE-AUDIT.md` for its honest
state — **do not edit it**, it is an input.

## The constraint you must respect

**No signing credentials exist in this repository, and none may be fabricated.**
Not a self-signed certificate presented as real, not a placeholder identity, not
a fake Team ID. This project's central discipline is that it never reports a
status it has not measured, and a build that claims to be signed when it is not
is the worst possible violation of that.

So your job is **everything up to the credential**: make signing a
configuration-and-secrets problem, so that a maintainer supplying credentials is
the only remaining step, and make the unsigned state visible rather than
silent.

## What to build

### 1. Cross-platform core bundles

`scripts/bundle_core.py` has only ever run on Linux. macOS and Windows bundles
are untested. PyInstaller does not cross-compile, so this means a build matrix,
not a clever flag.

Add a GitHub Actions **release workflow** (`.github/workflows/release.yml`,
tag-triggered) that builds on `ubuntu-latest`, `macos-latest` (both arm64 and
x64 if the runners allow) and `windows-latest`, runs the bundle's own acceptance
test on each, and uploads the artefacts. Where a platform cannot be verified in
CI, say so in the notes rather than assuming it works.

Watch for the traps that differ per platform: the binary is `gatepack.exe` on
Windows, `app/main/core.cts`'s resolution order must handle that, and the
`examples/` data added via `--add-data` uses `os.pathsep`, which differs.

### 2. Signing, wired but unpopulated

- macOS: `codesign` identity, hardened runtime, entitlements, and `notarytool`
  submission — configured in `app/electron-builder.yml` and driven entirely by
  secrets (`CSC_LINK`, `CSC_KEY_PASSWORD`, `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`,
  `APPLE_TEAM_ID`). Absent secrets, the build must **succeed unsigned and say so
  in its output**, never fail obscurely and never silently skip.
- Windows: Authenticode via `CSC_LINK`/`CSC_KEY_PASSWORD`, same discipline.
- Document every secret a maintainer must set, what it is, and where to get it,
  in `docs/RELEASING.md`. A maintainer should be able to follow it without
  guessing.

### 3. Verifiable artefacts

- **SHA-256 checksums** for every artefact, in a `SHA256SUMS` file published
  with the release.
- An **SBOM** covering both dependency trees — the npm tree and the bundled
  Python core. `scripts/licence_audit.py --require-node-tree --require-bundle`
  already enumerates both and passes over 714 components; reuse its enumeration
  rather than writing a second one that can disagree with it.
- The repo already checks build reproducibility (`scripts/repro_check.py`, two
  clean builds byte-identical). State plainly in the release docs whether the
  *packaged installers* are reproducible — they are probably not, because
  electron-builder embeds timestamps. Measure it; do not assume either way.

### 4. Finish the release documentation

- `docs/RELEASING.md` — the procedure must be correct end to end, in order,
  including the core bundle step and the toolchain bundle if one exists by then
  (another agent is working on it; write the section so it degrades gracefully
  if that lands later).
- `CHANGELOG.md` — it exists and covers 0.1.0. Update its "known limitations"
  to the true list: unsigned installers, KiCad import unverified (deferred out
  of scope), 16 of 22 library cells carry placeholder electrical data, and the
  multi-gate `gates_per_pkg` values are unverified — a wrong one yields a
  netlist that physically cannot be built.
- A **release checklist** a maintainer can actually follow, with the commands.

### 5. Make the unsigned state visible

An unsigned build must announce itself: in the release notes, in
`SHA256SUMS`'s accompanying text, and in what the workflow prints. A user
downloading an unsigned binary should learn that from the project, not from
their operating system's warning dialog.

## Files you own

`.github/workflows/release.yml`, `app/electron-builder.yml`,
`scripts/bundle_core.py`, `scripts/repro_check.py`, `scripts/version_check.py`,
`docs/RELEASING.md`, `CHANGELOG.md`, and new files under `docs/`.

## Off-limits — two other agents are in this repo right now

- `.github/workflows/ci.yml`, `app/tests/**` — the e2e agent.
- `scripts/bundle_toolchain.py`, `scripts/licence_audit.py`,
  `gatepack/toolchain.py`, `gatepack/doctor.py`, `Dockerfile*` — the toolchain
  agent. **You may call `licence_audit.py`; do not edit it.**
- `app/renderer/**`, `app/main/**`, `app/preload/**`, `app/shared/api.ts` —
  read-only, except `app/main/core.cts` if the Windows `.exe` resolution genuinely
  requires it; if so, keep the change minimal and say so in your notes.
- `docs/MILESTONE-AUDIT.md`, `gatepack-design.md`, `README.md` — inputs.
