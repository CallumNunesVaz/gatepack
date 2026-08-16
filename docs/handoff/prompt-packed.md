You are a React engineer who also writes careful Python, finishing the
schematic view.

# The project

`gatepack` compiles an FSM or truth table into a bill of materials built from
discrete logic packages. The desktop app is a view over CLI-produced artefacts;
it never reimplements core logic. 532 Python tests, 150 vitest, 12 Playwright
e2e pass.

You are in a git worktree on branch `deepseek/packed3`, clean baseline.

# Your scope: M15 — netlistsvg rendering all layers

`docs/GUI-AUDIT.md` records M15 as partial. `app/renderer/views/Schematic.tsx`
declares three toggleable layers; only one is a render:

- **mapped netlist (logical)** — a real netlistsvg render. Works now: the
  `gatepack mapped-netlist` subcommand it needs was added today.
- **packed netlist (package boundaries)** — a hardcoded text notice.
- **test points / unobservable nets** — a text list, now able to reach
  `analyse()`, which also exists as of today.

The exit criterion is "netlistsvg rendering all layers".

## 1. Core: `gatepack packed-netlist`

A `PackedView` payload already exists in `app/shared/api.ts` (read it; do not
edit it), and the whole bridge is plumbed — `packedNetlist()` in the preload,
IPC and session manager, invoking `gatepack packed-netlist <dir>`. **The
subcommand does not exist yet.** Add it to `gatepack/cli.py`, following
`_cmd_mapped_netlist` and `_cmd_analyse` for the envelope and the honest
degradation when there is no build.

`PackedView` carries package boundaries only, deliberately **not** a second
netlist — the renderer already has that from `mappedNetlist()`, and two
representations of one circuit can disagree. Each entry needs both the stable
cone-hash `cells` and the mapped-netlist `instanceCells`, because the rendered
SVG is keyed by instance names while `packing.force_groups` records stable
ones. `gatepack/build.py` computes both; `BuildResult.stable_names` is a
`CellNames` mapping with `to_instance()`/`to_stable()`.

Confusing those two name spaces has caused **four** separate defects in this
project. Use the conversion that exists; do not re-derive it.

## 2. Renderer: draw the layers

- **Packed layer:** package boundaries drawn over the logical netlist — a
  container per package, labelled with its refdes and part number, with spare
  slots visible. netlistsvg emits SVG with per-cell groups you can hit-test by
  instance name; overlay rather than re-layout.
- **Overlay layer:** test points and unobservable nets. `analyse()` returns
  `scoap` entries; an unobservable net is one whose observability is the
  sentinel (see `gatepack/analysis/scoap.py` — it is a large finite value, not
  infinity, and the report renders it as `∞`).
- Layers stay independently toggleable, and **C12 renders; it never edits**.

If a layer genuinely cannot be drawn from available data, say so in the notes
and leave the honest notice rather than faking a render — but exhaust the data
first. Both layers' data now exists.

## 3. Tests

- Python: the subcommand's envelope, including no-build degradation, and that
  `instanceCells` really index the mapped netlist (a stable name appearing
  there is the defect to catch).
- vitest, through the fake bridge: the packed layer renders one container per
  package with its refdes; a spare slot renders distinctly from a used one;
  the overlay marks exactly the unobservable nets and no others; toggling a
  layer off removes it.

## Off-limits

`gatepack/frontend/`, `gatepack/macros/`, `gatepack/verify/`,
`gatepack/estimate.py`, `app/renderer/selection/`,
`app/renderer/views/{BomView,VerificationPanel,SpecEditor,TruthTable}.tsx`,
`app/shared/api.ts`, `app/electron-builder.yml`, `scripts/`, `.github/`. You
may *read* anything. Write in `gatepack/cli.py`, `gatepack/api.py`,
`app/renderer/views/Schematic.tsx`, `app/renderer/worker/`,
`app/renderer/bridge/fake.ts`, `tests/`, and your notes.

# Rules — each of these has cost a previous run

- **Do not commit.** Leave everything in the working tree. No branches, no
  stashing, no amending.
- **Do not edit** `gatepack-design.md`, `docs/M0-FINDINGS.md`,
  `docs/M6-FINDINGS.md`, `docs/MILESTONE-AUDIT.md`, `docs/GUI-AUDIT.md`,
  `app/shared/api.ts`. They are inputs; `api.ts` is the authoritative IPC
  contract, match it field for field.
- **Stay inside your file scope.** Three other agents are writing in this repo
  right now, in the scopes listed as off-limits below.
- **Never write outside the project directory, and never `&&`-chain a command
  that might be refused.** Anything outside it is auto-rejected and the
  refusal ENDS THE RUN — it has now killed three runs, two of them mid-task
  after real work. Use `.gpout/` **inside your worktree** for every scratch
  file, backup and build output. Do not `cp` to `/tmp`; do not use `../` paths
  that climb out of the worktree.
- **Do not run `npm install`.** `app/node_modules` is already populated.
- Run the tests and fix what you break. Python:
  `.venv/bin/python -m pytest tests -q` (**532 pass, 4 skip** at baseline).
  From `app/`: `npx tsc --noEmit -p tsconfig.json`,
  `npx tsc --noEmit -p tsconfig.main.json`, `npx vitest run` (**150 pass**),
  and `DISPLAY=:1 npx playwright test --config playwright.config.cjs`
  (**12 pass**, after `npm run build:main && npx vite build`).
- **A check that cannot fail is worth nothing.** For everything you add, build
  the input that makes it fail and keep that as a test. This project has now
  shipped **eight** pieces of machinery that reported a status while measuring
  nothing, every one with a green suite, and four of them had tests that could
  not have failed.
- **Never fake a tool result.** A missing binary is reported, never
  substituted.
- **Run the real thing.** `gatepack-toolchain:m6` has Yosys 0.23, Icarus, sby,
  z3 and pydantic, and the CLI runs in it:
  `docker run --rm -v "$PWD:/repo" -w /repo gatepack-toolchain:m6 bash -c '...'`
  Claims that a tool closes must come from that, not a fake runner. Files it
  writes are owned by root — delete them from inside the container.
- Write `docs/BUILD-NOTES-<scope>.md`: what you implemented, what you guessed,
  what is a placeholder, what you could not verify, what is weakest. Your notes
  have three times caught defects you could not reach yourself — record
  suspicions as well as facts.

# Output

A short summary: files added/changed, test counts before and after, and the
three things you are least confident about.
