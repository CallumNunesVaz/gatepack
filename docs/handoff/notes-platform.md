# notes-platform — Package J handoff

Short form for the next agent. Full detail in `docs/BUILD-NOTES-platform.md`.

## What landed

- `gatepack/doctor.py` — `windows_note` → `platform_notes: {win32, darwin}`;
  `_purpose()` appends `. On Windows:` / `. On macOS:` per platform; added
  `is_darwin()`. Windows text **byte-identical** (Windows tests pass unedited).
- `tests/unit/test_doctor.py` — darwin guidance pinned by `platform="darwin"`.
- `scripts/bundle_toolchain.py` — `refusal_reason(platform=)` refuses
  `darwin`/`win32` with actionable messages before any docker call; `--platform`
  flag; `host_is_linux()` removed.
- `tests/unit/test_bundle_toolchain.py` (new) — refusal on darwin/win32, none on
  linux, refusal-before-docker. *(New file: the scope list omitted a test file
  for bundle_toolchain despite acceptance §3 requiring one.)*
- `start` — three GNU-isms fixed (see below); verbs unchanged.
- `app/tests/e2e/contract-commands.spec.ts` (new) — fake ⊆ real, renderer ⊆ real,
  renderer ⊆ fake, + a "delete a command and it fails" proof test. The real CLI
  registry is enumerated by an inline `python -c` walk of
  `gatepack.cli._build_parser()` — **no `gatepack/cli.py` change** (out of scope).
- `app/tests/e2e/real-core-views.spec.ts` (new) — schematic netlist, provenance
  spine, analysis dashboard against the real core; **no `test.skip`** (throws).
- `docs/MACOS.md` (new), `README.md` macOS paragraph.
- `.github/workflows/ci.yml` and `scripts/dependencies.json` — **unchanged** (no
  wiring/dep needed; the e2e job already collects the specs and fails on skip).

## The GNU-ism audit (full)

`start` calls no other repo script; it shells out to `python3`/`pip`/`node`/
`npm`/`docker`/`id`/`find`/`grep`/`sed`/`head`/`sleep`/`mkdir`/`kill`.

| finding | location | disposition |
|---|---|---|
| `find … -print -quit` | `build_stale` | **fixed** → `find … -print \| head -n 1` |
| `grep -om1 'http://…'` | `start_dev` | **fixed** → `grep -o … \| head -n 1` |
| `seq 1 60` | `start_dev` | **fixed** → `for ((i = 0; i < 60; i++))` |
| `head -1` | `doctor` | portable, but changed to `head -n 1` |
| `readlink -f` / `realpath` / `sed -i` / `mktemp` / `grep -P` | — | **absent** (no change) |
| `set -euo pipefail`, `[[ ]]`, `sleep 0.5`, `sed -n`, `sed s///` | throughout | portable (bash 3.2) |

Not fixed (deliberate): the docker toolchain-container path is Linux-specific
by design and never triggers on macOS with Homebrew tools installed.

## Verification status

- **verified here**: `bash -n start`; `./start doctor`; pytest 853/5; vitest 423;
  tsc clean ×2; playwright 31 (incl. contract + real-core views);
  `lint_workflows.py`; the inline CLI-registry walk; `analyse`/`provenance`
  against seeded netlists.
- **by construction**: darwin guidance (`platform="darwin"`), bundle refusal
  (`platform` injection), the contract test's three-way enumeration + the
  delete-a-command proof.
- **unverified**: anything on a real Mac — `./start` under bash 3.2, the
  `icarus-verilog` formula name, the Homebrew/OSS-CAD-Suite toolchain running
  `verify`/`build`, and the macos-13/14 signing/notarisation path.

## Watch out for (seams I could not reach)

- **`./start` under macOS bash 3.2** — the fixes are correct against GNU
  semantics but nothing ran BSD `find`/`grep`/bash 3.2 here.
- **The contract test parses source with regex** — `case 'X':` / `sub === 'X'`
  in `fake-core.cjs` and `return ['cmd', …]` in `session.cts`. A structural
  rewrite of either would change what the parsers see without the test failing;
  deleting a *command* is still caught (that is what the proof test shows).
- **`brew install icarus-verilog`** is unverified; the doctor note deliberately
  says only "via Homebrew" for iverilog.

## Least confident

1. `brew install icarus-verilog` (unverified formula name).
2. `./start` actually working on macOS bash 3.2 (audited, not executed).
3. The contract test's regex-based enumeration of the fake/renderer source.
