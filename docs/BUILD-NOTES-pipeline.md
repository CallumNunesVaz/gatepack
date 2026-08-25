# Build notes — pipeline signposting (§GUI-5)

The delegated run was cut short: it was auto-rejected on `cp … /tmp/bom_backup.tsx`
(an outside-the-worktree write), and a rejection ends the run. It had already
reached both tsconfigs clean and vitest 488, but never wrote these notes or its
own summary. This file is written from review of the delivered diff plus my own
verification, and says so wherever the distinction matters.

## What was implemented

| File | What it does |
|---|---|
| `renderer/shell/pipeline.ts` | The single declaration: stages, what each requires, which view is blocked on what, and the pure `computeStageStates`. The `groups.ts` precedent. |
| `renderer/shell/PipelineStrip.tsx` | The strip under the topbar, drawn as a fork. |
| `renderer/state/buildState.ts` | `useBuildState` over `api.buildState()`, plus reload / running / revision signals. |
| `renderer/state/verifySession.ts` | Session-only verification evidence. |
| `views/{Schematic,BomView,AnalysisView,VerificationPanel}.tsx` | Publish into those signals; render the shared blocking note. |

## Verified, not taken on trust

Each of these was falsified — the fix reverted, the failure observed, the fix
restored:

- **Verify is never painted from disk.** Wiring `verify` to `hasMappedNetlist`
  fails `does not paint Verify as done from disk state`.
- **Both build call sites notify.** Deleting `requestBuildStateReload()` from
  `BomView` fails one test; deleting it from `Schematic` fails another. There are
  exactly two `api.build()` call sites and both are covered.
- **The strip's `done` means an artefact exists.** The e2e test clicks the
  strip's own Build node against the real toolchain and then asserts
  `mapped.json` is on disk. An earlier version of that test failed at exactly
  that assertion, so it can fail.

## What I changed in review

- **The citation.** `pipeline.ts` cited `docs/GUI-AUDIT.md [GUI-5]`. The
  `[GUI-n]` sections live in `docs/MILESTONE-AUDIT.md`. It inherited this from my
  brief, where I had made the same mistake.
- **One change I made and then reverted.** I added the core's own error message
  beside the Analysis blocking note, on the grounds that explaining an error is
  helpful but swallowing it is misdirection. That was wrong here: the note only
  renders when `buildState` has *positively confirmed from disk* that
  `mapped.json` is absent, and in exactly that case the core's message adds
  nothing but the `run \`gatepack build\` first` CLI instruction that [GUI-5] is
  about. The delegated version is better. Its own test caught me.

## Weakest points

1. **The strip learns of a build only from the reload signal.** A build run
   outside the application — the CLI, a second window — does not reach it, and
   the strip goes on showing `ready` for a project that has a netlist. It
   under-reports rather than over-reports, which is the safe direction, but it
   is a limitation and not a design decision. The watcher cannot help: builds
   write into `.gatepack/`, which is in `IGNORED_SEGMENTS` deliberately.

2. ~~**`buildRevision` is observed, not measured.**~~ **Fixed in review.**
   Artefacts carry no revision, so the delivered version could only record "I
   observed a build now" and detect staleness from edits made *afterwards*: a
   project opened with an already-stale build reported `done` until the user next
   typed. That is a real over-claim, and the filesystem already knew the answer.

   `buildState()` now returns `sourcesNewerThanBuild`, comparing `mapped.json`'s
   mtime against `design.yaml` *and* `parts.csv` — a parts-table edit changes
   what a build would produce just as a spec edit does. The measurement outranks
   the observation in `computeStageStates`; the observation is kept as the
   fallback for when the filesystem cannot answer, because a session's own
   knowledge of an edit is still evidence. `null` means unknown and is reported
   as neither fresh nor stale.

   Falsified three ways: removing the measured branch fails the "stale even when
   this session observed it as current" test; dropping `parts.csv` from the
   source list fails the parts-table test; and the unknown case is pinned
   separately.

3. **The reduced-motion test proves less than it appears to.** jsdom applies no
   CSS, so it cannot observe that the animation stopped. What it actually pins is
   that state is carried on `data-state` and in text rather than by the moving
   dot — which is the property that matters, but the test name oversells it. The
   delegated code says so in its own comment, correctly.

4. **There is no `failed` stage state.** A build that errors leaves the strip at
   `ready`. That is defensible (no netlist was produced, so running it is still
   the next action) and the failure is toasted, but the strip is silent about it.

## Still open

- **Nothing outside the app reaches the strip** (weakness 1 above). Unfixed, and
  the safe direction to be wrong in.
- **No `failed` stage state** (weakness 4 above). Unfixed.

## Not done

- The delegated run never wrote its own build notes or summary, so its
  self-assessment — which on the previous package correctly identified the one
  real defect before review found it — is missing here. Points 1–4 above are mine.
