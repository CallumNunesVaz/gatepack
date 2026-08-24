/**
 * §GUI-1: the build outputs are written, not offered — this pins the fix.
 *
 * `revealOutputs` and `exportOutputs` are the two halves of "reach the files
 * `build` wrote". The reveal seam (`SessionDeps.shell`) is injected so no test
 * spawns a file manager: a stub records the path and returns the string
 * Electron's `shell.openPath` would (empty on success, an error message on
 * failure), which also pins the "check the result, don't assume ok" behaviour.
 */

import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { CancelRegistry } from './cancel.cjs';
import { SessionManager, type SessionDeps } from './session.cjs';

const DESIGN = 'name: outputs_test\n';

let tmp: string;
let projectDir: string;
let session: SessionManager | null;
let shellCalls: string[];

/** A shell seam that records every path and resolves to `result`. */
function shellSeam(result: string): SessionDeps['shell'] {
  return {
    openPath: (fullPath: string) => {
      shellCalls.push(fullPath);
      return Promise.resolve(result);
    },
  };
}

function makeSession(shellResult = ''): SessionManager {
  shellCalls = [];
  const deps: SessionDeps = {
    location: null,
    registry: new CancelRegistry(),
    examplesRoot: null,
    onProjectChanged: () => {},
    onFileChanged: () => {},
    onProgress: () => {},
    // Not a git tree — avoids spawning `git` in every test.
    gitExec: async () => ({ code: 1, stdout: '', stderr: '' }),
    shell: shellSeam(shellResult),
  };
  return new SessionManager(deps);
}

function outDir(): string {
  return path.join(projectDir, '.gatepack', 'out');
}

async function openProject(sm: SessionManager): Promise<void> {
  const env = await sm.openProjectPath(projectDir);
  expect(env.ok).toBe(true);
}

function writeArtefacts(dir: string, files: string[] = ['bom.csv', 'netlist.net', 'report.md']): void {
  fs.mkdirSync(dir, { recursive: true });
  for (const f of files) fs.writeFileSync(path.join(dir, f), `content of ${f}\n`);
}

beforeEach(() => {
  tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'gatepack-outputs-'));
  projectDir = path.join(tmp, 'project');
  fs.mkdirSync(projectDir, { recursive: true });
  fs.writeFileSync(path.join(projectDir, 'design.yaml'), DESIGN);
  shellCalls = [];
  session = null;
});

afterEach(() => {
  if (session) session.dispose();
  session = null;
  fs.rmSync(tmp, { recursive: true, force: true });
});

describe('revealOutputs', () => {
  it('refuses with nothing built — the directory does not exist', async () => {
    session = makeSession();
    await openProject(session);
    const env = await session.revealOutputs();
    expect(env.ok).toBe(false);
    if (!env.ok) {
      expect(env.error.code).toBe('GP4113');
      expect(env.error.message).toMatch(/run a build first/);
    }
    expect(shellCalls).toEqual([]);
  });

  it('refuses with nothing built — the directory exists but is empty', async () => {
    fs.mkdirSync(outDir(), { recursive: true });
    session = makeSession();
    await openProject(session);
    const env = await session.revealOutputs();
    expect(env.ok).toBe(false);
    if (!env.ok) {
      expect(env.error.code).toBe('GP4113');
      expect(env.error.message).toMatch(/run a build first/);
    }
    expect(shellCalls).toEqual([]);
  });

  it('refuses when no project is open', async () => {
    session = makeSession();
    const env = await session.revealOutputs();
    expect(env.ok).toBe(false);
    if (!env.ok) expect(env.error.code).toBe('GP4200');
    expect(shellCalls).toEqual([]);
  });

  it('reveals the output directory when outputs are present', async () => {
    writeArtefacts(outDir());
    session = makeSession();
    await openProject(session);
    const env = await session.revealOutputs();
    expect(env.ok).toBe(true);
    if (env.ok) expect(env.data.path).toBe(outDir());
    // The seam was invoked with exactly the output directory.
    expect(shellCalls).toEqual([outDir()]);
  });

  it('does not report ok when the shell fails to open the path', async () => {
    writeArtefacts(outDir());
    session = makeSession('Failed to open: permission denied');
    await openProject(session);
    const env = await session.revealOutputs();
    expect(env.ok).toBe(false);
    if (!env.ok) {
      expect(env.error.code).toBe('GP4114');
      expect(env.error.message).toContain('permission denied');
    }
    expect(shellCalls).toEqual([outDir()]);
  });
});

describe('exportOutputs', () => {
  it('copies the artefacts into the destination and reports them', async () => {
    writeArtefacts(outDir());
    session = makeSession();
    await openProject(session);

    const dest = path.join(tmp, 'handoff');
    const env = await session.exportOutputs(dest);

    expect(env.ok).toBe(true);
    if (!env.ok) throw new Error('expected ok');

    expect(env.data.path).toBe(dest);
    expect(env.data.files.sort()).toEqual(
      ['bom.csv', 'netlist.net', 'report.md'].map((f) => path.join(dest, f)).sort(),
    );

    // Only the three hand-over artefacts were copied — not the intermediates.
    expect(fs.readdirSync(dest).sort()).toEqual(['bom.csv', 'netlist.net', 'report.md']);
    for (const f of ['bom.csv', 'netlist.net', 'report.md']) {
      expect(fs.readFileSync(path.join(dest, f), 'utf8')).toBe(`content of ${f}\n`);
    }
  });

  it('refuses to overwrite an existing file rather than clobbering it', async () => {
    writeArtefacts(outDir());
    session = makeSession();
    await openProject(session);

    const dest = path.join(tmp, 'handoff');
    fs.mkdirSync(dest, { recursive: true });
    fs.writeFileSync(path.join(dest, 'bom.csv'), 'the user had this already\n');

    const env = await session.exportOutputs(dest);
    expect(env.ok).toBe(false);
    if (!env.ok) {
      expect(env.error.code).toBe('GP4115');
      expect(env.error.message).toContain('bom.csv');
    }
    // Nothing was written over: the pre-existing file is untouched and the
    // other two artefacts were not copied either (the export is all-or-nothing).
    expect(fs.readFileSync(path.join(dest, 'bom.csv'), 'utf8')).toBe('the user had this already\n');
    expect(fs.readdirSync(dest)).toEqual(['bom.csv']);
  });

  it('refuses with nothing built', async () => {
    session = makeSession();
    await openProject(session);
    const env = await session.exportOutputs(path.join(tmp, 'handoff'));
    expect(env.ok).toBe(false);
    if (!env.ok) {
      expect(env.error.code).toBe('GP4113');
      expect(env.error.message).toMatch(/run a build first/);
    }
  });

  it('refuses when a required artefact is missing from the output directory', async () => {
    writeArtefacts(outDir(), ['bom.csv', 'report.md']);
    session = makeSession();
    await openProject(session);
    const env = await session.exportOutputs(path.join(tmp, 'handoff'));
    expect(env.ok).toBe(false);
    if (!env.ok) {
      expect(env.error.code).toBe('GP4113');
      expect(env.error.message).toContain('netlist.net');
    }
  });

  it('refuses when no project is open', async () => {
    session = makeSession();
    const env = await session.exportOutputs(path.join(tmp, 'handoff'));
    expect(env.ok).toBe(false);
    if (!env.ok) expect(env.error.code).toBe('GP4200');
  });
});
