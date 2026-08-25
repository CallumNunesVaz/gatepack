import '@testing-library/jest-dom/vitest';
import { beforeEach } from 'vitest';
import { resetBuildState } from './renderer/state/buildState';
import { resetVerifySession } from './renderer/state/verifySession';

// The pipeline-session stores are module-scoped and written by any view that
// runs a build or a verification. A run in one test must not leak into the
// next (the strip compares against the *current* revision, so a stale leftover
// revision reads as "stale" and fails an unrelated test).
beforeEach(() => {
  resetBuildState();
  resetVerifySession();
});
