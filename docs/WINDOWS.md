# Running gatepack on Windows

gatepack's core is pure Python and runs on Windows unchanged. The two things
that are different on Windows are **the desktop installer** and **the native
EDA toolchain** (Yosys, SymbiYosys, Icarus Verilog). This page says exactly what
works, what does not, and what nobody has verified yet.

## What works

- **The command-line core.** `python -m gatepack.cli` runs on Windows the same
  as on Linux: `compile`, `estimate`, `verify`, `build`, `simulate`, `examples`,
  `lib`, `project`, `doctor`. Everything up to the point where a tool must
  *run* is platform-independent.
- **`gatepack doctor` on Windows.** It reports each tool's purpose and — unlike
  the POSIX report — appends *where a Windows user gets it* (OSS CAD Suite, or
  WSL2). It never claims a tool is present when it is not.
- **A bundled Windows core.** `scripts/bundle_core.py` produces `gatepack.exe`
  when run *on Windows* (or the `windows-latest` CI runner). See below.

## What does not work (and why)

- **The bundled toolchain.** `app/resources/bin/` is populated by
  `scripts/bundle_toolchain.py`, which extracts **Linux x86-64 ELF** binaries
  from the `gatepack-toolchain:m6` container. Those binaries are inert on
  Windows, so the script refuses to run on a non-Linux host. A Windows package
  ships **no** toolchain; the app reports each missing tool honestly.
- **PyInstaller cross-compiling.** PyInstaller builds only for the platform it
  runs on. You cannot produce `gatepack.exe` from Linux or macOS; the build
  must run on a Windows machine (or a `windows-latest` GitHub Actions runner).

## Installing and running from source

You need Python 3.11+ and Node.js 20 (Node only if you want the desktop app).

```
py -m venv .venv
.venv\Scripts\python -m pip install -e .
.venv\Scripts\python -m gatepack.cli doctor
```

or use the launcher:

```
start.ps1 doctor       # what is installed, what is missing, where to get it
start.ps1 cli ARGS...  # the command-line core
start.ps1              # the desktop application (needs `cd app` + `npm ci`)
start.ps1 dev          # the desktop app with renderer live-reload
```

`start.ps1` (or `start.cmd`, which just hands off to it) creates the venv on a
fresh clone, builds the app only when a source file is newer than the build,
and prints a readable message — never a stack trace — when a prerequisite is
missing.

## The toolchain on Windows

Synthesis and verification need Yosys, ABC, Icarus Verilog and SymbiYosys.
Two real options:

1. **OSS CAD Suite** (`YosysHQ/oss-cad-suite-build`) — a self-contained Windows
   distribution that includes Yosys and SymbiYosys. Put its binaries on `PATH`
   and `gatepack doctor` will find them.
2. **WSL2** — install the tools inside a Linux distribution and run gatepack
   there (`./start`, the Linux entry point, works as documented).

Without one of those, `gatepack build` refuses to synthesise and tells you so —
it never invents a netlist. This is deliberate.

## The desktop installer

`app/electron-builder.yml` already has an NSIS target and a correct Authenticode
posture: it signs **only** when `WIN_CSC_LINK`/`CSC_LINK` are present, and
produces an **unsigned** installer (and says so) when they are not. No
certificate or identity is fabricated. Building it needs a Windows host:

```
cd app
npm ci
npm run build
npx electron-builder --win nsis --x64
```

## What is untested

- The `windows-latest` CI job (`.github/workflows/ci.yml`) and the release
  matrix's `windows` entry are **written but never executed here**. They pin
  `gatepack.exe` naming and the `.exe`-aware environment scrub, but a real
  Windows runner has not run them.
- The NSIS installer has **not** been built or installed on a Windows machine.
- The `start.ps1` / `start.cmd` launchers have **not** been executed on Windows
  (PowerShell is unavailable on the Linux machine this repository is developed
  on). They follow the same verbs and prerequisites as `./start`, but every
  claim about them is "should work", not "verified".
- Whether an unsigned NSIS installer that ships no toolchain opens and reports
  the missing tools gracefully (rather than erroring) is **unverified**.

Treat every Windows path in this repository as *written, not proven* until it
has been run on a Windows machine.
