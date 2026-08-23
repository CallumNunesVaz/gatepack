# BUILD-NOTES — macOS runtime story + e2e fake/real command contract (Package J)

What I built, what I guessed, what is a placeholder, and what I could not
verify. All claims below are labelled **verified here** (ran on this Linux
host), **verified by construction** (a unit/e2e test exercises the non-Linux
path by injection), or **unverified** (needs a Mac, or a tool I cannot run).

## The claim this package makes

1. A macOS user now has the same honest runtime story a Windows user already
   had: `gatepack doctor` names each missing tool, what it was for, and *where
   a macOS user gets it*; `docs/MACOS.md` explains install/run/untested; and
   `scripts/bundle_toolchain.py` refuses on macOS with an actionable message
   instead of silently assuming Linux.
2. The e2e suite no longer trusts a fake that can answer commands the real CLI
   does not have. A contract test enumerates the fake, the renderer and the
   real CLI registry and fails if they drift — the exact seam that produced the
   three dead views in `docs/GUI-AUDIT.md` — and the three views now have
   real-core regression tests that fail (not skip) when the core is missing.

## Part 1 — macOS

### What I implemented

1. **`gatepack/doctor.py` — `windows_note` generalised to `platform_notes`.**
   `ToolSpec.platform_notes: dict[str, str]` (keyed by `sys.platform`) replaces
   `windows_note`. `_purpose()` looks up the note for the reported platform and
   appends `". On {Windows|macOS}: <note>"`. The **Windows text is byte-identical
   to before** (verified: the Windows doctor tests pass unedited). Added
   `is_darwin()`, exported it, and kept `is_windows()`.

2. **Real macOS guidance per tool.** yosys → `brew install yosys` (confident);
   z3 → `brew install z3` (confident); iverilog → "via Homebrew" (the formula
   name `icarus-verilog` is *not* asserted — see "least confident"); sby → OSS
   CAD Suite (`YosysHQ/oss-cad-suite-build`), which ships SymbiYosys (confident
   it is the route; no Homebrew formula is claimed); vvp ships with Icarus;
   bash is already on macOS (`/bin/bash`); espresso stays "build from source".

3. **`scripts/bundle_toolchain.py` — per-platform refusal, by injection.**
   `refusal_reason(platform=None)` returns `None` on Linux and an actionable
   message on `darwin`/`win32` (naming Homebrew + OSS CAD Suite for macOS, OSS
   CAD Suite + WSL2 for Windows). `bundle(platform=...)` raises it before any
   docker call, and `main()` gained a `--platform` flag. The previous
   `host_is_linux()` + inline Windows-only message is gone (superseded).

4. **`start` — GNU-ism audit.** Full findings below.

5. **Docs.** `docs/MACOS.md` (mirrors `docs/WINDOWS.md`) and a macOS paragraph
   in `README.md`.

### The GNU-ism audit (findings in full)

I read `start` top to bottom and every command it spawns (it calls no other
repo shell script — only `python3`/`pip`/`node`/`npm`/`docker`/`id`/`find`/
`grep`/`sed`/`head`/`sleep`/`mkdir`/`kill`). Findings, then disposition:

1. **`find … -print -quit`** (`build_stale`) — `-quit` is GNU-only; BSD/macOS
   `find` errors on it, which (with the error suppressed) made the stale check
   silently always-report "not stale" on macOS. **Fixed**: `find … -print 2>/dev/null | head -n 1`.
2. **`grep -om1 'http://…'`** (`start_dev`) — `-m` is GNU-only; BSD `grep`
   rejects it, so `start dev` could never find the Vite URL on macOS.
   **Fixed**: `grep -o '…' | head -n 1`.
3. **`seq 1 60`** (`start_dev`) — `seq` is a GNU coreutils tool absent from
   macOS (which has `jot`). **Fixed**: bash arithmetic `for ((i = 0; i < 60; i++))`.
4. **`head -1`** (`doctor`) — portable on both BSD and GNU, but changed to
   `head -n 1` for clarity and POSIX-safety.
5. **Checked and left alone (portable):** `readlink -f` — **absent** (root is
   resolved via `cd … && pwd`); `realpath` — absent; `sed -i` — absent (only
   `sed -n` / `sed s///`, portable); `mktemp` — absent; `grep -P` — absent;
   `set -euo pipefail` (pipefail is bash 3.0+, macOS ships 3.2); `[[ … ]]`
   pattern matching (bash 3.2); `sleep 0.5` (BSD sleep accepts fractional).

A near-miss worth recording: my first attempt at replacing `seq` used
`for ((_ = 0; _ < 60; _++))`, which is **broken in bash** — `_` is the special
last-argument variable and the C-style loop misbehaved (hang / `syntax error
in expression`). Caught by actually running the loop, not by `bash -n`. Fixed
to use `i`. This is exactly the class of defect the "run the real thing" rule
exists for.

### What I could not verify (macOS — required list)

- **`./start` has not run on macOS.** I removed the three BSD-hostile
  constructs and `bash -n` + `./start doctor` pass here, but that is Linux bash
  5.x, not macOS bash 3.2. This is the single weakest claim in the whole
  package.
