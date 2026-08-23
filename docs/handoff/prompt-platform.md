# Package J — macOS gets the same honesty Windows got, and e2e stops trusting a fake

Read `docs/handoff/delegation-rules.md` first. Every rule there applies.

## Two unrelated gaps, both about the same thing

Each is a place where the project's status is better than its evidence.

---

## Part 1 — macOS has a release path and no runtime story

`docs/RELEASING.md` covers macOS thoroughly: the release matrix builds on
`macos-13` (x64) and `macos-14` (arm64), signing and notarisation are wired
credential-free, `scripts/verify_signing.py` runs `codesign`/`spctl`/`stapler`
on the signed path. That half is in good shape.

The runtime half does not exist:

* There is no `docs/MACOS.md`. `docs/WINDOWS.md` was written for someone who has
  never seen this repository; macOS users get nothing.
* `README.md` does not mention macOS at all.
* `gatepack/doctor.py` grew a `windows_note` per tool and an injectable
  `platform` argument so the Windows guidance is *testable on this Linux host*
  (`is_windows(platform)`, `_purpose(spec, platform)`). There is no equivalent
  for darwin, so a macOS user with no yosys is told "missing" and nothing else.
* `scripts/bundle_toolchain.py` sources every binary from the Debian-based
  `gatepack-toolchain:m6` image. On macOS there is no bundled toolchain at all,
  and nothing says so.

### What to build

1. **Generalise the doctor's platform note** from a Windows special case to a
   per-platform table — `windows_note` becomes something like
   `platform_notes: {"win32": ..., "darwin": ...}`, keeping the existing Windows
   text and behaviour byte-identical. The existing Windows tests must still
   pass unchanged; if they need editing, you have changed behaviour, so stop and
   say so.
2. **Real macOS guidance per tool.** yosys, iverilog and z3 are in Homebrew;
   sby ships in OSS CAD Suite. Name the actual route for each tool. Do not
   invent a formula name you are not sure of — if you are unsure, say "via
   Homebrew" without a specific formula rather than guessing a string a user
   will paste into a terminal. **State which of these you are confident about
   and which you are not.**
3. **`docs/MACOS.md`**, mirroring `docs/WINDOWS.md`: install, run, what works,
   what needs a manually installed toolchain, what is untested. Written for
   someone who has never seen this repository.
4. **`scripts/bundle_toolchain.py` must refuse on darwin and win32** the way
   `scripts/bundle_core.py` already refuses to cross-compile — an explicit,
   actionable refusal naming what a macOS machine would have to do, not a silent
   Linux-only assumption. Test it by injection.
5. **Audit `./start` for GNU-isms.** It is the Linux entry point and it is bash,
   so it *may* already work on macOS — or it may use `readlink -f`, `sed -i`
   without an argument, `realpath`, `mktemp -d -t` in the GNU form, or
   `grep -P`, every one of which behaves differently or not at all on BSD
   userland. Read it and every script it calls, list what you find, and fix what
   is safely fixable. This is a real check you can perform completely on this
   host, and it is worth more than the documentation.

### The constraint that outranks the task

**You are on Linux. You cannot test anything on macOS.** Label every claim:

* **verified here** — you ran it on this machine and it did the thing;
* **verified by construction** — a unit test exercises the darwin path with
  `platform: 'darwin'`, the way the Windows tests already do;
* **unverified** — needs a Mac, and you say so plainly.

A section titled "what I could not verify" is a required deliverable, not an
apology. Do not write that something "works on macOS" when you mean "this should
work on macOS".

---

## Part 2 — the e2e suite mostly drives a fake

`app/tests/e2e/` runs Playwright against the real Electron main process, but
most specs use a hermetic fake core (`app/tests/e2e/fake-core.cjs`); only the
GUI-audit regressions use the real Python core.

That split is reasonable for speed, and it is also the exact shape of the defect
that produced `docs/GUI-AUDIT.md`: **the renderer was wired to three core
subcommands that did not exist** (`mapped-netlist`, `provenance`, `analyse`).
Every test passed, because every test asked a fake. Three views were dead in the
real application.

### What to build

A **contract test between the fake and the real core**, which is the general fix
rather than a patch for those three commands:

* enumerate every command the fake answers;
* enumerate every command the real CLI registers;
* assert the fake answers **no command the real core does not have**, and that
  every command the renderer invokes exists in both.

That would have caught the original defect on the day it was introduced, and it
runs in milliseconds without the real toolchain.

Then extend the real-core e2e coverage to the views that were dead: the
schematic's netlist, the linked-selection spine, and the analysis dashboard —
against the real core, marked so a skip is a failure.

**A skip is not a pass.** If the real core is unavailable in an environment, the
test must fail there rather than quietly skip, for the same reason the
`toolchain` CI job greps its own log for "skipped".

---

## Your file scope — nothing outside it

* `gatepack/doctor.py`, `tests/unit/test_doctor.py`
* `scripts/bundle_toolchain.py`, `scripts/dependencies.json`
* `start` (portability fixes only — do not change what the verbs do)
* `docs/MACOS.md` (new), `README.md` (the macOS paragraph only)
* `app/tests/e2e/**`
* `.github/workflows/ci.yml`
* `docs/BUILD-NOTES-platform.md`, `docs/handoff/notes-platform.md`

**Off-limits**: `app/renderer/**` and `app/main/**` (other agents are there),
`app/shared/api.ts`, `gatepack/emit/**`, `gatepack/verify/**`,
`gatepack/synth/**`, `libraries/**`, `examples/**`, `docs/WINDOWS.md` and
`docs/RELEASING.md` (they are correct; do not rewrite them). Also always
off-limits: `gatepack-design.md`, `docs/*-FINDINGS.md`,
`docs/MILESTONE-AUDIT.md`, `docs/GUI-AUDIT.md`.

## Acceptance

1. `.venv/bin/python -m pytest -q` — **749 pass, 5 skip** at baseline, all still
   passing plus yours. The existing Windows doctor tests pass **unedited**.
2. A test pinning the darwin guidance, exercised by injection on this host.
3. A test that `bundle_toolchain` refuses on darwin and on win32 with an
   actionable message, and still works on linux.
4. The fake/real command contract test, proven by deleting a command from the
   CLI registry in the test and watching it fail.
5. From `app/`: `npx vitest run` (**388 pass**), both `tsc` configs clean,
   `DISPLAY=:1 npx playwright test --config playwright.config.cjs` (**24 pass**,
   after `npm run build:main && npx vite build`) plus whatever you add.
6. `scripts/lint_workflows.py` passes on any workflow you change.

## Output

`docs/BUILD-NOTES-platform.md` and `docs/handoff/notes-platform.md`: what you
implemented, the GNU-ism audit's findings in full (including the ones you did
not fix), what is verified here versus by construction versus unverified, and
the three things you are least confident about.
