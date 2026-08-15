/**
 * Git status for the project root (§16 C9: branch + dirty files, or `null`
 * when the directory is not in a git working tree). Shells out to `git`; no
 * library. The parsing functions are pure so they can be unit-tested; the
 * shelling-out is injectable for the same reason.
 */

import { spawn } from 'node:child_process';

export interface GitStatus {
  branch: string;
  dirtyFiles: string[];
}

/** Parse `git rev-parse --abbrev-ref HEAD` into a branch name, or null. */
export function parseBranch(stdout: string): string | null {
  const branch = stdout.trim();
  if (branch === '') return null;
  if (branch === 'HEAD') return null; // detached HEAD
  return branch;
}

/**
 * Parse `git status --porcelain` output. Each line is `XY path` or
 * `XY orig -> new`; we return the affected path (the rename target when the
 * line is a rename). Quoting edge cases are deliberately not handled — the
 * porcelain format's C-style quoting is rare and the field is display-only.
 */
export function parseStatusPorcelain(stdout: string): string[] {
  return stdout
    .split('\n')
    .map((line) => line.slice(3).trim())
    .filter((line) => line.length > 0)
    .map((line) => {
      const arrow = line.indexOf(' -> ');
      return arrow >= 0 ? line.slice(arrow + 4) : line;
    });
}

export interface ExecResult {
  code: number;
  stdout: string;
  stderr: string;
}

export type Exec = (args: string[], opts?: { cwd?: string }) => Promise<ExecResult>;

/** Run `git` via `spawn`; returns raw output without throwing. */
export const gitExec: Exec = (args, opts) => {
  return new Promise((resolve) => {
    const child = spawn('git', args, { cwd: opts?.cwd });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (d) => (stdout += String(d)));
    child.stderr.on('data', (d) => (stderr += String(d)));
    child.on('error', () => resolve({ code: -1, stdout, stderr }));
    child.on('close', (code) => resolve({ code: code ?? -1, stdout, stderr }));
  });
};

/**
 * Read the git status for `dir` (branch + dirty files), or null when `dir` is
 * not inside a git working tree. The repository root is discovered by asking
 * `git rev-parse --show-toplevel`, so a project opened in a subdirectory still
 * reports the whole repository's branch.
 */
export async function readGitStatus(
  dir: string,
  exec: Exec = gitExec,
): Promise<GitStatus | null> {
  const toplevel = await exec(['rev-parse', '--show-toplevel'], { cwd: dir });
  if (toplevel.code !== 0) return null;

  const branch = await exec(['rev-parse', '--abbrev-ref', 'HEAD'], { cwd: dir });
  const status = await exec(['status', '--porcelain'], { cwd: dir });
  if (status.code !== 0) return null;

  return {
    branch: parseBranch(branch.stdout) ?? 'HEAD',
    dirtyFiles: parseStatusPorcelain(status.stdout),
  };
}