- **The `brew install icarus-verilog` formula name** is written from memory and
  unverified; `yosys`/`z3` names are more certain but also unverified on this
  host. I deliberately wrote "via Homebrew" (no formula) in the doctor note for
  iverilog, and flagged the name in `docs/MACOS.md`.
- **The Homebrew/OSS-CAD-Suite toolchain has not run `verify`/`build`** on
  macOS, and I have not confirmed OSS CAD Suite's current macOS build contents.
- **The `macos-13`/`macos-14` release-matrix entries and signing/notarisation**
  (in `docs/RELEASING.md`, which is correct and untouched) have never executed
  here.
- **`grep -o` on BSD `grep`** — I used it in `start_dev`; `-o` is supported by
  BSD grep, but I could not run BSD grep to confirm the exact `[0-9]*` match
  semantics against a Vite log line.

## Part 2 — the e2e fake/real contract

### What I implemented

1. **`app/tests/e2e/contract-commands.spec.ts` (new).** Enumerates, live:
   - the commands the **fake** answers (parsed from `fake-core.cjs`'s
     `case 'X':` switch and its `sub === 'X'` project/lib/examples dispatch);
   - the commands the **renderer** invokes (parsed from `session.cts`'s
     `buildCommandArgs` returns + its raw `project` verbs);
   - the commands the **real CLI** registers — by spawning `.venv/bin/python`
     with an inline script that walks `gatepack.cli._build_parser()`'s
     subparsers. This is done **inline in the test** (no `gatepack/cli.py`
     change, which is outside this package's file scope); the walk is derived
     from the parser, not a hand-copied list, so deleting a command from the
     registry removes it here too.
   Then asserts: fake ⊆ real, renderer ⊆ real, renderer ⊆ fake. Runs in
   ~100 ms with no Electron and no toolchain. A fourth test deletes
   `mapped-netlist` from the real registry and watches `diff(fake, real)`
   flag it — the "delete a command and watch it fail" proof that the check is
   not vacuous.

2. **`app/tests/e2e/real-core-views.spec.ts` (new).** The three views that were
   dead, driven against the real core with no `test.skip`:
   - **schematic netlist** — seeds `mapped.json`+`packed.json`, opens the
     Schematic view, asserts `schematic-svg svg` renders and no `schematic-error`;
   - **linked-selection spine** — seeds the committed `xor2` provenance
     fixtures (`premap.json`/`mapped.json`/`post_abc.json`), asserts
     `provenance()` returns `output_logic.y → y_int` with `confidence: exact`
     and `coverage > 0`;
   - **analysis dashboard** — seeds `mapped.json`+`cells.lib`+`generated.v`,
     opens Analysis and runs it, asserts the stuck-at classification renders
     and no `analysis-error`.

### Why I did not change `.github/workflows/ci.yml` or `scripts/dependencies.json`

Both were in scope, and I concluded neither needs a change:

- The e2e specs are all collected by the existing `e2e` job (Playwright picks
  up `app/tests/e2e/*.spec.ts`), which already installs the core
  (`pip install -e .`) and already treats a skip as a failure (greps its log for
  "skipped"). The new specs never skip — they throw — so no wiring is needed.
- The `test` job already runs the new `tests/unit/test_{doctor,bundle_toolchain}.py`
  tests. `scripts/lint_workflows.py` passes on the unchanged workflows.
- `scripts/dependencies.json` declares *dependencies*, and no new dependency was
  added (the macOS guidance is prose, not a shipped library).

### A note on file scope

The brief's scope list names `scripts/bundle_toolchain.py` but no test file for
it, while acceptance §3 requires "a test that `bundle_toolchain` refuses on
darwin and on win32 … and still works on linux". I therefore added a new
`tests/unit/test_bundle_toolchain.py` (mirroring the existing
`tests/unit/test_bundle_core.py`); it is the only file outside the literal scope
list, and it is needed to make that acceptance check non-vacuous. The CLI-registry
enumeration is done *inline in the e2e test* so that no `gatepack/cli.py` change
(also outside scope) was required.

## Test counts

| suite | before | after |
|---|---|---|
| pytest | 845 pass / 5 skip | **853 pass / 5 skip** |
| vitest | 423 pass | **423 pass** |
| playwright e2e | 24 pass | **31 pass** |
| tsc (renderer + main) | clean | **clean** |

## The three things I am least confident about

1. **The `brew install icarus-verilog` formula name** — written from memory and
   unverified on a Mac; I kept it out of the doctor note ("via Homebrew") but it
   is the one thing a macOS user is most likely to paste and have fail.
2. **`./start` on macOS bash 3.2** — the audit is real and the fixes are
   correct against GNU semantics, but I could not run macOS `find`/`grep`/bash
   3.2, so "should work on macOS" is exactly what it is.
3. **The contract test's source-parsing** — enumerating the fake/renderer
   commands is regex over `fake-core.cjs`/`session.cts`; a structural rewrite of
   either (not a deleted command) could quietly change what the parsers see
   without the test failing. The `case 'X':` / `sub === 'X'` shapes are the
   weak seam.

## What I guessed

- The macOS guidance wording (Homebrew / OSS CAD Suite) is factual but not
  verified against those distributions' current contents.
- `docs/MACOS.md`'s "what is untested" list is the honest version of "should
  work"; nothing there has been run on a Mac.
