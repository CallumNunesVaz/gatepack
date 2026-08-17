# BUILD NOTES — signing, made real

Scope: `.github/workflows/release.yml`, `app/electron-builder.yml`,
`scripts/verify_signing.py`, `scripts/gpg_sign_sums.py`,
`scripts/sign_local.py`, `scripts/lint_workflows.py`,
`scripts/tests/test_workflows.sh`, `docs/RELEASING.md`, and new tests under
`tests/unit/` (`test_verify_signing.py`, `test_gpg_sign_sums.py`,
`test_sign_local.py`, `test_lint_workflows.py`).

## What I implemented

1. **Verification, not assumption** — `scripts/verify_signing.py`. Per platform:
   - macOS: `codesign --verify --deep --strict --verbose=2`, `spctl --assess
     --type execute`, `xcrun stapler validate`.
   - Windows: `signtool verify /pa /v`.
   - Linux: `sha256sum -c SHA256SUMS` (checksum coverage; Linux has no OS
     signing).
   The verdict is the *platform tool's* verdict; a missing tool is reported as
   `cannot verify` (exit 2), never substituted with a pass. Exit 0 = verified,
   1 = a check failed, 2 = cannot verify.

2. **Release workflow restructure** — `.github/workflows/release.yml`. The two
   paths are now structurally distinct, named steps (`Build installer —
   UNSIGNED …` / `Build installer — SIGNED + notarized`), each writing its own
   `$GITHUB_STEP_SUMMARY` banner. The signed path is followed by a `Verify
   signature` step that fails the job if `verify_signing.py` does not pass. The
   unsigned path writes `SIGNING-STATUS.txt` beside the artefacts. The publish
   job optionally GPG-signs `SHA256SUMS` and verifies Linux checksum coverage.

3. **Detached GPG signature** — `scripts/gpg_sign_sums.py`. Reads
   `GPG_PRIVATE_KEY` (armored) from the environment, imports it into an
   ephemeral `GNUPGHOME`, detach-signs `SHA256SUMS`, and **self-verifies** the
   signature before reporting success. Absent the key it announces a
   checksum-only release.

4. **Local signing** — `scripts/sign_local.py`. Reads credentials from the
   environment (never a repo file, never printed), runs the signed build, runs
   the same `verify_signing.py` as CI, and refuses to call a result "signed" it
   cannot verify.

5. **Workflow lint** — `scripts/lint_workflows.py` (self-contained YAML subset
   checker + structural checks over `release.yml`) and
   `scripts/tests/test_workflows.sh`. The lint is wired into the existing shell
   harness (`scripts/tests/run.sh`), so it runs in CI's `test` job with no new
   dependencies.

## What is proven vs what is merely wired (honest list)

The maintainer has **no signing credentials** and will ship **unsigned** for
0.1.0. So, with no credential and no macOS/Windows host:

- **Proven (run here, real tools):**
  - The verifier *fails* on an unsigned artefact and *passes* a signed one —
    via stub `codesign`/`signtool` tools that measure a signature marker, so the
    stub exercises the same discrimination the real tools do (an always-fail
    stub would pass the negative test and be worthless; the positive test is the
    one that catches that).
  - The verifier reports `cannot verify` (exit 2) when the platform tool is
    absent — never a fabricated pass.
  - Linux checksum coverage fails on a tampered artefact and on a missing entry
    (real `sha256sum`).
  - The GPG path produces and self-verifies a detached signature (real `gpg`,
    throwaway test key) and rejects a garbage key.
  - `sign_local.py` refuses without credentials and refuses on a failed
    verification.
  - The workflow lint rejects broken YAML and a workflow missing its
    verification/marker steps; the committed workflows lint clean.
  - The unsigned path's markers still surface: `assemble_release.py` turns
    `SIGNING-STATUS.txt` into `SHA256SUMS.txt`/release-notes banners (pinned by
    the pre-existing `tests/unit/test_assemble_release.py`).

- **Wired but unexercisable until a credential exists:**
  - Real `codesign`, `spctl`, `xcrun stapler`, `signtool` invocation — these run
    only on macOS/Windows runners, with a real certificate. The argv is
    constructed and unit-tested; the actual Apple/Microsoft verdict is not.
  - Real notarisation and stapling by electron-builder.
  - The release workflow job graph has never executed on GitHub.

