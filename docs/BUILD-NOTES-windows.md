# BUILD-NOTES — Windows packaging, toolchain guidance, and launchers (Package D)

What I built, what I guessed, what is a placeholder, and what I could not verify.

## The claim this package makes

A Windows user can now install and run gatepack in one of two honest states:
with a toolchain (OSS CAD Suite on `PATH`, or WSL2) it fully works; without one
it degrades to a report that *names each missing tool, what it was for, and
where a Windows user gets it* — never "yosys: missing" with nothing after it,
and never a fabricated result.

## What I implemented

1. **`gatepack/doctor.py` — Windows-specific guidance.**
   - `ToolSpec` gains a `windows_note: str = ""` field.
   - `run_doctor(platform=None)` / `_probe_tool(spec, platform)` / `is_windows()`.
   - `_purpose()` appends `". On Windows: <note>"` to the `purpose` text **only
     when reporting for Windows**. The base purpose is untouched, and the JSON
     envelope keys are byte-identical to the POSIX report — so the contract test
     (`set(data) == {version, tools, resources, allToolsPresent}` and
     `set(tool) == {name, found, purpose, direct, path, version, source}`) holds
     unchanged. Only the text of `purpose` differs.
   - Guidance names real distributions: OSS CAD Suite for yosys/sby/z3, Icarus
     Verilog (MSYS2/official) for iverilog/vvp, and WSL2 for `bash` — the one
     thing a *native* Windows build can never provide, because sby runs its
     engine steps through `/usr/bin/env bash`.

2. **`scripts/bundle_core.py` — cross-compile refusal + injectable platform.**
   - `host_platform()`, and `binary_name(platform=None)` now accept an explicit
     platform so the Windows name is pinnable without monkeypatching `os.name`.
   - `build_core(platform=None)` refuses a foreign platform up front with a clear
     message (PyInstaller cannot cross-compile; build on a Windows runner — the
     release matrix already does). It never emits a host binary named
     `gatepack.exe`. Added a `--platform` CLI flag.

3. **`scripts/bundle_toolchain.py` — Linux-only guard.**
   - `host_is_linux()` and a `bundle()` guard that refuses non-Linux hosts with a
     message pointing at OSS CAD Suite / WSL2. This closes the failure mode the
     brief names: bundling Linux ELF binaries into a Windows installer that
     would then report every tool missing.

4. **Windows launchers — `start.ps1` + `start.cmd`.** `start.ps1` implements the
   four verbs (`app`, `dev`, `cli`, `doctor`, `help`), creates the venv on a
   fresh clone, fails with a readable message (never a stack trace) when a
   prerequisite is absent, and delegates the toolchain report to the core's own
   `gatepack doctor` (so the Windows guidance above is what `start.ps1 doctor`
   prints). `start.cmd` is a thin shim over `start.ps1`.

5. **CI — `.github/workflows/ci.yml` gains a `windows-core` job** that runs
   `bundle_core.py` and the bundled-core acceptance test on `windows-latest`.
   This is the only place the Windows core is exercised on a real Windows
   runner (the release matrix does it only on tag pushes).

6. **Docs — `docs/WINDOWS.md`** (install, run, what works, what needs OSS CAD
   Suite / WSL2, what is untested) and a short Windows section in `README.md`.

7. **`app/electron-builder.yml`** — a comment only, on the `win:` block, stating
   that the Windows installer ships the core but no native toolchain.

## What is verified here

- `scripts/bundle_core.py --platform win32` on this Linux host exits 1 with the
  cross-compile refusal (ran it).
- `python -m gatepack doctor --json` still emits a valid envelope with the exact
  contract keys (ran it).
- The Windows guidance is exercised on this POSIX host by passing
  `platform="win32"` to `run_doctor` — the same injectable-platform pattern
  `app/main/core.test.ts` uses for `core.cts` (`tests/unit/test_doctor.py`).

## What is verified by construction

- `binary_name("win32") == "gatepack.exe"`, `host_platform()` tracks `os.name`
  (`tests/unit/test_bundle_core.py`).
- `build_core(platform=<foreign>)` raises "cross-compile" before ever touching
  PyInstaller (`test_cross_compile_is_refused_not_silently_renamed`).
- The doctor Windows test asserts every EDA tool's guidance names a real
  distribution and the bash entry explains the WSL2 requirement.

## What I could not verify

This is the required list. Everything on it needs a real Windows machine.

- **`windows-core` CI job** (and the release matrix's `windows` entry) has never
  executed on a Windows runner. `tests/toolchain/test_core_bundle.py` uses
  `os.access(BUNDLE, os.X_OK)`, which on Windows is a no-op that returns true for
  any existing file — so its "executable" assertion is weaker on Windows than
  Linux. The `.exe` naming and `.exe`-aware scrub are pinned, but the actual
  build has not run.
- **`start.ps1` / `start.cmd` have never been executed on Windows.** PowerShell
  is unavailable on this host. Every claim about them is "should work". In
  particular: `Start-Process -FilePath "npm.cmd"` (the dev flow), `%*` argument
  forwarding through `start.cmd`, and `exit $LASTEXITCODE` propagation are all
  untested.
- **The NSIS installer has not been built or installed.** Whether an unsigned
  NSIS installer that ships no toolchain launches and reports the missing tools
  gracefully (rather than erroring) is unverified.
- **Whether OSS CAD Suite actually ships every tool I named it for.** I name
  OSS CAD Suite for yosys/sby/z3 (confident), but I have **not** confirmed it
  ships Icarus Verilog — for iverilog/vvp I pointed at MSYS2/official builds
  instead, deliberately, because I could not verify OSS CAD Suite includes them.
- **`gatepack/toolchain.py` bundled-tool resolution does not check `.exe`.**
  `resolve_tool` looks for `d / name` (no suffix); a frozen Windows core with a
  bundled `yosys.exe` would not find it. This file is **out of my scope**, so I
  did not fix it — but it is a real gap: the Windows core ships, and if someone
  ever bundles Windows tools beside it, resolution would miss them. Recorded
  here because it is the weakest seam between what I own and what I cannot touch.

## The three things I am least confident about

1. **`start.ps1`/`start.cmd`** — written blind, PowerShell semantics are
   unforgiving, and nothing here exercises them. `start.cmd`'s `%*` forwarding
   and the `npm.cmd` `Start-Process` are the most likely to be wrong.
2. **The `windows-core` CI job actually passing** — `os.access(X_OK)` on Windows
   and `subprocess.run(["gatepack.exe", ...])` resolving via a scrubbed `PATH`
   are the two spots I expect to bite first.
3. **Whether extending `purpose` (rather than adding a dedicated guidance field)
   is the right shape** — it is the only way to stay inside the pinned JSON
   contract without editing `api.ts`, but it means the renderer's `purpose`
   string carries Windows prose, and I could not check how `app/renderer` lays
   it out (off-limits for me).

## What I guessed

- The guidance wording ("OSS CAD Suite", "MSYS2 or an official build", "WSL2")
  is factual but not verified against the distributions' current contents.
- `start.ps1` mirrors `./start`'s verbs and prerequisites; the `dev` flow is the
  closest thing to a guess in it (background Vite + log-polling + Electron).
