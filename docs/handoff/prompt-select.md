You are a React engineer finishing the interaction that justifies this
application existing.

# The project

`gatepack` compiles an FSM or truth table into a bill of materials built from
discrete logic packages. §15's linked selection is the stated reason for
building a GUI at all — everything else could be a report. 532 Python tests,
150 vitest, 12 Playwright e2e pass.

You are in a git worktree on branch `deepseek/select3`, clean baseline.

# Your scope: M16 — the remaining cross-highlights

`docs/GUI-AUDIT.md` records M16 as partial. The data path is now fixed: the
`gatepack provenance` subcommand was added today, so `provenance()` returns a
real `ProvenanceMap`. What remains is in the renderer:

- **package selections map to nothing.** Selecting a package card in the BOM
  view should highlight the gates it holds, and vice versa.
- **property selections map to nothing.** Selecting a failing property (or a
  counterexample step) in the verification panel should highlight the spec
  constructs and gates implicated in it. `Check.counterexample` carries
  `steps` and `pointers` for exactly this.

Read §15.2's table in `gatepack-design.md` and work through it. Every row that
does not work is your scope; every row that does is a regression risk.

## What matters more than coverage

- **Partial links must stay visibly partial.** Measured on the showcase: 5 of
  7 transitions carry exact provenance; `transitions[1]` and `transitions[4]`
  have **none**, because `abc` folds intermediates into the combinational cone
  and `opt_clean` removes them. A transition that highlights nothing must say
  "no exact link" — silence reads as a broken UI, or worse as "this transition
  produced no logic". Render `inferred` differently from `exact`.
- **Package selection crosses name spaces.** Packages hold *stable* cone-hash
  names; the schematic and provenance map are keyed by mapped-netlist
  *instance* names. `BuildResult.stableCellNames` maps instance → stable.
  Confusing these has caused four separate defects here — convert explicitly,
  and add a test that a stable name never leaks into a place expecting an
  instance name.
- **A selection with no counterpart is a state, not a no-op.** Every direction
  in §15.2 either highlights something or says why it cannot.

## Tests

Through the fake bridge, never a real process:

- selecting a package highlights exactly its cells, and selecting one of those
  cells selects the package back;
- a counterexample step highlights the constructs its `pointers` name;
- a transition with no provenance entry renders its "no exact link" state, and
  one with an `inferred` entry renders differently from an `exact` one;
- the §15.2 rows that already work still work.

## Off-limits

`gatepack/` (all of it — the data you need is already on the contract),
`app/renderer/views/Schematic.tsx`, `app/renderer/worker/`,
`app/shared/api.ts`, `app/main/`, `app/preload/`, `scripts/`, `.github/`. You
may *read* anything. Write in `app/renderer/selection/`,
`app/renderer/views/{BomView,VerificationPanel,SpecEditor,TruthTable}.tsx`,
`app/renderer/components/`, `app/renderer/bridge/fake.ts`, `app/tests/e2e/`,
and your notes.

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
