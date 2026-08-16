# Package: "core exited 1" — the exit code and the envelope disagree

You are an engineer who treats a protocol mismatch between two components as a
contract question first and a code change second.

## The project

`gatepack` compiles a truth table or FSM specification into a bill of materials
and a schematic netlist built from discrete 74AUP logic packages, formally
verifying the result on every build. The Electron app spawns
`gatepack <cmd> --json`, parses exactly one envelope from stdout, validates it,
and renders it.

## The defect, as the user sees it

Press **Run verification** in the app on a machine without yosys installed and
the entire result is:

```
core exited 1
```

No check list, no reasons, nothing actionable.

## What is actually happening

The core is behaving well. Run it yourself:

```
env -i PATH=/usr/bin:/bin ./app/resources/bin/gatepack verify \
  examples/pelican/design.yaml --library libraries/74aup.csv \
  --build .gpout/vtest --json
```

It prints a complete, schema-valid envelope with `ok: true` and, per check,
`status: "not_run"` with a `skippedReason` naming the missing tool
(`"yosys not installed (logic synthesis, §C3)"`). Exactly what §C15 wants: a
missing tool is a legitimate visible state.

**And it exits 1**, because `allPassed` is false.

`app/main/core.cts` (~line 240) then throws that envelope away:

```js
// A non-zero exit that still claims `ok: true` is a lying core: never
// pass it through. Prefer a visible error envelope.
if (code !== 0 && envelope.ok) { ... 'core exited ' + code ... }
```

That guard is well-intentioned and catches a real failure mode. It also
destroys the most informative envelope the tool produces.

## The contract question — decide it first

`app/shared/api.ts` says:

> Exit code is 0 for `ok: true` and non-zero otherwise; the renderer must key on
> `ok`, never on the exit code alone.

Two defensible readings collide:

1. **The envelope's `ok` describes the command, not the result.** `verify` ran
   perfectly and reports that three checks did not run. That is `ok: true`, and
   exiting 1 violates the stated contract.
2. **A non-zero exit for a failed verification is genuinely useful** — it is how
   anyone would drive this from a shell script or CI, and removing it would be a
   regression for CLI users.

Both are right, which means the contract is underspecified rather than either
component being simply wrong. Resolve it deliberately and write the resolution
into `app/shared/api.ts` as prose — that file is the authority, and this is
exactly the kind of ambiguity it exists to settle.

My reading, which you should challenge if you disagree: `ok` means "the command
executed and this envelope is its answer"; the *exit code* additionally encodes
whether the answer is all-green, for shell use. Those are different questions
and both are worth answering. If you agree, then main's guard must fire only
when the envelope is **absent or unparseable**, not when a valid `ok: true`
envelope accompanies a non-zero exit — and the contract must say which commands
use their exit code that way.

Whatever you decide, the guard must keep catching the case it was written for: a
core that dies mid-run and leaves a truncated or missing envelope must still
surface visibly, never as a silent empty result.

## Then audit every command for the same mismatch

`verify` is the one the user hit. Check all of them —
`lib check`, `estimate` (a red verdict), `build`, `simulate`, `analyse`,
`provenance`, `doctor` — by running each with `--json` and recording the exit
code alongside `ok`. Some will legitimately exit non-zero; the contract must
name them. Put the table in your build notes.

## Tests

- A test that fails on the current behaviour: a core that exits non-zero with a
  valid `ok: true` envelope must reach the renderer intact.
- A test that keeps the original guard honest: a core that exits non-zero with
  **no** envelope, or a truncated one, must still produce a visible error.
- An e2e test through the real main process, using the fake core in
  `app/tests/e2e/fake-core.cjs` (it can be told to exit non-zero), asserting the
  verification panel renders the check list with its skip reasons rather than
  "core exited 1".

Break each one, watch it go red, restore, and report what the failure looked
like. This project has shipped **nine** pieces of machinery that reported a
status while measuring nothing.

## Files you own

`app/shared/api.ts`, `app/main/core.cts` and its tests, `gatepack/cli.py`,
`app/tests/e2e/fake-core.cjs` and a new e2e spec, and new tests under `tests/`.

## Off-limits — three other agents are in this repo right now

- `app/renderer/**` — two agents are in the shell, panels, state and views.
- `scripts/**`, `gatepack/toolchain.py`, `gatepack/doctor.py`, `Dockerfile*`,
  `.github/**` — the toolchain agent.
- `libraries/**`, `gatepack/macros/**`, `gatepack/parts.py` — the library-data
  agent.
- `docs/MILESTONE-AUDIT.md`, `gatepack-design.md` — inputs.
