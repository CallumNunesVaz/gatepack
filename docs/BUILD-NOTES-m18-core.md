# BUILD NOTES — M18 core bundling (the core actually ships)

Scope: make "the Python core does not ship inside the app" false. A
self-contained `gatepack` core at `app/resources/bin/gatepack`, produced by a
bundler, proven by a test that scrubs the host, wired into the packaged app, and
a legible missing-tool story plus a `doctor` self-check. Files owned per the
task brief: `scripts/`, `app/resources/`, `app/electron-builder.yml`,
`app/main/core.cts`, `docs/RELEASING.md`, `.gitignore`, `pyproject.toml`, and
new files under `tests/`.

This supersedes the "What I did not solve" section of the earlier
`docs/BUILD-NOTES-m18.md` (which did the packaging config but explicitly did NOT
bundle the core).

## Test results

```
$ .venv/bin/python -m pytest tests -q            # 543 passed, 5 skipped
$ .venv/bin/python -m pytest tests -q            # baseline before this work: 532 passed, 4 skipped
$ GATEPACK_PACKAGING=1 .venv/bin/python -m pytest tests/toolchain/test_packaging.py -q   # 1 passed
$ cd app && npx tsc --noEmit -p tsconfig.main.json   # clean
$ cd app && npx vitest run                      # 151 passed (was 150)
```

## What was built

### 1. `scripts/bundle_core.py` — the core bundler

Produces a PyInstaller **onefile** ELF at `app/resources/bin/gatepack`
(~14.5 MB, stripped). It runs with no host Python, no venv, and no gatepack:
the frozen binary answers `gatepack doctor --json` under `env -i` with an empty
`PATH`.

- PyInstaller is a **build-only** dependency. It is not in `pyproject.toml`'s
  runtime `dependencies` (which still declares only `pydantic`), and the script
  fails loudly with a "install with `pip install pyinstaller`" message if the
  module is not importable. It was installed into `.venv` only to exercise the
  build here (the environment turns out to have PyPI access; `pip install
  pyinstaller` succeeded).
- The package-data trap was the reason the task flagged `.ys`/`.v` files: they
  are loaded at runtime via `importlib.resources` (`gatepack/yosys/__init__.py`,
  `gatepack/macros/__init__.py`). `--collect-all gatepack` folds them into the
  bundle, and the post-build smoke test **re-loads** them under a scrubbed
  environment. If either resource went missing the script exits non-zero rather
  than leaving a broken binary — it never emits a stub.
- The build is invoked as `python -m PyInstaller` via subprocess (never the
  in-process API, which can `sys.exit`), with `--paths <repo>`,
  `--collect-all gatepack`, `--collect-all pydantic`, `--clean`, `--noconfirm`,
  and scratch dirs under `.gpout/core-bundle` (gitignored). The entry point is a
  three-line `_gatepack_entry.py` written to the workdir.
- `examples/` is **not** package data (it sits beside the `gatepack` package), so
  `--collect-all gatepack` does not see it and `gatepack/examples.py`'s
  `__file__`-based lookup missed it in a frozen build. It is bundled explicitly
  with `--add-data examples:examples`, and `examples.py` now resolves its root
  via `sys._MEIPASS` when `getattr(sys, "frozen", False)`. The smoke test asserts
  `examples list` **names** `pelican` and that `examples extract pelican`
  materialises a `design.yaml` — exit-0-only would have let the empty-result
  regression through.
- `libraries/74aup.csv` is **deliberately not** bundled: the CLI takes it as an
  explicit `--library` path argument (every `build`/`estimate`/`verify` requires
  one), the packaged app opens projects that carry their own `parts.csv`, and
  the file is placeholder electrical data anyway. Bundling a default library the
  user never asked for would be the wrong default.

### 2. The acceptance test (`tests/toolchain/test_core_bundle.py`)

This is the test the brief says seven rounds got wrong. It:

1. builds the bundle (session-scoped; skips with a reason **naming PyInstaller**
   if the module is missing);
