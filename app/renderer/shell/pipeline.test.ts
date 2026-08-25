/**
 * The pipeline declaration and its pure state computation.
 *
 * Two things are pinned here and must be able to fail:
 *
 *   - the fork: `verify` is NOT gated on `build`. If someone draws the strip as
 *     a straight four-box chain, the declaration (and the strip) must say so;
 *   - `verify` shows `done` only from a run in this session, never from disk
 *     state (`hasMappedNetlist`).
 */

import { describe, expect, it } from 'vitest';
import {
  computeStageStates,
  PIPELINE_STAGES,
  VIEW_BLOCKS,
  type PipelineInputs,
} from './pipeline';

function inputs(over: Partial<PipelineInputs> = {}): PipelineInputs {
  return {
    projectOpen: true,
    hasSpecErrors: false,
    specErrorCount: 0,
    hasMappedNetlist: false,
    buildRevision: null,
    verifyRevision: null,
    revision: 1,
    buildRunning: false,
    verifyRunning: false,
    ...over,
  };
}

function stateOf(result: ReturnType<typeof computeStageStates>, id: string) {
  return result.find((s) => s.stageId === id)!;
}

describe('the pipeline declaration is a fork', () => {
  it('verify requires spec, not build', () => {
    const verify = PIPELINE_STAGES.find((s) => s.id === 'verify')!;
    const build = PIPELINE_STAGES.find((s) => s.id === 'build')!;
    expect(build.requires).toEqual(['spec']);
    // The whole point of the fork: verify is not gated on build.
    expect(verify.requires).toEqual(['spec']);
    expect(verify.requires).not.toContain('build');
  });

  it('build feeds the three artefact-reading views and nothing more', () => {
    expect(VIEW_BLOCKS.schematic.blockedBy).toBe('build');
    expect(VIEW_BLOCKS.packing.blockedBy).toBe('build');
    expect(VIEW_BLOCKS.analysis.blockedBy).toBe('build');
    expect(VIEW_BLOCKS.verify.blockedBy).toBeNull();
    expect(VIEW_BLOCKS.truthtable.blockedBy).toBeNull();
    expect(VIEW_BLOCKS.spec.blockedBy).toBeNull();
  });
});

describe('computeStageStates', () => {
  it('a fresh unbuilt project marks Build ready and Verify ready', () => {
    const r = computeStageStates(inputs());
    expect(stateOf(r, 'spec').state).toBe('done');
    expect(stateOf(r, 'build').state).toBe('ready');
    expect(stateOf(r, 'verify').state).toBe('ready');
  });

  it('verify is NOT done from disk state — mapped.json present, no session run', () => {
    const r = computeStageStates(inputs({ hasMappedNetlist: true, buildRevision: 1 }));
    expect(stateOf(r, 'build').state).toBe('done');
    // mapped.json says nothing about verification: it must stay ready.
    expect(stateOf(r, 'verify').state).toBe('ready');
  });

  it('verify is done only after a run this session for this revision', () => {
    const r = computeStageStates(inputs({ verifyRevision: 1 }));
    expect(stateOf(r, 'verify').state).toBe('done');
  });

  it('a session verify for an older revision is stale, not done', () => {
    const r = computeStageStates(inputs({ verifyRevision: 0, revision: 1 }));
    expect(stateOf(r, 'verify').state).toBe('stale');
  });

  it('a build observed at an older revision is stale', () => {
    const r = computeStageStates(
      inputs({ hasMappedNetlist: true, buildRevision: 0, revision: 1 }),
    );
    expect(stateOf(r, 'build').state).toBe('stale');
  });

  it('running wins over every other state', () => {
    const r = computeStageStates(inputs({ buildRunning: true, hasMappedNetlist: true, buildRevision: 1 }));
    expect(stateOf(r, 'build').state).toBe('running');
    const v = computeStageStates(inputs({ verifyRunning: true, verifyRevision: 1 }));
    expect(stateOf(v, 'verify').state).toBe('running');
  });

  it('a blocked stage names what it waits for', () => {
    const r = computeStageStates(inputs({ hasSpecErrors: true, specErrorCount: 3 }));
    expect(stateOf(r, 'spec').state).toBe('blocked');
    expect(stateOf(r, 'spec').blocker).toBe('3 errors in the spec');
    // Both branches inherit the spec's blocker.
    expect(stateOf(r, 'build').state).toBe('blocked');
    expect(stateOf(r, 'build').blocker).toBe('3 errors in the spec');
    expect(stateOf(r, 'verify').state).toBe('blocked');
  });

  it('no project open blocks the spec (and therefore both branches)', () => {
    const r = computeStageStates(inputs({ projectOpen: false }));
    expect(stateOf(r, 'spec').state).toBe('blocked');
    expect(stateOf(r, 'spec').blocker).toBe('no project open');
    expect(stateOf(r, 'build').state).toBe('blocked');
    expect(stateOf(r, 'verify').state).toBe('blocked');
  });
});
