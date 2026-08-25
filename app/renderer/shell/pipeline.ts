/**
 * The pipeline's order and blocking rules — one declaration, several readers.
 *
 * The precedent is `groups.ts`: the palette and the shortcuts sheet share it so
 * they cannot disagree about naming or order. Same here — the pipeline strip,
 * the view ids the shell switches between, and the in-view notes all read this
 * file, so there is exactly one place that says what blocks what. Three views
 * discovering the order for themselves by failing is how the table in
 * docs/GUI-AUDIT.md [GUI-5] happened: the schematic told a GUI user to "run
 * `gatepack build` first" with no build button on screen, analysis offered
 * "Run analysis to see metrics" without mentioning the build it requires, and
 * verification — which needs no build at all — was indistinguishable from the
 * two that do.
 *
 * The pipeline is a **fork**, not a line:
 *
 *   Spec ──▶ Build ──▶ Schematic · Packing & BOM · Analysis
 *        └────────────▶ Verify
 *
 * `verify` runs its own synthesis and is *not* gated on `build`. Drawing it as
 * a straight left-to-right chain of four boxes would be a lie, and drawing
 * dependency graphs correctly is the entire point of this application. The
 * `requires` field encodes the fork: `build.requires` and `verify.requires` are
 * both `['spec']`, and nothing anywhere says verify requires build.
 */

export type ViewId = 'spec' | 'truthtable' | 'schematic' | 'packing' | 'analysis' | 'verify';

export type StageId = 'spec' | 'build' | 'verify';

export type StageState = 'done' | 'ready' | 'running' | 'blocked' | 'stale';

export interface StageDef {
  id: StageId;
  /** Short, user-facing label. */
  label: string;
  /**
   * The command-bus id that runs this stage, or null when it cannot be run.
   * The strip dispatches this — never `api.*` directly — so the strip and the
   * palette are one way to run a build, not two that behave differently.
   */
  command: string | null;
  /** The stage(s) this one waits for. Empty for the source. */
  requires: StageId[];
}

export const PIPELINE_STAGES: readonly StageDef[] = [
  { id: 'spec', label: 'Spec', command: null, requires: [] },
  { id: 'build', label: 'Build', command: 'run.build', requires: ['spec'] },
  { id: 'verify', label: 'Verify', command: 'run.verify', requires: ['spec'] },
];

/**
 * The views a completed build feeds. They are not stages to run — they are
 * downstream consumers of `build`'s artefacts, drawn after the Build node so
 * the fork is visible.
 */
export const BUILD_FEEDS: readonly { viewId: ViewId; label: string }[] = [
  { viewId: 'schematic', label: 'Schematic' },
  { viewId: 'packing', label: 'Packing & BOM' },
  { viewId: 'analysis', label: 'Analysis' },
];

/**
 * Which view is blocked on which stage, and — in prose meant for a user, not a
 * code comment — why a blocked view is blocked. The in-view notes render this
 * wording, so the schematic, the packing view and the analysis view can no
 * longer each invent their own (three different) explanation.
 */
export interface ViewBlock {
  viewId: ViewId;
  /** The stage that gates this view, or null when nothing does. */
  blockedBy: StageId | null;
  /** User-facing prose for the view's empty/unbuilt state. */
  note: string;
}

export const VIEW_BLOCKS: Record<ViewId, ViewBlock> = {
  spec: { viewId: 'spec', blockedBy: null, note: '' },
  truthtable: { viewId: 'truthtable', blockedBy: null, note: '' },
  schematic: {
    viewId: 'schematic',
    blockedBy: 'build',
    note: 'The schematic reads the mapped netlist, which only exists after a build.',
  },
  packing: {
    viewId: 'packing',
    blockedBy: 'build',
    note: 'Run a build to see the mapped cells and BOM.',
  },
  analysis: {
    viewId: 'analysis',
    blockedBy: 'build',
    note:
      'The viability verdict comes from estimate and needs no build; the metrics ' +
      'come from analyse, which reads the mapped netlist and needs a build first.',
  },
  verify: { viewId: 'verify', blockedBy: null, note: '' },
};

/* ------------------------------------------------------------------ */
/* The pure state computation.                                         */
/* ------------------------------------------------------------------ */

export interface PipelineInputs {
  projectOpen: boolean;
  hasSpecErrors: boolean;
  specErrorCount: number;
  hasMappedNetlist: boolean;
  /** Revision the build artefacts were built/observed at, or null when unbuilt. */
  buildRevision: number | null;
  /** Revision a verification ran at this session, or null when it has not. */
  verifyRevision: number | null;
  revision: number;
  buildRunning: boolean;
  verifyRunning: boolean;
}

export interface StageStatus {
  stageId: StageId;
  state: StageState;
  /** Why the stage is blocked — names the blocker. */
  blocker?: string;
}

function specStatus(inputs: PipelineInputs): StageStatus {
  if (!inputs.projectOpen) {
    return { stageId: 'spec', state: 'blocked', blocker: 'no project open' };
  }
  if (inputs.hasSpecErrors) {
    const n = inputs.specErrorCount;
    return {
      stageId: 'spec',
      state: 'blocked',
      blocker: `${n} error${n === 1 ? '' : 's'} in the spec`,
    };
  }
  return { stageId: 'spec', state: 'done' };
}

export function computeStageStates(inputs: PipelineInputs): StageStatus[] {
  const spec = specStatus(inputs);
  const specBlocked = spec.state !== 'done';

  const build: StageStatus = (() => {
    if (inputs.buildRunning) return { stageId: 'build', state: 'running' };
    if (specBlocked) return { stageId: 'build', state: 'blocked', blocker: spec.blocker };
    if (!inputs.hasMappedNetlist) return { stageId: 'build', state: 'ready' };
    if (inputs.buildRevision !== null && inputs.buildRevision !== inputs.revision) {
      return { stageId: 'build', state: 'stale' };
    }
    return { stageId: 'build', state: 'done' };
  })();

  const verify: StageStatus = (() => {
    if (inputs.verifyRunning) return { stageId: 'verify', state: 'running' };
    if (specBlocked) return { stageId: 'verify', state: 'blocked', blocker: spec.blocker };
    // `verify` leaves nothing on disk, so the ONLY evidence that it ran is a
    // run in this session. No `verifyRevision` means it has not run here.
    if (inputs.verifyRevision === null) return { stageId: 'verify', state: 'ready' };
    if (inputs.verifyRevision !== inputs.revision) return { stageId: 'verify', state: 'stale' };
    return { stageId: 'verify', state: 'done' };
  })();

  return [spec, build, verify];
}