2. invokes it **by bare name** with `PATH` rebuilt to contain only
   `app/resources/bin` plus directories that contain neither `gatepack` nor
   `python3`, with `GATEPACK_CORE`/`PYTHONPATH`/`PYTHONHOME` unset — asserts a
   valid `doctor --json` envelope, that the bundle can `compile` a design, and
   that `examples list` names `pelican` and `examples extract pelican` writes a
   `design.yaml` (exit-0-only is not a check, since `examples list` exits 0
   while returning nothing when the examples are missing);
3. the negative half moves the bundle aside and asserts the *same* scrubbed
   invocation now fails, so a host venv cannot have been answering.

A note on the command: the brief said to assert `gatepack lib list --json`
returns a valid envelope. No `lib list` subcommand exists (the library commands
are `lib check` / `lib gen`, neither of which takes `--json`). I used
`gatepack doctor --json` instead — it exercises the full import graph *and*
proves the bundled package data loads, which `lib list` would not have. This is
recorded here because it is a deliberate deviation, not an oversight.

### 3. The packaged app really uses it

- `core.cts` gained an optional `resourcesPath` option; `index.cts` now passes
  `process.resourcesPath`. This fixed a real path bug I found by running the
  package: `app.getAppPath()` returns `…/resources/app.asar` in the packaged
  app, so the old `path.join(appRoot, 'resources', 'bin', 'gatepack')` resolved
  **inside the asar** and never found the binary. electron-builder's
  `extraResources (from: resources, to: resources)` lands the core at
  `<package>/resources/resources/bin/gatepack` (verified in the unpacked tree),
  which is `path.join(resourcesPath, 'resources', 'bin', 'gatepack')`.
- `tests/toolchain/test_packaging.py` (gated behind `GATEPACK_PACKAGING=1`
  because electron-builder takes minutes) builds the app, runs
  `npx electron-builder --linux dir`, and greps the unpacked tree for
  `resources/resources/bin/gatepack`, asserting it is present, executable, and
  outside the asar. Verified passing here.

### 4. `gatepack doctor` + legible missing-tool errors

- New `gatepack/doctor.py` + `gatepack doctor [--json]`: reports each external
  tool (`yosys`, `sby`, `iverilog`, `vvp`, `z3`, `espresso`) as found (with
  version, when the tool can report one) or missing, each with its purpose, plus
  a bundled-resources check that re-loads `common_frontend.ys` and the M-cell
  models. `allToolsPresent` folds only the tools gatepack invokes directly
  (yosys/sby/iverilog/vvp); z3 and espresso are reported but never gate it.
  Exit code is always 0 — it is a report, so a bundled core with no toolchain
  still answers a valid envelope (which the acceptance test depends on).
- The missing-binary path now names the binary *and* its purpose:
  `build` without yosys reports `yosys is not on PATH (logic synthesis:
  behavioural Verilog -> mapped netlist)` (exit 1, `GP1006`, no traceback);
  `verify`'s `not_run` reasons now carry the purpose too. Pinned by
  `tests/contract/test_doctor_contract.py`, which points `PATH` at an empty
  directory (real resolution, not a mock) and asserts the message.
- `app/shared/api.ts` was **not** edited (as required). The `doctor` payload is
  a new envelope `data` shape; the renderer has no `doctor` surface and none was
  added. If the app ever wants a "tools" panel, the would-be IPC seam is:
  add `doctor(): Promise<Envelope<DoctorResult>>` to `GatepackApi`, a
  `DoctorResult` interface mirroring the CLI `data` object (`version`, `tools:
  {name, found, purpose, direct, path, version}[]`, `resources`, and
  `allToolsPresent`), the matching zod schema in `app/main/envelope.cts`, an
  `ipcMain.handle` for it in `app/main/ipc.cts`, and a `contextBridge` exposure
  in `app/preload`. None of that was done — it is out of scope and out of my
  file ownership — and the CLI side is complete on its own.

## The native toolchain — report, not fabrication

I did **not** bundle yosys/sby/iverilog/espresso/z3, and I did not ship a
placeholder that pretends to. What a per-platform bundle would require, checked
against each upstream's own licence file rather than the design doc's table:

