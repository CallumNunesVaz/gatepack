
# Rules — each of these has cost a previous run

- **Do not commit.** Leave everything in the working tree. No branches, no
  stashing, no amending.
- **Do not edit** `gatepack-design.md`, `docs/M0-FINDINGS.md`,
  `docs/M6-FINDINGS.md`, `docs/MILESTONE-AUDIT.md`, `docs/GUI-AUDIT.md`,
  `app/shared/api.ts`. They are inputs; `api.ts` is the authoritative IPC
  contract, match it field for field.
- **Stay inside your file scope.** Three other agents are writing in this repo
  right now, in the scopes listed as off-limits below.
- **Never touch any path outside the project directory — READS INCLUDED — and
  never `&&`-chain a command that might be refused.**
  `cat /etc/os-release`, `ls /usr/lib`, `cp x /tmp/y` are all auto-rejected and
  the refusal ENDS THE RUN mid-task. To learn about the host, use commands that
  do not name an outside path (`uname -m`, `ldd --version`, `docker run ...`),
  or read it inside a container and print the result. Anything outside it is auto-rejected and the
  refusal ENDS THE RUN — it has now killed three runs, two of them mid-task
  after real work. Use `.gpout/` **inside your worktree** for every scratch
  file, backup and build output. Do not `cp` to `/tmp`; do not use `../` paths
  that climb out of the worktree.
- **Do not run `npm install`.** `app/node_modules` is already populated.
- Run the tests and fix what you break. Python:
  `.venv/bin/python -m pytest -q` (**723 pass, 5 skip** at baseline,
  including 59 toolchain tests that need docker).
  From `app/`: `npx tsc --noEmit -p tsconfig.json`,
  `npx tsc --noEmit -p tsconfig.main.json`, `npx vitest run` (**334 pass**),
  and `DISPLAY=:1 npx playwright test --config playwright.config.cjs`
  (**24 pass**, after `npm run build:main && npx vite build`).
- **A check that cannot fail is worth nothing.** For everything you add, build
  the input that makes it fail and keep that as a test. This project has now
  shipped **nine** pieces of machinery that reported a status while measuring
  nothing, every one with a green suite, and four of them had tests that could
  not have failed.
- **Never fake a tool result.** A missing binary is reported, never
  substituted.
- **Run the real thing.** `gatepack-toolchain:m6` has Yosys 0.23, Icarus, sby,
  z3 and pydantic, and the CLI runs in it. Always pass `-u`, or everything the
  container writes into the checkout is owned by root and your *next* local
  command fails with EACCES:
  `docker run --rm -u "$(id -u):$(id -g)" -v "$PWD:/repo" -w /repo gatepack-toolchain:m6 bash -c '...'`
  Claims that a tool closes must come from that, not a fake runner.
  `tests/toolchain/docker_runner.py` builds this command for the test suite;
  use it rather than hand-rolling a `docker run` in a test.
- Write `docs/BUILD-NOTES-<scope>.md`: what you implemented, what you guessed,
  what is a placeholder, what you could not verify, what is weakest. Your notes
  have three times caught defects you could not reach yourself — record
  suspicions as well as facts.

# Output

A short summary: files added/changed, test counts before and after, and the
three things you are least confident about.
