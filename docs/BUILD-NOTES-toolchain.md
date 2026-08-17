# BUILD-NOTES — bundled native toolchain (§17.1)

What I built, what I guessed, what is a placeholder, and what I could not verify.

## What I implemented

A packaged gatepack can now **build and verify a design with no EDA software
installed**, because the toolchain ships beside the frozen core and the core
finds it there.

1. **`scripts/bundle_toolchain.py`** — pulls the pinned toolchain out of
   `gatepack-toolchain:m6` (the image every M0/M6 measurement was taken in) and
   lays it into `app/resources/`, recording per binary its provenance, version,
   SHA-256, and `ldd` closure in `app/resources/bin/toolchain-manifest.json`.
   The pinned versions are exactly what the project already measures against:
   **Yosys 0.23** (git `7ce5011c24b`) and **sby at
   `beb8b3c6e38ee716cd9771eb906c37684e83eab4`** — no version move, so
   `docs/M0-FINDINGS.md` / `docs/M6-FINDINGS.md` remain valid.

2. **`gatepack/toolchain.py`** — `resolve_tool()` follows the same precedence as
   `app/main/core.cts` for the core: `GATEPACK_TOOLS` (explicit dir), then the
   bundled directory (only when frozen, i.e. the packaged app), then `PATH`. A
   dev checkout running from source keeps using its **system** tools. `ToolchainRunner`
   now resolves the bare command name to the right copy and sets
   `LD_LIBRARY_PATH`/`PATH` so a bundled binary reaches its bundled libraries
   and its bundled siblings (sby → yosys-smtbmc → yosys/z3).

3. **`gatepack/doctor.py`** — reports **which copy** it found (`source`:
   `bundled`/`system`/`env`) plus the version, per tool. `sby` has no
   `--version`, so its version comes from the manifest (the pinned commit).

4. **`scripts/licence_audit.py`** — extended with `--require-toolchain` /
   `--toolchain`, auditing every file in `app/resources/` against the manifest,
   failing on an incompatible licence, a file the manifest does not name, and a
   manifest entry with no file behind it.

5. **Tests** — resolution precedence (unit), doctor `source` shape (unit +
   contract), the licence audit "make it fail" cases (unit + shell harness), and
   a two-halves acceptance test (`tests/toolchain/test_toolchain_bundle.py`).

## What ships, and its provenance + dynamic linking

| Binary | Licence | From | Links against (bundled) |
|---|---|---|---|
| `yosys` | ISC | Debian bookworm Yosys 0.23 | libstdc++, libreadline, libffi, libz, libtcl8.6, libgcc_s, libtinfo |
| `berkeley-abc` | BSD-style (UCB) | Debian bookworm berkeley-abc | libreadline, libbz2, libz, libstdc++, libgcc_s, libtinfo |
| `iverilog` | **GPL-2.0-or-later** | Debian Icarus Verilog 11.0 | (glibc only) |
| `vvp` | **GPL-2.0-or-later** | Debian Icarus Verilog 11.0 | libreadline, libstdc++, libgcc_s, libtinfo |
| `z3` | MIT | Debian z3 4.8.12 | libstdc++, libgcc_s |
| `sby` | ISC | sby @ pinned commit, frozen | (Python, frozen) |
| `yosys-smtbmc` / `yosys-witness` | ISC | Debian yosys package, frozen | (Python, frozen) |
| `share/yosys/` | ISC | Yosys techlibs + scripts | data |
| `x86_64-linux-gnu/ivl/` | GPL-2.0-or-later | Icarus support files (ivlpp, ivl, .tgt, .vpi) | data |

Every shared library in `bin/lib/` is the *resolved* target of the Debian
symlink (e.g. `libstdc++.so.6.0.30` copied as `libstdc++.so.6`), so nothing is a
dangling symlink. The glibc core set (libc, libm, ld-linux, …) is **not**
bundled — it is the interface to the running libc and cannot be shipped
portably. This is the "a binary that works because of a system library is not
bundled" rule applied to the loader itself, and it is the one documented
exception.

## Licences — checked against the source, not the list in the brief

I verified every licence against the actual package shipped, not the list in the
prompt:

* **Icarus Verilog** (`iverilog`/`vvp` + `x86_64-linux-gnu/ivl/*`): the Debian
  `copyright` file says "either version 2 of the License, **or (at your option)
  any later version**". That "or later" clause is what makes it compatible with
  this GPL-3.0-or-later app, and the audit classifies it as `GPL-2.0-or-later`
  (compatible) rather than `GPL-2.0-only` (incompatible). The "make it fail"
  test constructs a `GPL-2.0-only` toolchain and confirms the audit rejects it.