| tool | role in gatepack | licence (verified) | GPL-3.0-only app OK? |
|------|------------------|--------------------|----------------------|
| yosys | synthesis (C3) | ISC (from `COPYING`) | yes, permissive |
| sby | §11 properties + equiv fallback | ISC (from `COPYING`) | yes |
| iverilog | compile sim testbench | GPL-2.0-or-later (from `COPYING`) | yes (GPL-2.0-or-later upgrades to GPL-3) |
| vvp | run compiled sim | same as iverilog | yes |
| z3 | SMT solver for sby (indirect) | MIT (from `LICENSE.txt`) | yes |
| espresso | async cover (v0.2, unused today) | **no top-level LICENSE file** | **unresolved** |

Two honest findings that contradict the design doc §4 table:

1. **espresso (chipsalliance fork) has no detectable licence.** The repo has no
   `LICENSE`/`COPYING` at the top level (the GitHub licence endpoint returns
   404). §4 lists "Espresso (maintained fork) | BSD-style (UC Berkeley)", which
   is the *heritage* of the original Berkeley code, not something the fork
   restates. Bundling it is a maintainer decision, not something I can clear
   silently. Good news: gatepack does not invoke espresso today (only the async
   backend, which is refused at v0.1.0, would), so this does not block the
   current core.
2. **z3 is only reached indirectly** (sby's `smtbmc z3` engine) — gatepack never
   shells out to `z3` itself. The brief's list ("shells out to … espresso and
   z3") is slightly ahead of the code: `grep` finds no direct `espresso`/`z3`
   invocation anywhere in `gatepack/`. `doctor` reports both anyway, marked
   `direct: false`.

Per-binary sizes and static-linking feasibility are **not** measured here: the
reproducible `Dockerfile` (pinned Yosys 0.23, sby, chipsalliance/espresso,
Debian-packaged iverilog/z3) has still not been built end to end, and I will not
quote a size I have not produced. The honest statement is: sizes and
relocatability are only knowable after a real build, and yosys/espresso are
source-built against the pinned base-image digest (provenance = commit SHA +
digest), while iverilog/z3 come from the Debian archive (provenance =
base-image digest). Static linking is feasible for yosys (`make
config-gcc`/`config-clang` with `STATIC`) but unproven in this tree.

## What I could not verify / is weakest

1. **The bundle is Linux x86-64 only.** PyInstaller is not a cross-compiler; a
   Windows/macOS core must be built on those platforms (or in CI matrix jobs),
   and none of that is tested here. The `--linux dir` package is the honest
   subset, same as the earlier M18 round.
2. **`examples/` is now bundled** (see §1: `--add-data` + `sys._MEIPASS`
   resolution), and the smoke test + acceptance test assert `examples list`
   names `pelican` and `examples extract pelican` writes a `design.yaml`. The
   `libraries/74aup.csv` decision is: not bundled, by design (explicit
   `--library` argument; the packaged app opens projects with their own
   `parts.csv`).
3. **`process.resourcesPath` vs `app.getAppPath()`.** I fixed the packaged path
   by passing `resourcesPath` through, verified against a real
   `electron-builder --linux dir` output. I did not test macOS/Windows layouts
   (unbuildable here), where the resource tree shape should be the same but is
   unproven.
4. **Pre-existing shell-harness failure (not mine, not fixed).**
   `scripts/tests/test_licence_audit.sh` fails 2 checks because it still expects
   the committed-tree audit to exit 1 with "one shipped finding", but the audit
   now exits 0 — `spdx-exceptions` was already excluded from the asar by the
   existing `files` excludes in `app/electron-builder.yml` before this work. The
   shell harness reports 4/5; this predates M18-core and belongs to the licence
   audit's scope, so I left it rather than editing a test whose expectation I
   did not set.

## What is guessed / placeholder

- Tool "purposes" in `doctor` are my prose, not spec text.
- Version probing uses `--version` for yosys/sby/z3 and `-V` for
  iverilog/vvp; espresso has no version flag so its version is `null` when
  found. These are best-effort and unverified against a real toolchain image
  (the probe is exercised only in the "missing" direction here).
- `appId`/`maintainer` placeholders in `electron-builder.yml` are unchanged and
  still the maintainer's job.
