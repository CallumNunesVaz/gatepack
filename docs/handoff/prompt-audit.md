# Package: close out v0.1.0 — the licence audit, CI, and the release docs

You are a release engineer. Your instinct is that a green CI badge over
unexercised tests is worse than no badge, because it is a claim.

## The project

`gatepack` compiles a truth table or FSM specification into a bill of materials
and a schematic netlist built from discrete 74AUP logic packages, formally
verifying the result on every build. It is GPL-3.0-or-later, ships a Python core
and an Electron app together, and its distinguishing claim is that it never
reports a status it has not measured.

M18 (packaging, docs, v0.1.0) is the last milestone and is `partial`. Three
things stand between the tree and a release, all in your scope.

## 1. The licence audit does not see the bundled core

`scripts/licence_audit.py` audits the **npm dependency tree only**. As of
today, `scripts/bundle_core.py` produces `app/resources/bin/gatepack` — a
PyInstaller binary that ships inside the app and embeds CPython, pydantic and
PyInstaller's bootloader.

On a hand check those are PSF, MIT and GPL-2.0-with-bootloader-exception, all
GPL-3.0-compatible, so there is no known defect today. **That is exactly the
problem**: it was settled by hand, and the audit exists so licence questions are
not settled by hand. A future Python dependency that is incompatible would ship
unnoticed.

Extend the audit over the bundled core:

- Enumerate what the bundle actually contains — do not assume the declared
  dependency list is the shipped set; that assumption was already wrong once for
  the npm tree (`docs/BUILD-NOTES-licence2.md`).
- Resolve each component's licence and classify it against the existing `POLICY`
  table. Add licences to `POLICY` **by name, after review** — never by
  defaulting an unknown to compatible.
- Verify the PyInstaller bootloader exception yourself and record what you read.
  If GPL-3.0 compatibility turns on that exception, that is a fact the project
  must state, not infer.
- Make it fail. Construct a bundle component with an incompatible licence and
  confirm the audit rejects it; keep that as a test.

## 2. CI does not run the new tests

`.github/workflows/ci.yml` has three jobs: `test`, `toolchain`,
`desktop-packaging`. Several test files added recently are not exercised by any
of them:

```
tests/toolchain/test_core_bundle.py      needs PyInstaller
tests/toolchain/test_packaging.py        needs GATEPACK_PACKAGING=1
tests/toolchain/test_mcell_coverage.py   needs the toolchain image
tests/unit/test_doctor.py, tests/contract/test_doctor_contract.py
app/renderer/keys/registry.test.ts       and the rest of vitest
```

Work out which are genuinely covered and which only appear to be, then wire in
what is missing. The `toolchain` job already fails if a toolchain test *skips* —
apply the same principle to the bundle tests: a skipped test that should have
run is a false green.

**Report what you find before you fix it.** If a job is passing because its
tests skip, that is a finding worth writing down.

## 3. Release documentation

- `README.md`'s Status section is stale. It says packaging and signed installers
  do not exist, provenance coverage is not reported, and the GUI milestones have
  not been audited. All three are now wrong. Rewrite it against
  `docs/MILESTONE-AUDIT.md`, which is the honest record. **Do not edit the audit
  itself** — it is an input.
- `docs/RELEASING.md` — check every claim still holds after the core-bundling
  work, and add the bundle step to the release procedure in the right order.
- Write a `CHANGELOG.md` for v0.1.0 from the git history. What a user gets, not
  what the commits say.
- **The worked example** is an M18 exit criterion and does not exist: a
  walkthrough that takes the pelican showcase from specification to BOM,
  showing the real commands and the real output. Run every command you put in it
  and paste what actually came back. A walkthrough with invented output is worse
  than none.

Note: `./start` at the repo root is the entry point (`./start`, `./start dev`,
`./start cli ARGS`, `./start doctor`). Use it in the docs where it is the
simplest correct instruction.

## Files you own

`scripts/**`, `.github/**`, `README.md`, `docs/RELEASING.md`, `CHANGELOG.md`,
and new tests under `tests/`.

## Off-limits — three other agents are in this repo right now

`app/**` entirely (three agents are overhauling the GUI), `gatepack/**`,
`gatepack-design.md`, `docs/MILESTONE-AUDIT.md`, `docs/M0-FINDINGS.md`,
`docs/M6-FINDINGS.md`, `docs/GUI-AUDIT.md`.

If the licence audit needs a change in `app/` to be testable, describe it in
your notes instead of making it.
