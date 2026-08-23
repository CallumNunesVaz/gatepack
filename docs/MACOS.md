# Running gatepack on macOS

gatepack's core is pure Python and runs on macOS unchanged. The two things that
are different on macOS are **the desktop installer** and **the native EDA
toolchain** (Yosys, SymbiYosys, Icarus Verilog). This page says exactly what
works, what does not, and what nobody has verified yet.

## What works

- **The command-line core.** `python -m gatepack.cli` runs on macOS the same as
  on Linux: `compile`, `estimate`, `verify`, `build`, `simulate`, `examples`,
  `lib`, `project`, `doctor`. Everything up to the point where a tool must
  *run* is platform-independent.
- **`gatepack doctor` on macOS.** It reports each tool's purpose and — unlike
  the bare POSIX report — appends *where a macOS user gets it* (Homebrew for
  yosys, iverilog and z3; OSS CAD Suite for SymbiYosys). It never claims a tool
  is present when it is not.
- **A bundled macOS core.** `scripts/bundle_core.py` produces the `gatepack`
  binary when run *on macOS* (or the `macos-13` / `macos-14` CI runners). See
  below.
- **`./start`.** The Linux entry point is a bash script and is intended to run
  on macOS too (the BSD-userland differences were audited and removed). It is
  exercised on Linux, not on macOS; see the untested list.

## What does not work (and why)

- **The bundled toolchain.** `app/resources/bin/` is populated by
  `scripts/bundle_toolchain.py`, which extracts **Linux x86-64 ELF** binaries
  from the `gatepack-toolchain:m6` container. Those binaries are inert on
  macOS, so the script refuses to run on a non-Linux host with an explicit
  message. A macOS package ships **no** toolchain; the app reports each missing
  tool honestly.
- **PyInstaller cross-compiling.** PyInstaller builds only for the platform it
  runs on. You cannot produce the macOS `gatepack` binary from Linux or
  Windows; the build must run on a macOS machine (or a `macos-13`/`macos-14`
  GitHub Actions runner).

## Installing and running from source

You need Python 3.11+ and Node.js 20 (Node only if you want the desktop app).

First install the tools gatepack shells out to. The three that are in Homebrew:

```
brew install yosys z3
brew install icarus-verilog   # formula name not verified on a macOS host — see below
```

SymbiYosys (`sby`) is **not** in Homebrew; it ships in **OSS CAD Suite**
(`YosysHQ/oss-cad-suite-build`), a self-contained distribution with a macOS
build. Download it and put its `bin` directory on `PATH`.

Then:

```
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m gatepack.cli doctor
```

or use the launcher:

```
./start doctor       # what is installed, what is missing, where to get it
./start cli ARGS...  # the command-line core
./start              # the desktop application (needs `cd app` + `npm ci`)
./start dev          # the desktop app with renderer live-reload
```

`./start` creates the venv on a fresh clone, builds the app only when a source
file is newer than the build, and prints a readable message — never a stack
trace — when a prerequisite is missing.

## The toolchain on macOS

Synthesis and verification need Yosys, ABC, Icarus Verilog and SymbiYosys.

- **Yosys** — `brew install yosys`.
- **Icarus Verilog** (and its `vvp` runtime) — via Homebrew. The formula is
  `icarus-verilog`; that name is written from memory and **has not been verified
  on a macOS host**. If in doubt, search `brew search icarus`.
- **Z3** — `brew install z3` (reached indirectly through SymbiYosys's smtbmc
  engine).
- **SymbiYosys (`sby`)** — not in Homebrew. Install **OSS CAD Suite**
  (`YosysHQ/oss-cad-suite-build`) and put it on `PATH`.

Without those, `gatepack build` refuses to synthesise and tells you so — it
never invents a netlist. `gatepack doctor` reports each tool by name and
purpose, with the macOS install route appended.

## The desktop installer

`app/electron-builder.yml` has a macOS (dmg/zip) target and a correct signing
posture: it signs **only** when the Apple signing credentials are present, and
produces an **unsigned** build (and says so) when they are not. No certificate
or identity is fabricated. Building it needs a macOS host:

```
cd app
npm ci
npm run build
npx electron-builder --mac
```

`scripts/verify_signing.py` runs `codesign`/`spctl`/`stapler` over the signed
path, and the release matrix builds on `macos-13` (x64) and `macos-14` (arm64).
See `docs/RELEASING.md`.

## What is untested

Every macOS path in this repository is *written, not proven* until it has been
run on a real Mac. This page was written and tested on Linux only:

- `./start` has been **audited** for BSD-userland differences (GNU `find
  -quit`, GNU `grep -m`, `seq`) and those were removed, but it has **not been
  executed on macOS**.
- The `macos-13`/`macos-14` release-matrix entries and the signing/notarisation
  steps are **written but never executed here**.
- The `brew install icarus-verilog` formula name is **unverified** (best
  recollection); `yosys` and `z3` formula names are more certain but also not
  checked on this host.
- Whether an unsigned macOS build that ships no toolchain opens and reports the
  missing tools gracefully (rather than erroring) is **unverified**.
- The Homebrew- and OSS-CAD-Suite-installed toolchain has **not** been run
  through `gatepack verify`/`build` on macOS.

Treat every macOS path in this repository as *written, not proven* until it has
been run on a Mac.
