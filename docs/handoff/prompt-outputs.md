# Package O — the build outputs are written, never offered

Read `docs/handoff/delegation-rules.md` first. Every rule there applies.

## The gap

`gatepack build` writes the BOM, the KiCad netlist, the report and the netlists
into `.gatepack/out` inside the project. The application shows them — the BOM
view renders `bom.csv`'s contents — but gives you no way to *reach the files*:

- there is no **Reveal in folder** and no **Export** anywhere in the File menu
  or the command palette;
- nothing in `app/main/` calls `shell.showItemInFolder` or `shell.openPath` —
  grep for them, there are zero hits;
- **Save As** runs `gatepack project bundle`, which packages `design.yaml` and
  `parts.csv` — the **specification**, not the outputs.

So the last step of the job — handing a netlist and a BOM to a fabricator —
happens in a file manager. This is the only remaining boundary recorded in
`docs/MILESTONE-AUDIT.md` [GUI-1].

## The contract, and a narrow exception to the api.ts rule

The delegation rules say `app/shared/api.ts` is an input you must not edit. For
**these two additions only**, that is lifted — because it cannot work otherwise.
`api.ts` is structurally enforced at both ends: `GatepackApi` is implemented by
`app/preload/index.cts` and by `app/renderer/bridge/fake.ts`, so declaring a
method without implementing it fails `tsc` on both tsconfigs immediately. I
tried landing the contract ahead of the implementation and had to revert it. The
contract and its implementation are one commit's worth of work, not two.

So: add **exactly** these two members to the `GatepackApi` interface, verbatim,
including the comments. Nothing else in `api.ts` may change.

```ts
  /**
   * Reveal the build output directory in the OS file manager.
   *
   * `build` writes the BOM, the KiCad netlist and the report into
   * `.gatepack/out` inside the project and the application never offered them,
   * so handing a netlist to a fabricator meant leaving the app. Errors rather
   * than opening an empty directory when nothing has been built — an "outputs"
   * command that reveals nothing is worse than one that says there are none.
   */
  revealOutputs(): Promise<Envelope<{ path: string }>>;

  /**
   * Copy the build outputs to a directory the user picks in a native dialog.
   *
   * Reveal is enough to find them; this is for handing them on. The native
   * dialog is the trust boundary for writing outside the project root (§5.2),
   * so the destination is always chosen by the user and never by the renderer.
   */
  exportOutputs(): Promise<Envelope<{ path: string; files: string[] }>>;
```

If you believe the shape is wrong, implement it as given and say why in the
build notes. Do not redesign it.

`fake.ts` must implement both — it is in your scope, and the renderer tests all
run against it.

## The architecture to implement

Follow the path `newProject` took in `session.cts` / `ipc.cts` / `index.cts` /
`preload/index.cts`; it is the most recent example of exactly this shape and was
written to be copied.

### 1. `SessionManager.revealOutputs()`

- Resolve the output directory as `<project.root>/.gatepack/out`. `session.cts`
  already computes this path in `buildCommandArgs` (`outDir`) — do not hardcode
  a second copy of the layout; share it.
- **Error when the project is not open, or the directory does not exist or is
  empty.** An "outputs" command that opens an empty folder is a small lie of
  the kind this project spends most of its effort not telling. Use a `GP4xxx`
  code consistent with the family already in `session.cts` and `ipc.cts`
  (`GP4100`/`GP4101` open failures, `GP4111`/`GP4112` project failures,
  `GP4201` cancelled). Codes are free-form strings — `envelope.cts` types them
  as `z.string()` and holds only the `GP9xxx` bridge codes — so there is no
  registry to update and no validation to satisfy; pick one that reads as
  belonging to the set. Make the message say what to do ("run a build first"),
  not merely what went wrong.
- Reveal with Electron's `shell` module. Prefer `openPath` on the directory
  (opens the folder) over `showItemInFolder` on a file (opens the parent and
  selects it) — say in the build notes which you chose and why.
- `shell.openPath` resolves to a **string**: empty on success, an error message
  on failure. It does not reject. Returning `ok` without checking it is a
  silent failure, and it is the obvious mistake here.

