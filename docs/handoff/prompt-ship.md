# Package: M18 — make the core actually ship inside the app

You are a release engineer who has shipped Electron applications with a native
sidecar process before, and who has been burned by "it works on my machine"
more than once.

## The project

`gatepack` compiles a truth table or FSM specification into a bill of materials
and a schematic netlist built from discrete 74AUP logic packages, and formally
verifies the result on every build. The Python core is the whole product; the
Electron app in `app/` is strictly a view over artefacts the CLI produces
(§5 of `gatepack-design.md`). The app never reimplements logic — it spawns the
CLI and renders what comes back.

## The defect

**A packaged gatepack does not contain gatepack.**

`app/main/core.cts` resolves the core in this order:

1. `$GATEPACK_CORE`
2. `app/resources/bin/gatepack` — §17's reserved location for the bundled core
3. `.venv/bin/gatepack` relative to the project root
4. `gatepack` on `PATH`

Nothing populates step 2. `app/electron-builder.yml` already has the
`extraResources` and `asarUnpack` entries pointing at `app/resources/`, and they
are inert because that directory does not exist. So an installed app finds the
core only if the user happens to have a gatepack dev checkout or a pip install
on the same machine — which is to say, it works for you and for nobody else.

`docs/RELEASING.md` states this honestly under "The core does not ship yet".
Your job is to make that sentence untrue, and to update it.

## What to build

### 1. A core bundler

`scripts/bundle_core.py` — produce a self-contained core at
`app/resources/bin/gatepack` that runs with **no Python, no venv and no
gatepack on the host**.

PyInstaller is the obvious tool. Use it if it works; if you find a reason it
does not (the `.ys` and `macros/models/*.v` package data in `pyproject.toml`
are the likely trap — they must land inside the bundle and be found at
runtime), say so in your notes and use whatever does work. A zipapp plus a
vendored interpreter is a legitimate alternative if you justify it.

Constraints:

- PyInstaller is a **build-only** dependency. It must not appear in
  `pyproject.toml`'s runtime `dependencies`.
- The bundle output goes to `app/resources/bin/`. Add that path to
  `.gitignore` — it is a build artefact, not source. Do not commit binaries.
- The bundler must fail loudly if the result is broken, not emit a stub.

### 2. A test that fails when the core is not really bundled

This is the acceptance criterion, and it is the part previous rounds got wrong
seven times over. A test that passes because a host venv answered the call has
measured nothing.

Build the bundle, then invoke it with the environment **scrubbed**: no
`GATEPACK_CORE`, `PATH` stripped of `.venv/bin` and of any directory containing
a `gatepack` or `python3`, `PYTHONPATH` unset, `PYTHONHOME` unset. Assert that
`gatepack lib list --json` still returns a valid envelope. Then assert the
negative: with `app/resources/bin/gatepack` moved aside, the same scrubbed
invocation **fails** — if it still succeeds, your scrub is not scrubbing and
the positive test proves nothing.

Mark it skip-if-PyInstaller-unavailable rather than passing vacuously, and make
the skip reason name the missing tool.

### 3. Prove the packaged app uses it

`npx electron-builder --linux dir` (output goes to `../.gpout/dist` per the
config), then check the unpacked tree: `resources/resources/bin/gatepack` is
present, is executable, and is outside the asar. A packaging test that greps
the unpacked layout is fine — it is a real check on real output.

### 4. The native toolchain — report, do not fabricate

The core still shells out to `yosys`, `sby`, `iverilog`, `espresso` and `z3`.
Bundling those per-platform is a much larger job than the Python core and you
may well not be able to do it here.

**Do not fake it, and do not ship a placeholder that pretends.** What you must
do instead:

- Work out honestly what each binary would require (licence, size, static
  linking, per-platform provenance) and write it up. Yosys is ISC, sby is ISC,
  Icarus is GPL-2.0-or-later, z3 is MIT — check these yourself, do not trust
  this list, and note anything that conflicts with the app's GPL-3.0-only
  `package.json` declaration.
- Make the failure legible. A user with a bundled core and no yosys must get a
  clear, specific message naming the missing binary and what it is for — not a
  stack trace, not a silent empty result. Add a `gatepack doctor`-style
  self-check that reports each required external tool as found (with version)
  or missing, exposed through the CLI with `--json`. Wire it into
  `app/shared/api.ts`'s existing shape only if a seam already exists; **do not
  edit `api.ts`** — if a new IPC surface is needed, describe it in your notes
  and leave the CLI side complete.
- Write a test that the missing-binary path produces that message. Make it fail
  by pointing the resolver at an empty directory, not by mocking.

### 5. Update the docs

`docs/RELEASING.md` — the "What exists and what does not" section and the
release steps. It must describe what you actually achieved, including what is
still not bundled. Under-promising here is correct.

## Off-limits — three other agents are editing these right now

- `gatepack/macros/**`, `gatepack/verify/**`, `tests/toolchain/test_mcell*` —
  the M8 agent.
- `gatepack/pack/**`, `app/renderer/views/Schematic.tsx` — the M15 agent.
- `app/renderer/selection/**`, `app/renderer/views/**` — the M16 agent.

You own `scripts/`, `app/resources/`, `app/electron-builder.yml`,
`app/main/core.cts`, `docs/RELEASING.md`, `.gitignore`, `pyproject.toml`, and
new files under `tests/`. If you need something in another scope, write it in
your notes instead of reaching for it.
