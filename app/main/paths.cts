/**
 * Path scoping (§5.2: "File access scoped to the opened project directory").
 *
 * Every path the renderer hands us is resolved, then checked — first
 * lexically, then against `realpath` — to be inside the project root. A
 * `../../etc/passwd`-style argument must be refused here, not caught later by
 * luck. Symlinks are resolved so a symlink planted inside the project pointing
 * at `/etc` is also refused.
 */

import * as fs from 'node:fs';
import * as path from 'node:path';

export class PathScopeError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'PathScopeError';
  }
}

/** True when `target` is `root` itself or a descendant of it (lexically). */
export function isInside(root: string, target: string): boolean {
  const rel = path.relative(root, target);
  return rel === '' || (!rel.startsWith('..') && !path.isAbsolute(rel));
}

/**
 * Resolve `candidate` against `root` and verify it stays inside `root` after
 * resolving symlinks. Returns the resolved absolute path, or throws
 * {@link PathScopeError}.
 */
export function resolveWithin(root: string, candidate: string): string {
  const rootAbs = path.resolve(root);
  const candidateAbs = path.resolve(rootAbs, candidate);

  if (!isInside(rootAbs, candidateAbs)) {
    throw new PathScopeError(`path escapes project root: ${candidate}`);
  }

  const realRoot = realpathExisting(rootAbs);
  const realCandidate = realpathExisting(candidateAbs);
  if (!isInside(realRoot, realCandidate)) {
    throw new PathScopeError(`path resolves outside project root: ${candidate}`);
  }

  return candidateAbs;
}

/**
 * `realpathSync` of a path that may not exist yet: resolve the nearest existing
 * ancestor and re-append the missing tail, so a write to a not-yet-created file
 * is still checked against the real location of its parent directory.
 */
export function realpathExisting(p: string): string {
  let cursor = p;
  const tail: string[] = [];
  // Walk up until an existing path is found.
  for (;;) {
    try {
      const real = fs.realpathSync(cursor);
      return path.join(real, ...tail.reverse());
    } catch {
      const parent = path.dirname(cursor);
      if (parent === cursor) {
        // Filesystem root does not exist: return the lexical form.
        return p;
      }
      tail.push(path.basename(cursor));
      cursor = parent;
    }
  }
}
