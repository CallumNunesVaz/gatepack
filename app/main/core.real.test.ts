import * as fs from 'node:fs';
import * as path from 'node:path';
import { describe, expect, it } from 'vitest';

import { locateCore, spawnCore } from './core.cjs';

/**
 * Runs the *real* core if it is present in this worktree, and skips cleanly
 * when it is not (or when it is not invocable). This is the one test that is
 * not hermetic — the rest drive a fake core — and it deliberately does not use
 * `--json`: the core's `--json` flag is implemented in a parallel branch and
 * may not exist here. Proving the core is locatable and invocable is the point.
 */
function findRepoRoot(start: string): string {
  let cur = path.resolve(start);
  for (;;) {
    if (fs.existsSync(path.join(cur, 'pyproject.toml'))) return cur;
    const parent = path.dirname(cur);
    if (parent === cur) break;
    cur = parent;
  }
  return path.resolve(process.cwd(), '..');
}

const repoRoot = findRepoRoot(process.cwd());
const location = locateCore({
  appRoot: path.join(repoRoot, 'app'),
  projectRoot: repoRoot,
  env: process.env,
});

describe.skipIf(location === null)('real core', () => {
  it('locates and runs the real core (`--version`)', async () => {
    const loc = location!;
    const res = await spawnCore(loc, ['--version']);
    expect(res.code).toBe(0);
    expect(res.stdout).toContain('gatepack');
  });
});