## Test counts

```
before this work (reviewer's baseline):     637 passed, 5 skipped
after (full suite, this box):               664 passed, 5 skipped, 1 failed
```

The `1 failed` is **not** this scope and **not** introduced here:
`tests/toolchain/test_toolchain_bundle.py::test_bundled_toolchain_builds_pelican_under_scrubbed_env`
now fails because `libraries/74aup.csv` maps AND2/OR2 to the multi-gate parts
`74AUP2G08`/`74AUP2G32` with `gates_per_pkg=2` that is still marked *unverified*
(the pelican build refuses without `allow_unverified_gates_per_pkg`).
`libraries/**` and `examples/**` are the showcase agent's scope and are
off-limits here; the multi-gate datasheet verification is their in-flight work.

My new tests, each built so it *can* fail:

- `tests/unit/test_verify_signing.py` (12) — unsigned rejected / signed
  accepted (stub tools), missing-tool = cannot-verify, real-sha256sum Linux
  coverage pass/fail-on-tamper/fail-on-missing, argv construction, verdict
  classification.
- `tests/unit/test_gpg_sign_sums.py` (4) — real-gpg sign + self-verify, garbage
  key rejected, absent key announced, missing-sums-file error.
- `tests/unit/test_sign_local.py` (8) — platform mapping, cred detection lists
  names-not-values, verify_command mapping, refusal on missing creds / failed
  verification.
- `tests/unit/test_lint_workflows.py` (8) — real workflows lint clean, broken
  indentation/tab/unbalanced-bracket caught, block-scalar content preserved,
  structural checks flag a missing verify/marker step.

## Guesses / placeholders / weakest parts

1. **macOS notarisation verification target.** `verify_signing.py macos` runs
   `stapler validate` against the `.dmg` when one is passed, else the `.app`.
   Whether electron-builder staples the `.app` or only the `.dmg` is something I
   could not observe (no macOS runner). If `stapler validate` fails on a
   correctly-notarised app, the fix is to staple/validate the artefact
   electron-builder actually submitted — the workflow already passes the `.dmg`
   first, which is the artefact users download. Flagged, not asserted.
2. **`gh release create` is not idempotent** (carried over from prior notes) — a
   re-run of an existing tag fails. Not addressed; documented in RELEASING.md.
3. **The workflow lint is a subset parser.** It handles the YAML these workflows
   actually use (block mappings/sequences, flow collections, quoted scalars,
   `|`/`>` block scalars, `${{ }}`). It would not catch a workflow that later
   starts using anchors/aliases or more exotic YAML; if a future edit uses those,
   the lint will *reject* the file (fail closed) rather than silently pass —
   which is the safe direction.4. **`sign_local.py`'s `build_signed` is untested end-to-end** (it shells out to
   electron-builder with real credentials, which I cannot run). Its logic —
   which secrets are required, that missing secrets refuse, that a failed
   verification refuses — is tested; the subprocess wiring is not exercised.
5. **The stub-tool tests rely on `grep` being on the stub's PATH.** The test
   prepends (not replaces) PATH so the stubs can measure; a host without `grep`
   would skip nothing but would fail those two tests — acceptable, since `grep`
   is present on every CI runner and this box.

5. **`signtool` may not be on `PATH` on the Windows runner.** The Windows verify
   step calls `signtool verify /pa /v` by bare name; on `windows-latest` the
   Windows SDK ships `signtool.exe` but it is not guaranteed on `PATH` in a bash
   step. `verify_signing.py windows --signtool <path>` lets the workflow pin it,
   and a truly absent signtool is reported as "cannot verify" (exit 2) — which is
   the correct, fail-closed answer, but means a signed Windows release would fail
   its own verification if the tool is not discoverable. This is the single most
   likely first-signing-run surprise and is flagged rather than papered over with
   speculative, untested SDK-path lookups.

## What I could not verify (and did not fake)

- Any real code signature, notarisation ticket, or Authenticode chain. No
  credential exists, and none was fabricated (the rule: no self-signed
  certificate presented as real, no placeholder Team ID, no invented identity).
- The release workflow executing on GitHub. Both YAML files parse and every
  command the workflow runs was run individually on this Linux box, but the job
  graph (macOS/Windows runners, secret injection) has never executed.