* **yosys / sby / yosys-smtbmc / yosys-witness** are ISC (read from the Debian
  `copyright` and sby's `COPYING`).
* **z3** is MIT (Expat).
* **berkeley-abc** is the "University of California, Berkeley" permissive licence
  (BSD-style); it bundles a few GPL-2+/MIT/BSD files as headers (Windows-only
  pthread shims, MiniSat/glucose sources) but is distributed under the UCB
  licence. Classified BSD-style per the existing `dependencies.json` "ABC"
  entry.
* Shared libraries: libstdc++/libgcc_s (GPL-3.0-or-later **with the GCC Runtime
  Library Exception**, which permits the link), libreadline (GPL-3.0-or-later),
  libtcl8.6 (Tcl licence, BSD-style), libffi/libtinfo (MIT), libz (zlib),
  libbz2 (bzip2).

GPL-2.0-only would block the release; nothing here is GPL-2.0-only.

## Sizes — honest numbers

| Platform | Core | Toolchain | Total |
|---|---|---|---|
| **Linux x86_64** | 14 MB | ~90 MB | **~104 MB** (bundled and verified) |
| macOS | 14 MB (core) | **not bundled** | core only — see below |
| Windows | 14 MB (core) | **not bundled** | core only — see below |

Linux breakdown (the only platform done this pass): `bin/` binaries + libs 81 MB
(z3 23 MB, berkeley-abc 16 MB, sby 11 MB, yosys-witness 11 MB, yosys 9.3 MB,
yosys-smtbmc 7.3 MB, `lib/` 4.8 MB, iverilog 60 KB, vvp 1.4 MB), `share/yosys/`
4.4 MB, `x86_64-linux-gnu/ivl/` 5.0 MB. The frozen Python drivers (sby,
yosys-smtbmc, yosys-witness) are the bulk of the non-z3/abc overhead — each
embeds its own CPython — the price of not shipping a separate Python runtime.

## What I could not verify, and what is weakest

* **espresso is NOT bundled.** The probe image (`Dockerfile.probe`) does not
  build it, and the reproducible `Dockerfile` (which builds
  `chipsalliance/espresso@0288253c…`) has never been built end to end, so there
  is no binary to extract and no licence to check against the actual source. It
  is only used by the not-yet-shipped async backend (v0.2), so `doctor` reports
  it as `found: false` (honest, not faked). Bundling it means first building and
  measuring the reproducible image.
* **macOS and Windows are not covered this pass.** The bundle is Linux x86_64
  only (glibc + ELF + Debian multiarch paths: `x86_64-linux-gnu/ivl`,
  `lib/*.so`). macOS/Windows need their own toolchain builds — different object
  formats, different dynamic loading, different paths — and are out of scope
  here. `electron-builder.yml` already lists macOS/Windows targets, so this is a
  coverage gap to name, not to hide: a packaged macOS/Windows app today still
  reports "4 tools missing" in `doctor`, exactly as it did before this work.
* **The `source` field, and a failed check's `detail`, are not yet shown by the
  GUI.** `app/shared/api.ts` and `app/main/envelope.cts` (read-only for me)
  validate IPC with zod schemas that strip unknown keys: `doctor`'s `source` is
  stripped, and `verify`'s `Check` type has no `detail` field for a failed
  check, so an sby ERROR's message reaches the CLI (`--json` `detail` key, the
  human output, and `manifest.json`) but not the renderer. Both are one-field
  additions in files I do not own.
* The Yosys share lookup (`<bin>/../share/yosys`) and the Icarus ivl lookup
  (`<bin>/../x86_64-linux-gnu/ivl`) are inferred from the binaries' Debian
  relocatable-patch behaviour (I confirmed the exact paths by moving the
  binaries and reading the `sh: …/ivlpp: not found` errors). They hold for the
  bundled Debian binaries; a different Yosys/Icarus build would need re-checking.
* `bundle_toolchain.py` requires the host to have `docker` + the `:m6` image and
  `PyInstaller`; it is a build-time tool, not a runtime dependency.

## Decisions made under review

* **A POSIX shell is a host requirement, not a bundled binary.** sby_core runs
  its engine steps through `/usr/bin/env bash -c …`, so it needs a `bash` on
  `PATH`. I chose *not* to bundle a shell: bash exists on essentially every
  Linux and macOS host, it is part of the base system (not an EDA tool), and
  bundling one would add a large, security-sensitive binary that interacts with
  the host in ways a self-contained toolchain should not. Two things make this
  honest rather than undiagnosed:
  1. `build_run_env` now sets `PATH` **explicitly** for a bundled tool — bundled
     dir first, then the inherited `PATH`, then `/bin:/usr/bin:/usr/local/bin` —
     rather than relying on inheritance, so a bundled sby finds `bash` even when
     the parent `PATH` is empty. Verified: the full `verify` (equivalence +
     exhaustive sim + mutation + a property that proves) now passes under
     `env -i` with no `PATH`.
  2. `gatepack doctor` reports `bash` as a checked dependency (a host
     requirement found by absolute path, `source: system`), like any other tool.
* **sby ERROR is now a failed check, not "unrecognized output".** sby exits
  rc=16 on ERROR; `parse_sby` now maps any non-0/non-2 exit to a `failed`
  `TaskResult` carrying sby's own message (`COMMAND NOT FOUND`, the failing
  engine step). `not_run` is reserved for "we did not attempt this" (tool
  missing). This closes the "a status reported by machinery that did not
  measure what it claims" failure mode the review caught. Tested both as a pure
  parse and end-to-end (z3 moved aside → `property …: failed` with the cause).

## What I guessed

* The three frozen Python drivers are frozen with the *host* PyInstaller
  (CPython 3.12) running the container's pure-Python sources (sby modules +
  click 8.1.3 from the container). This works in practice (the property check
  discharges), but it is not byte-identical to the container's CPython 3.11.
* The GCC runtime licence is recorded in the manifest with spaces
  ("GPL-3.0-or-later with GCC Runtime Library Exception"); the audit has both
  the space-normalised and the hyphenated POLICY keys.
