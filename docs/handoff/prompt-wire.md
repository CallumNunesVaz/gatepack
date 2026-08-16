# Package: wire the panels in, and fix three defects the e2e agent found

You are a front-end engineer finishing an integration that was split across two
people and left with no seam between them.

## The project

`gatepack` compiles a truth table or FSM specification into a bill of materials
and a schematic netlist built from discrete 74AUP logic packages, formally
verifying the result on every build. The Electron app is strictly a view over
artefacts the CLI produces.

## Defect 1 — six panels exist and none of them are reachable

This is the important one. A previous round added the IPC surface and six
inspector panels:

```
app/renderer/panels/ToolchainStatusPanel.tsx   inspect.doctor
app/renderer/panels/ProvenancePanel.tsx        inspect.provenance
app/renderer/panels/MappedNetlistPanel.tsx     inspect.mappedNetlist
app/renderer/panels/PackedNetlistPanel.tsx     inspect.packedNetlist
app/renderer/panels/LibraryPanel.tsx           inspect.library
app/renderer/panels/ExamplesPanel.tsx          project.examples
```

They are unit-tested in `panels.test.tsx` and **nothing imports them**. No
handler is registered for any `inspect.*` command, so dispatching one from the
command palette shows a "not wired yet" toast.

The consequence is that the project's claim to CLI parity is currently false in
the only sense that matters: the user cannot reach these. The registry test
(`app/renderer/keys/registry.test.ts`) passes because it checks that a *command
entry* exists per CLI subcommand — a necessary condition that says nothing about
whether the command does anything.

Wire them into the shell's dispatch so every `inspect.*` and `project.examples`
command opens its panel. How they present — a dialog, a docked pane, a tab in
the inspector — is your call; argue for it in your notes. Whatever you choose
must be keyboard-dismissible and must return focus where it came from.

**Then make the registry test sufficient rather than necessary.** Extend it (or
add a companion) so that a command with a `cli` tag must also resolve to a
mounted handler. A command entry that dispatches to nothing should fail the
suite. That check is the whole reason this defect is worth fixing properly
rather than just adding six imports.

## Defect 2 — the design name goes stale mid-session

`app/renderer/state/project.tsx` reads the spec **once on mount**.
`onProjectChanged` updates `project`, so the status bar's path updates, but the
spec is never re-read, so `model.name` — and the status bar's design field —
keeps showing the previous project's name after `openProjectPath`.

The e2e agent wrote a test for exactly this, watched it go red, and switched the
test to the flow that works rather than leaving a failing test in the suite. Its
note is in `docs/BUILD-NOTES-e2e.md`. Fix the defect and restore the strict test:
open project A, then project B, and assert the design name follows.

## Defect 3 — `onFileChanged` is consumed by nobody

Main broadcasts debounced file-change events (C9) and no renderer code
subscribes, so an external edit to `design.yaml` never reaches the editor. The
renderer's model of the spec is effectively frozen after mount, which is the
same root cause as defect 2.

Subscribe, and re-read. Be careful about the interaction with unsaved local
edits: silently overwriting what the user has typed because a file changed on
disk is a worse bug than the one you are fixing. Decide the policy deliberately
(prompt, or keep local edits and mark stale), state it in your notes, and test
both directions.

## Defect 4 — `AnalysisView` has no error state

A failing `estimate()` or `analyse()` leaves the Analysis view blank. Only the
Verification panel surfaces an `ok:false` envelope today. A missing tool is a
legitimate, visible state — `gatepack build` refuses with "synthesis
unavailable … (never faked here)" and that refusal must reach the user as a
message naming the tool, never an empty panel.

Give it the same error treatment the other views have, and test it with a
seeded failure envelope from the fake bridge.

## Rules specific to this package

- **Do not weaken an existing test to make something pass.** If a test blocks
  you, it is more likely right than you are; if it genuinely is wrong, say so
  explicitly in your notes and explain why.
- Every test you add must be able to fail. Break the thing, watch it go red,
  restore, and report what the failure looked like.
- The design system is `app/renderer/ui/` — tokens, `Icon`, `Tooltip`, `Button`,
  `Panel`, `EmptyState`, `Spinner`, `Toast`. Never hardcode a colour or spacing.

## Files you own

`app/renderer/App.tsx`, `app/renderer/shell/**`, `app/renderer/panels/**`,
`app/renderer/state/**`, `app/renderer/keys/registry.test.ts`,
`app/renderer/views/AnalysisView.tsx` and its test, and
`app/tests/e2e/status-bar.spec.ts`.

## Off-limits — one other agent is in this repo right now

`scripts/**`, `gatepack/**`, `Dockerfile*`, `.github/**` — the toolchain agent
is bundling yosys/sby/iverilog and touching the core's tool resolution.

Also off-limits: `app/shared/api.ts` (the contract is complete for this work),
`docs/MILESTONE-AUDIT.md`, `gatepack-design.md`.
