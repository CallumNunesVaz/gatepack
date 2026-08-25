/**
 * The pipeline strip — the stages under the topbar, drawn as the fork they are.
 *
 * One node per stage (`Spec`, `Build`, `Verify`), connected as the dependency
 * graph demands: `Spec` feeds `Build` on the top branch and `Verify` on the
 * bottom, and `Build` feeds the three artefact-reading views. A straight
 * four-box strip would be a lie about Verify, so this draws the fork.
 *
 * Each stage reports exactly one of five states (`done`/`ready`/`running`/
 * `blocked`/`stale`). The `ready` state is the actionable one — the stage that
 * needs running next — so the connector into it is the only connector that
 * animates, and only one at a time. A blocked stage is not clickable and names
 * what it waits for: a control that looks live and does nothing is worse than
 * no control.
 *
 * The travelling-dot connector reuses the `gp-schematic-flow` idiom from
 * `views.css`, so "signal moving" looks the same everywhere. The animation is
 * never the only carrier of state: each node also carries `data-state`, a
 * colour and a text label, so every state is readable under
 * `prefers-reduced-motion: reduce`.
 */

import { useMemo } from 'react';
import { useProject } from '../state/project';
import { useCommandBus } from './commands';
import { Spinner } from '../ui';
import {
  BUILD_FEEDS,
  computeStageStates,
  PIPELINE_STAGES,
  type StageId,
  type StageStatus,
} from './pipeline';
import { useBuildRevision, useBuildRunning, useBuildState } from '../state/buildState';
import { useVerifyRevision, useVerifyRunning } from '../state/verifySession';

function StageNode({
  status,
  onRun,
  area,
}: {
  status: StageStatus;
  onRun?: () => void;
  area: string;
}) {
  const def = PIPELINE_STAGES.find((s) => s.id === status.stageId)!;
  const runnable = def.command !== null && status.state !== 'blocked';
  const disabled = status.state === 'running';

  const content = (
    <>
      <span className="pipeline__stage-label">{def.label}</span>
      {status.state === 'running' ? (
        <Spinner size={12} label={`${def.label} running`} />
      ) : null}
      {status.state === 'blocked' && status.blocker ? (
        <span className="pipeline__stage-blocker">{status.blocker}</span>
      ) : null}
    </>
  );

  if (!runnable) {
    return (
      <div
        className={`pipeline__stage pipeline__stage--${status.state}`}
        data-stage={status.stageId}
        data-state={status.state}
        data-testid={`pipeline-stage-${status.stageId}`}
        style={{ gridArea: area }}
        title={status.blocker ?? undefined}
      >
        {content}
      </div>
    );
  }

  const action = status.state === 'ready' ? 'run' : 'run again';
  const label = `${def.label} — ${action}`;
  return (
    <button
      type="button"
      className={`pipeline__stage pipeline__stage--${status.state}`}
      data-stage={status.stageId}
      data-state={status.state}
      data-testid={`pipeline-stage-${status.stageId}`}
      style={{ gridArea: area }}
      disabled={disabled}
      aria-label={label}
      title={label}
      onClick={onRun}
    >
      {content}
    </button>
  );
}

function Connector({ active, area, testId }: { active: boolean; area: string; testId: string }) {
  return (
    <svg
      className="pipeline__connector"
      data-testid={testId}
      data-active={active || undefined}
      style={{ gridArea: area }}
      width="48"
      height="16"
      viewBox="0 0 48 16"
      aria-hidden="true"
      focusable="false"
    >
      <line className="pipeline__connector-track" x1="0" y1="8" x2="48" y2="8" />
      {active ? <line className="pipeline__connector-flow" x1="0" y1="8" x2="48" y2="8" /> : null}
    </svg>
  );
}

export function PipelineStrip() {
  const { project, diagnostics, revision } = useProject();
  const bus = useCommandBus();
  const buildState = useBuildState(revision);
  const buildRunning = useBuildRunning();
  const buildRevision = useBuildRevision();
  const verifyRevision = useVerifyRevision();
  const verifyRunning = useVerifyRunning();

  const errorCount = diagnostics.filter((d) => d.severity === 'error').length;

  const statuses = useMemo(
    () =>
      computeStageStates({
        projectOpen: project !== null,
        hasSpecErrors: errorCount > 0,
        specErrorCount: errorCount,
        hasMappedNetlist: buildState.state?.hasMappedNetlist ?? false,
        sourcesNewerThanBuild: buildState.state?.sourcesNewerThanBuild ?? null,
        buildRevision,
        verifyRevision,
        revision,
        buildRunning,
        verifyRunning,
      }),
    [
      project,
      errorCount,
      buildState.state,
      buildRevision,
      verifyRevision,
      revision,
      buildRunning,
      verifyRunning,
    ],
  );

  const byId = new Map<StageId, StageStatus>(statuses.map((s) => [s.stageId, s]));
  // The actionable stage: the first `ready` stage in pipeline order, one at a
  // time. Its connector is the only one that animates.
  const actionable = PIPELINE_STAGES.find((s) => byId.get(s.id)?.state === 'ready');

  const spec = byId.get('spec')!;
  const build = byId.get('build')!;
  const verify = byId.get('verify')!;

  return (
    <div className="shell__pipeline" data-testid="pipeline-strip" aria-label="Build pipeline">
      <StageNode status={spec} area="spec" />
      <Connector active={actionable?.id === 'build'} area="cBuild" testId="connector-spec-build" />
      <StageNode status={build} area="build" onRun={() => bus.dispatch('run.build')} />
      <Connector active={false} area="cViews" testId="connector-build-views" />
      <div
        className="pipeline__views"
        data-testid="pipeline-views"
        style={{ gridArea: 'views' }}
        title="Read the mapped netlist a build produces"
      >
        {BUILD_FEEDS.map((f) => f.label).join(' · ')}
      </div>
      <Connector active={actionable?.id === 'verify'} area="cVerify" testId="connector-spec-verify" />
      <StageNode status={verify} area="verify" onRun={() => bus.dispatch('run.verify')} />
    </div>
  );
}
