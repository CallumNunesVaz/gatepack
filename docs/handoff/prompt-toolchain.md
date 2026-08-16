# Package: bundle the native toolchain so a packaged app can actually build

You are a release engineer who has shipped native binaries inside desktop
applications and knows that the hard parts are dynamic linking, per-platform
provenance, and licence obligations — not the download.

## The project

`gatepack` compiles a truth table or FSM specification into a bill of materials
and a schematic netlist built from discrete 74AUP logic packages, and formally
verifies the result on every build. It is GPL-3.0-or-later. Its central claim is
that the emitted netlist is *formally proven* equivalent to the specification —
so the tools that do the proving are not optional extras, they are the product.

## The gap

The Python core now ships inside the app: `scripts/bundle_core.py` produces a
self-contained PyInstaller binary at `app/resources/bin/gatepack`, and
`app/main/core.cts` prefers it. Verified under `env -i` with no Python and no
`PATH`.

But the core shells out to **yosys, sby, iverilog, vvp, z3 and espresso**, and
none of those ship. On a machine without them, `gatepack doctor` correctly
reports "4 tools missing" and `gatepack build` refuses with "synthesis
unavailable … (never faked here)". Honest, and useless: an installed gatepack
cannot do the thing gatepack is for.

Close it. A user who installs the app must be able to build and verify a design
with no other software installed.

## What to build

### 1. A toolchain bundler

`scripts/bundle_toolchain.py`, alongside the existing core bundler and in the
same style — into `app/resources/bin/` (already `asarUnpack`ed and gitignored;
`electron-builder.yml` carries the `extraResources` entry).

Per binary, work out and document: where the build comes from, how it is
verified (checksum against a published artefact, or built from pinned source),
and what it dynamically links against. **A binary that works on your machine
because of a system library is not bundled** — check with `ldd`, and either
bundle the libraries alongside or link statically.

Pin versions to what the project already measures against:
`Dockerfile.probe` builds **Yosys 0.23**, and sby is pinned to commit
`beb8b3c6e38ee716cd9771eb906c37684e83eab4` because no tagged release matches
Yosys 0.23. `docs/M0-FINDINGS.md` and `docs/M6-FINDINGS.md` record what was
measured against those versions and **override the design document where they
disagree**. A different Yosys version invalidates those findings, so if you must
move, say so loudly rather than quietly.

Note `sby` is Python and `z3` may be reachable as a Python wheel — those two may
be far easier than the C++ ones. Solve the easy ones properly rather than
holding the whole package hostage to the hardest.

### 2. Teach the core to find them

`gatepack/toolchain.py` resolves tools on `PATH`. It must prefer the bundled
copies when running inside the packaged app, without breaking a development
checkout that uses system tools. Follow the resolution order
`app/main/core.cts` already establishes for the core itself (explicit env var,
then bundled, then system) and make the precedence testable.

`gatepack/doctor.py` must report **which copy** it found — bundled or system —
and its version. A user debugging a wrong result needs to know which yosys ran.

### 3. Licences — this is the part that can actually block a release

Each binary is a separate work with its own licence, and they now ship inside a
GPL-3.0 application. Yosys is ISC, sby is ISC, Icarus is **GPL-2.0-or-later**,
z3 is MIT, espresso varies by distribution — **check every one yourself against
the actual source you bundle; do not trust this list.**

GPL-2.0-only would be incompatible with GPL-3.0. If Icarus turns out to be
GPL-2.0-or-later the "or later" is what saves it, and that is a fact to state
explicitly, not infer. Where a licence requires it, ship the licence text and
the written offer for source.

`scripts/licence_audit.py` already audits the npm tree and the bundled Python
core (`--require-bundle`). **Extend it over the bundled binaries too**, and make
it fail: construct a bundled binary with an incompatible licence and confirm the
audit rejects it. Keep that as a test.

### 4. Be honest about size

These binaries are large. Report the installed size before and after, per
platform, in your notes. If it is 300 MB, say 300 MB. If you conclude a
platform cannot be done in this pass, **say which and why** — a partial bundle
that is honest about its coverage is a good outcome; a stub that pretends is
not, and this project refuses to fake tool results anywhere else.

### 5. Prove it

The acceptance test is the same shape as the core bundle's, and both halves
matter: with the toolchain bundled, a **scrubbed environment** (`env -i`, no
`PATH`, nothing installed) must run `gatepack build` on the pelican showcase and
produce the same 20-package BOM the toolchain container produces. Then move the
bundled binaries aside and confirm the same invocation *fails* — without that,
a host yosys answering the call would prove nothing.

## Files you own

`scripts/bundle_toolchain.py` and `scripts/licence_audit.py`,
`gatepack/toolchain.py`, `gatepack/doctor.py`, `Dockerfile*`, and new tests
under `tests/`.

## Off-limits — two other agents are in this repo right now

- `.github/workflows/ci.yml`, `app/tests/**` — the e2e agent.
- `app/electron-builder.yml`, `docs/RELEASING.md`, `CHANGELOG.md`,
  `.github/workflows/release.yml`, `scripts/bundle_core.py` — the release agent.
  If `bundle_core.py` needs a change, describe it in your notes.
- `app/renderer/**`, `app/main/**`, `app/shared/api.ts` — read-only.
- `docs/MILESTONE-AUDIT.md`, `gatepack-design.md`, `docs/M0-FINDINGS.md`,
  `docs/M6-FINDINGS.md` — inputs.
