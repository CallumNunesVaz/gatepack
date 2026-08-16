import { describe, expect, it } from 'vitest';

import { buildCommandArgs } from './session.cjs';
import type { ProjectState } from './session.cjs';

// `buildCommandArgs` is the argv seam between the session manager and the core;
// the project-independent commands (doctor, listExamples, checkLibrary) are
// pinned here so a case that silently drops the path/name fails loudly.
describe('buildCommandArgs', () => {
  it('builds listExamples without a project', () => {
    expect(buildCommandArgs('listExamples', null)).toEqual(['examples', 'list']);
  });

  it('builds checkLibrary from an explicit path', () => {
    expect(buildCommandArgs('checkLibrary', null, '/tmp/parts.csv')).toEqual([
      'lib',
      'check',
      '/tmp/parts.csv',
    ]);
  });

  it('builds doctor without a project', () => {
    expect(buildCommandArgs('doctor', null)).toEqual(['doctor']);
  });

  it('keeps the project-scoped commands working against a project', () => {
    const project = { root: '/tmp/proj' } as unknown as ProjectState;
    expect(buildCommandArgs('compile', project)).toEqual([
      'compile',
      '/tmp/proj/design.yaml',
      '-o',
      '/tmp/proj/.gatepack/build',
    ]);
  });
});
