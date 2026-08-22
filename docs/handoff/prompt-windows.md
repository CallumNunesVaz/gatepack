# Package D — a real way to run gatepack on Windows

Read `docs/handoff/delegation-rules.md` first. Every rule there applies.

## The task

Make it genuinely possible for someone on Windows to install and run gatepack.

## What already exists

More than you might expect. Check before you build:

* `app/electron-builder.yml` already has a `win:` target producing an **NSIS**
  installer, and its Authenticode block is already written correctly — it signs
  only if `WIN_CSC_LINK`/`CSC_LINK` are present, and fabricates nothing.
* `app/main/core.cts` already resolves `gatepack.exe` on `win32`
  (`binaryName()`), and `app/main/core.test.ts` already tests that.
* `app/build/icon.ico` exists.
* `scripts/bundle_core.py` and `scripts/bundle_toolchain.py` build the bundled
  core and toolchain.

## The actual blocker, which is not the installer

`app/resources/bin/` contains **Linux x86-64 ELF binaries** — `gatepack`,
`yosys`, `iverilog`, `vvp`, `sby`, `berkeley-abc`, plus `lib/` and
`x86_64-linux-gnu/`. On Windows every one of them is inert. An NSIS installer
built today would install cleanly, launch, and then report that every tool is
missing.

So the work is not "add a Windows target" — that exists. It is:

1. making the packaging path actually produce a Windows-usable app, and
2. making the *degraded* state honest and actionable, because for some users it
   will be the state they are in.

## The constraint that outranks the task

**You are on Linux. You cannot test a Windows installer.** Do not write, in
code comments, docs, or your notes, that something "works on Windows" when what
you mean is "this should work on Windows". Every claim must be labelled with
how it was established:

* **verified here** — you ran it on this machine and it did the thing;
* **verified by construction** — a unit test exercises the Windows code path
  with `platform: 'win32'`, the way `core.test.ts` already does;
* **unverified** — needs a Windows machine, and you say so plainly.

A section of your notes titled "what I could not verify" is a required
deliverable, not an apology. This project has shipped nine pieces of machinery
that reported a status while measuring nothing; an installer nobody has run is
the easiest possible way to ship a tenth.

**And no fabricated signing material.** No self-signed certificate presented as
real, no placeholder publisher identity, no invented certificate thumbprint. The
existing config's posture — sign if the secret is there, produce an unsigned
installer and say so if it is not — is correct. Keep it.

## What to build

### 1. A Windows core, or an honest account of why not

`scripts/bundle_core.py` freezes the Python core. Determine whether it can
produce a Windows executable from here (it almost certainly cannot — PyInstaller
does not cross-compile) and either make it work or document exactly what a
Windows machine or CI runner would have to do. A `windows-latest` job in
`.github/workflows/` is the realistic answer; wire it up even though you cannot
run it, and say it is unverified.

### 2. The toolchain story

Yosys, Icarus and sby are the hard part. On Windows the realistic options are
OSS CAD Suite, or WSL2. Work out which the app can actually detect and use, and
make `gatepack doctor` say something useful on Windows: not "yosys: missing" but
what it is for and where a Windows user gets it. `doctor` already reports tools
with their purpose — extend that, do not replace it.

### 3. A launcher

`./start` is the Linux entry point (`./start`, `./start dev`, `./start cli`,
`./start doctor`). Provide the Windows equivalent — `start.ps1` and/or
`start.cmd` — covering the same verbs. It must fail with a readable message when
a prerequisite is absent, never with a stack trace.

### 4. Documentation

A Windows section in the README or a `docs/` page: install, run, what works,
what needs WSL2, what is untested. Written for someone who has never seen this
repository.

## Your file scope — nothing outside it

* `app/electron-builder.yml`
* `app/main/**` (platform handling only — do not change the IPC contract)
* `start.ps1`, `start.cmd` (new)
* `scripts/bundle_core.py`, `scripts/bundle_toolchain.py`, `scripts/dependencies.json`
* `.github/workflows/**`
* `README.md` and/or `docs/WINDOWS.md` (new)
* `gatepack/doctor.py`, `tests/unit/test_doctor.py`
* `docs/BUILD-NOTES-windows.md`, `docs/handoff/notes-windows.md`

**Off-limits** (another agent is working there right now): `examples/**`,
`libraries/**`, `gatepack/examples.py`. Also always off-limits:
`app/shared/api.ts`, `gatepack-design.md`, `docs/*-FINDINGS.md`,
`docs/MILESTONE-AUDIT.md`, `docs/GUI-AUDIT.md`.

Do not touch `app/renderer/**` — a large amount of work landed there today.

## Acceptance

1. `.venv/bin/python -m pytest -q` — **723 pass, 5 skip** at baseline, still
   passing plus yours.
2. From `app/`: `npx tsc --noEmit -p tsconfig.main.json` clean, `npx vitest run`
   (**388 pass**) still green.
3. Unit tests that exercise the Windows code paths on this Linux host by passing
   `platform: 'win32'` — the pattern `app/main/core.test.ts` already uses. Every
   Windows behaviour that *can* be tested that way must be.
4. `python -m gatepack doctor --json` still valid, and a test pinning the
   Windows-specific guidance.
5. `scripts/lint_workflows.py` passes if it applies to what you changed.
6. Your notes contain a "what I could not verify" section naming every claim
   that needs a Windows machine.

## Output

`docs/BUILD-NOTES-windows.md` and `docs/handoff/notes-windows.md`: what you
implemented, what is verified here versus by construction versus unverified,
and the three things you are least confident about.
