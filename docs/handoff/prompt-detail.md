# Package: a failed check must carry its reason to the GUI

You are an engineer who treats "the UI said it failed but not why" as a defect
in the contract, not a cosmetic gap.

## The project

`gatepack` compiles a truth table or FSM specification into a bill of materials
and a schematic netlist built from discrete 74AUP logic packages, formally
verifying the result on every build. The Electron app is strictly a *view* over
artefacts the CLI produced — it never computes a status itself.

## The defect

The core's verification checks carry a human-readable `detail` when they fail —
for example SymbiYosys's own error text when a property harness cannot run. The
IPC boundary drops it: `app/shared/api.ts` and the envelope schema in
`app/main/envelope.cts` have no field for it, so the renderer receives a check
that is red and mute. The user sees `failed` and nothing else, and has to go to
a terminal to find out what happened.

This is the project's recurring failure mode in miniature — a status reported by
something that did not carry what it measured. The number of two-file changes
that fix it is exactly one; make it.

## What to do

1. Find where the core emits a check result (`gatepack/`) and what fields it
   actually populates on failure. **Read it, do not assume the field is called
   `detail`** — carry through whatever the core really emits.
2. Add the field to the shared IPC type in `app/shared/api.ts` and to the zod
   schema in `app/main/envelope.cts`, so it validates rather than being stripped.
   Optional, so an older core that omits it still validates.
3. Surface it in the renderer wherever a failed check is rendered. Find the
   component; do not invent a new panel. A failed check should show its reason
   without the user having to click anything, and long text (sby dumps a stack)
   must wrap or scroll inside its container rather than blowing out the layout.
4. Tests: a unit test that the schema accepts and preserves the field, a unit
   test that it survives round-trip through the envelope parse, and a renderer
   test that a failed check with a reason renders that reason. If an existing
   test asserts the field is absent, that assertion is now wrong — update it and
   say so in your report.

## Second, smaller task

`app/renderer/views/spec/FsmGraph.tsx` just gained an exported helper
`nearestSides(from, to)` which picks which face of a state box a transition
should leave from and arrive at, given the two boxes' centres. Write unit tests
for it in `app/renderer/views/spec/fsmRouting.test.ts`:

- a target directly to the right leaves `r` and arrives `l`; left, above and
  below likewise;
- the returned target side is always the opposite of the source side;
- a diagonal offset resolves to the *dominant* axis, and because the node box is
  wider than it is tall the comparison is in units of the box half-extent — a
  target 60px right and 30px down comes off the right face, not the bottom.

Do not change `FsmGraph.tsx` itself; another engineer is editing it right now.
Test the helper as it stands.

## The rules that govern this repo

- **Never fake a tool result.** If something cannot be verified, report it
  unverified.
- Do not weaken an assertion to make a test pass.
- Never touch any path outside the project directory — **reads included**.
- Do not commit. Leave the work in the tree; the maintainer reviews and commits.

## Files you own

`app/shared/api.ts`, `app/main/envelope.cts`, the renderer component that draws
check results, `app/renderer/views/spec/fsmRouting.test.ts`, and new tests.

## Off-limits

`app/renderer/views/spec/FsmGraph.tsx`, `app/renderer/views/views.css`,
`.github/**`, `app/electron-builder.yml`, `docs/RELEASING.md`, `app/signing/**`.

## Verify before reporting

`cd app && npx tsc --noEmit -p tsconfig.json && npx vitest run` — 264 tests pass
today; report the number after your change and account for any that moved.
