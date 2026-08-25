# Brief — signpost the pipeline, and animate what needs actioning

Read `docs/handoff/delegation-rules.md` first. Every rule there applies.

## The complaint

> "the steps blocking other sections (e.g. build comes before analysis) need to
> be more clearly signposted in the GUI"
> "Perhaps an animated pipeline at the top of the GUI to show what needs to be
> actioned?"

## What is actually true today — measured, not inferred

Run against a real project copied to a temp dir with `.gatepack/` deleted, then
each view opened in turn. This is the table you are fixing:

| View | What an unbuilt project shows | Verdict |
|---|---|---|
| Spec editor | the spec | fine |
| Truth table | fully populated — `compile` needs no build | fine |
| Schematic | `schematic unavailable — no mapped netlist at …/mapped.json: run \`gatepack build\` first` | **a CLI instruction in a GUI, with no build button on screen** |
| Packing & BOM | "Run a build to see the mapped cells and BOM." + a **Run build** button | **the model to copy** |
| Analysis | "Run analysis to see metrics." | **never mentions the build it requires** |
| Verification | "Run verification to see …" — and it *works*, unbuilt | fine, but indistinguishable from the two above |

Clicking **Run analysis** on an unbuilt project produces, on one screen:

```
no mapped netlist at …/mapped.json: run `gatepack build` first
VIABILITY: AMBER — package count is amber (value 26)
```

Both are true (`estimate` needs no build, `analyse` does) and nothing says so.
A verdict rendered beside an error, unlabelled, is this project's recurring
defect: **a status stronger than its evidence.**

### What each stage leaves on disk

Measured by calling each in turn and listing `.gatepack/`:

| Stage | Writes | Can its state be evidenced after a restart? |
|---|---|---|
| `compile` | `.gatepack/build/generated.v`, `properties.sv` | yes, but not where `buildState` looks |
| `build` | 13 files in `.gatepack/out/`, incl. `mapped.json` | **yes** |
| `verify` | **nothing** | **no** |

**`verify` leaves no trace.** After restarting the app a verified design is
indistinguishable from an unverified one. The strip must therefore never paint
Verify as done from anything except a verification that ran *in this session,
for the current revision*. Do not invent a manifest file to fix this. Do not
infer it from `report.md`. Report the state you can evidence.

### The real dependency shape