### 2. `SessionManager.exportOutputs()`

- Show a native directory-chooser (`showOpenDialog`, `['openDirectory',
  'createDirectory']`), following `newViaDialog` in `ipc.cts`.
- Cancelled is not an error condition to hide — return the same shape the other
  dialogs use for a cancelled open (`GP4201`).
- Copy the build artefacts into the chosen directory. Copy the *artefacts*, not
  the whole directory: `bom.csv`, `netlist.net`, `report.md` are what a person
  hands on. Decide whether the intermediate files (`mapped.json`, `premap.json`,
  `cells.lib`, `yosys.ys`, ...) belong, and **justify the decision in the build
  notes** — there is a real argument either way and the reviewer wants to see
  that you made a choice rather than reached for `cp -r`.
- Return the destination and the list of files actually written.
- **Do not overwrite silently.** Decide the policy (refuse? suffix? overwrite?)
  and test it. Writing over a file the user already had there, with no warning,
  is the kind of thing that has to be deliberate.
- Writing outside the project root is a genuine widening of §5.2. It is
  acceptable **only** because a native dialog picked the destination. Never
  accept a destination path from the renderer.

### 3. IPC, preload, menu, palette

- `ipc.cts`: register both, no payload schema needed.
- `preload/index.cts`: expose both.
- `app/main/index.cts`: add to the File menu, near Save As. Suggested:
  `Reveal Outputs` and `Export Outputs…`. Pick accelerators that do not collide
  with the existing ones (`Mod+N/O/S/Shift+S/Shift+O/Q`) or use none.
- `app/renderer/keys/registry.ts`: add commands in the `project` group so they
  appear in the palette, and **register handlers for them in `Shell.tsx`** —
  `commands.tsx` says a reachable command that does nothing is a lie, and
  another package in this repo is currently fixing exactly that class of defect
  for the `run.*` commands. Do not add a third instance of it.

## Acceptance criteria

1. **`app/tests/e2e/app.spec.ts` pins the exact bridge surface** and will go red
   when you add two methods. That is the §5.2 posture working. Add them to the
   expected list **with a comment saying why the widening is safe**, exactly as
   `newProject`/`newProjectDialog` are recorded there.
2. **A test that a reveal with nothing built is refused**, and that a reveal
   with outputs present succeeds. Do not spawn a file manager in the test —
   inject or stub the `shell` call at the seam, and assert the seam was invoked
   with the right path.
3. **A test that export copies the files** into a destination directory and
   reports them, and one for the overwrite policy you chose.
4. `contract-commands.spec.ts` derives the commands the renderer invokes from
   `session.cts`. Neither of these runs a `gatepack` subcommand, so it should be
   unaffected — but run it and check, and if it does react, understand why
   before changing it.
5. Baselines, all of which must still pass:
   `.venv/bin/python -m pytest -q` (**904 pass, 5 skip**);
   from `app/`: `npx tsc --noEmit -p tsconfig.json`,
   `npx tsc --noEmit -p tsconfig.main.json`, `npx vitest run`,
   and after `npm run build`, `DISPLAY=:1 npx playwright test`.

   `app/tests/e2e/examples-end-to-end.spec.ts` and `schematic-pointer.spec.ts`
   need the `gatepack-toolchain:m6` docker image and take about a minute; they
   are expected to pass, not skip. Two other packages have landed in this branch
   before you, so the vitest and playwright counts will be higher than the
   numbers in the delegation rules — record what you actually measured.

## File scope

Yours: `app/main/session.cts`, `app/main/ipc.cts`, `app/main/index.cts`,
`app/main/envelope.cts`, `app/preload/index.cts`,
`app/renderer/keys/registry.ts`, `app/renderer/shell/Shell.tsx`,
`app/renderer/bridge/fake.ts`, `app/tests/e2e/app.spec.ts`, and new tests.

Plus `app/shared/api.ts`, for the two additions quoted above and nothing else.

Off-limits: everything else — anything under `gatepack/`,
`app/renderer/views/`, and every file in the "do not edit" list in the rules.

Write `docs/BUILD-NOTES-outputs.md`.