`verify` runs its own synthesis (`gatepack/verify/run.py` docstring: "Runs the
front-end (C1), Liberty + sim generation (C2), synthesis (C3, if Yosys is
present)"), so it is **not** gated on `build`. The pipeline is a fork:

```
Spec ──▶ Build ──▶ Schematic · Packing & BOM · Analysis
     └────────────▶ Verify
```

A straight four-box strip left-to-right would be a lie about Verify, and
drawing dependency graphs correctly is the entire point of this application.
Draw the fork.

## Already done for you — do not redo, do not edit `app/shared/api.ts`

`buildState()` is on the contract and implemented end to end (session → ipc →
preload → `FakeGatepack`). Both tsconfigs are clean with it in place.

```ts
export interface BuildState {
  outputDir: string;        // absolute; need not exist
  artefacts: string[];      // the readdir, sorted; [] when unbuilt
  hasMappedNetlist: boolean; // 'mapped.json' present
}
buildState(): Promise<Envelope<BuildState>>;
```

It reports **existence, not freshness** — deliberately. Staleness is the
project revision's job (§16.1) and the views already carry it. Do not conflate
them.

`FakeGatepack` defaults to **unbuilt** (`buildArtefacts: string[] = []`), so a
test has to opt *in* to a built project. Keep it that way.

## Build this

### 1. `app/renderer/shell/pipeline.ts` — one declaration of the order

The precedent is `shell/groups.ts`: the palette and the shortcuts sheet share
it so they cannot disagree about naming or order. Same here — the strip, the
rail and the in-view notes all read this, so there is exactly one place that
says what blocks what. Three views inventing their own answer is how the table
above happened.

Declare the stages, what each needs, the command that runs it, and — in prose
meant for a user, not a code comment — *why* a blocked view is blocked. Also
declare which view is blocked on which stage.

### 2. `app/renderer/state/buildState.ts` — the live answer

A hook over `buildState()`. Mirror the reload-signal pattern already in
`renderer/selection/linkData.ts` (`requestLinkReload` / `subscribeLinkReload` /
`getLinkReloadCount`) — that module exists because a fetch-once-on-mount view
went stale, which is exactly the failure available here. Re-fetch on project
revision change **and** on a build finishing, and make every site that calls
`api.build()` notify it. Miss one and the strip lies for the rest of the
session.

### 3. `app/renderer/shell/PipelineStrip.tsx` + CSS — the strip

Across the top, under `.shell__topbar`. Per stage:

| State | Meaning | Evidence |
|---|---|---|
| `done` | ran, current | Build: `hasMappedNetlist`. Spec: project open, no error diagnostics. Verify: ran this session for this revision |
| `ready` | prerequisite met, not yet run — **the actionable one** | — |
| `running` | in flight | the existing progress/task state |
| `blocked` | prerequisite unmet | name what it waits for |
| `stale` | ran, but for an older revision | the existing revision mechanism |

- Clicking a stage runs it. "Show what needs to be actioned" is worth much more
  if the thing is actionable from where it is shown. Dispatch through the
  command bus (`run.build`, `run.verify`) — do not call `api.*` directly, or
  the strip and the palette become two ways to run a build that behave
  differently.
- A `blocked` stage is not clickable and must say what it is waiting for.
  A control that looks live and does nothing is worse than no control.
- **Animate only the connector into the actionable stage, and only one at a
  time.** The whole strip in motion says nothing about where to look.
- Reuse the travelling-dot idiom already in `views.css`
  (`@keyframes gp-schematic-flow`) so the application has one visual language
  for "signal moving" rather than two.
- `tokens.css` states the rule and it is not negotiable: *"an animation may
  never be the only thing that communicates a state change."* Under
  `prefers-reduced-motion: reduce` every state must still be readable — the
  strip must pass its tests with motion off.

### 4. The three views

- **Schematic**: replace the `run \`gatepack build\` first` text with the shared
  note and a real **Run build** button. A GUI that tells you to go and type a
  CLI command has not finished the job.
- **Analysis**: say plainly which half is missing and why — `estimate` gave the
  viability verdict and needs no build; `analyse` gave nothing and does. Do not
  render an unlabelled verdict beside an error.
- **Packing & BOM**: switch to the shared note so there is one wording. It is
  already right; the point is that it stops being right *separately*.

## Tests, and how they must be able to fail

`app/renderer/shell/*.test.tsx` (vitest) for the strip and the pipeline
declaration; extend the Playwright specs for the real thing.

**A check that cannot fail is worth nothing** — this is the rule that has cost
this project the most. Concretely, for each of these, build the input that
makes it fail and keep it:

- Verify shows `done` **only** after a verification in this session. Assert that
  a fresh mount with `mapped.json` present and no verification run shows Verify
  as *not* done. If you cannot make that assertion fail by wiring Verify to
  disk state, the assertion is not testing anything.
- A `blocked` stage is not clickable **and** names its blocker.
- The strip still reports every state under `prefers-reduced-motion: reduce`.
- The build-finished signal reaches the strip: assert the strip flips from
  `ready` to `done` after a build, and confirm it fails when the notify call is
  removed from any one of its call sites.

A recent package here shipped a test that passed with the feature *removed*,
because the assertion held for an unrelated reason. Before you trust a test,
delete the code it covers and watch it fail.

## Write `docs/BUILD-NOTES-pipeline.md`

What you implemented, what you guessed, what is a placeholder, what you could
not verify, and what is weakest. On the last package the delegated notes
correctly identified the one real defect in the work before review found it —
that section earns its keep, so be blunt in it.
