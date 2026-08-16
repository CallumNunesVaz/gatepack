/**
 * Child-process lifecycle for the Python core (§16 C9).
 *
 * The core is invoked as `gatepack <cmd> ... --json`; its stdout is captured
 * and parsed as exactly one JSON envelope. Everything the application shows is
 * produced by the core and read back here — never re-implemented, never faked.
 *
 * Locating the core, in priority order:
 *   1. `GATEPACK_CORE` (integration/test override),
 *   2. a bundled binary under `app/resources/bin/gatepack`,
 *   3. `.venv/bin/gatepack` relative to the project root,
 *   4. `gatepack` on `PATH`.
 * When none is found the caller surfaces a visible error envelope.
 */

import { spawn } from 'node:child_process';
import * as fs from 'node:fs';
import * as path from 'node:path';

import type { z } from 'zod';

import type { Envelope } from '../shared/api';
import { CancelRegistry, CancelledError, type ChildLike } from './cancel.cjs';
import { errorEnvelope, parseEnvelope } from './envelope.cjs';

export interface CoreLocation {
  executable: string;
  /** Arguments placed before the subcommand, e.g. `['-m', 'gatepack.cli']`. */
  prefixArgs: string[];
  /** Human-readable provenance of the location, for diagnostics. */
  source: string;
  /** Extra environment for the spawned process (merged over the inherited env). */
  env?: Record<string, string>;
}

export interface LocateOptions {
  appRoot: string;
  projectRoot: string;
  env: NodeJS.ProcessEnv;
  /**
   * `process.resourcesPath` — the directory electron-builder's
   * `extraResources` (from: resources, to: resources) lands in.  Only the
   * packaged app sets this; in dev it is undefined and the source-tree
   * location under `appRoot` is used instead.
   */
  resourcesPath?: string;
  /**
   * Platform used to resolve executable names (``gatepack`` vs
   * ``gatepack.exe``).  Defaults to ``process.platform``; a test passes
   * ``'win32'`` to exercise the Windows name on a POSIX host.
   */
  platform?: NodeJS.Platform;
}

/**
 * The on-disk executable name for ``base`` on ``platform``: Windows binaries
 * carry a ``.exe`` suffix, POSIX ones do not.  Kept as a pure function so the
 * Windows branch is testable without a Windows host.
 */
export function binaryName(base: string, platform: NodeJS.Platform = process.platform): string {
  return platform === 'win32' ? `${base}.exe` : base;
}

function isExecutable(p: string): boolean {
  try {
    fs.accessSync(p, fs.constants.X_OK);
    return fs.statSync(p).isFile();
  } catch {
    return false;
  }
}

/**
 * Locate the core executable, or return null. Never falls back to stub data:
 * the caller must surface a visible error envelope when this returns null.
 */
export function locateCore(opts: LocateOptions): CoreLocation | null {
  const { appRoot, projectRoot, env, resourcesPath } = opts;
  const platform = opts.platform ?? process.platform;

  const override = env.GATEPACK_CORE;
  if (override && override.length > 0 && isExecutable(override)) {
    return { executable: override, prefixArgs: [], source: 'GATEPACK_CORE' };
  }

  // §17's reserved location for the bundled core, in two shapes:
  //   * dev (appRoot is the app source dir): `app/resources/bin/gatepack`;
  //   * packaged (extraResources `to: resources`): `<resources>/resources/bin/gatepack`.
  // Both are checked because the packaged app's `appRoot` points inside the
  // asar (`…/resources/app.asar`), so the source-tree shape cannot resolve
  // there and the packaged shape does not exist in dev.  The name is the
  // platform's (`gatepack.exe` on Windows — PyInstaller appends the suffix).
  const coreName = binaryName('gatepack', platform);
  const bundledCandidates = [path.join(appRoot, 'resources', 'bin', coreName)];
  if (resourcesPath !== undefined && resourcesPath !== appRoot) {
    bundledCandidates.push(path.join(resourcesPath, 'resources', 'bin', coreName));
  }
  for (const bundled of bundledCandidates) {
    if (isExecutable(bundled)) {
      return { executable: bundled, prefixArgs: [], source: bundled };
    }
  }

  const venvScript = path.join(projectRoot, '.venv', 'bin', 'gatepack');
  if (isExecutable(venvScript)) {
    return { executable: venvScript, prefixArgs: [], source: venvScript };
  }

  // The venv may not have the console script installed (`pip install -e .`
  // not run); `python -m gatepack.cli` is the same entry point and is the
  // documented way to run the CLI from source (AGENTS.md). The `gatepack`
  // package lives at the project root, so point PYTHONPATH at it — otherwise
  // the module is only importable when the cwd happens to be the repo root.
  const venvPython = path.join(projectRoot, '.venv', 'bin', 'python');
  if (isExecutable(venvPython)) {
    return {
      executable: venvPython,
      prefixArgs: ['-m', 'gatepack.cli'],
      source: `${venvPython} -m gatepack.cli`,
      env: { PYTHONPATH: projectRoot },
    };
  }

  const pathGatepack = findOnPath('gatepack', env.PATH, platform);
  if (pathGatepack !== null) {
    return { executable: pathGatepack, prefixArgs: [], source: pathGatepack };
  }

  return null;
}

function findOnPath(
  name: string,
  searchPath: string | undefined,
  platform: NodeJS.Platform = process.platform,
): string | null {
  if (!searchPath) return null;
  const exeName = binaryName(name, platform);
  for (const dir of searchPath.split(path.delimiter)) {
    if (dir === '') continue;
    const candidate = path.join(dir, exeName);
    if (isExecutable(candidate)) return candidate;
  }
  return null;
}

export interface SpawnResult {
  code: number | null;
  stdout: string;
  stderr: string;
}

/** Spawn the core with `args`; resolves with raw output and exit code. */
export function spawnCore(location: CoreLocation, args: string[], cwd?: string): Promise<SpawnResult> {
  return new Promise((resolve) => {
    const child = spawn(location.executable, [...location.prefixArgs, ...args], {
      cwd,
      env: { ...process.env, ...(location.env ?? {}) },
    });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (d) => (stdout += String(d)));
    child.stderr.on('data', (d) => (stderr += String(d)));
    child.on('error', () => resolve({ code: null, stdout, stderr }));
    child.on('close', (code) => resolve({ code, stdout, stderr }));
  });
}

export type ProgressReporter = (stage: string, percent?: number) => void;

export interface RunCoreOptions {
  cwd?: string;
  token?: string;
  registry?: CancelRegistry;
  onProgress?: ProgressReporter;
}

/**
 * Run `gatepack <command> <args> --json`, capture stdout, parse exactly one
 * envelope, validate it against `schema`, and return it. When `token` is
 * supplied the process is registered so `cancel(token)` kills it and the
 * returned promise rejects with {@link CancelledError} rather than ever
 * resolving a stale result into the renderer.
 */
export function runEnvelope<T>(
  location: CoreLocation,
  schema: z.ZodType<T>,
  command: string,
  args: string[],
  options: RunCoreOptions = {},
): Promise<Envelope<T>> {
  const fullArgs = [...args, '--json'];
  return new Promise<Envelope<T>>((resolve, reject) => {
    let settled = false;
    const settle = (fn: () => void) => {
      if (settled) return;
      settled = true;
      fn();
    };

    const { token, registry, onProgress } = options;
    const child = spawn(location.executable, [...location.prefixArgs, ...fullArgs], {
      cwd: options.cwd,
      env: { ...process.env, ...(location.env ?? {}) },
    });
    let stdout = '';
    let stderr = '';

    let registered = false;
    if (token !== undefined && registry !== undefined) {
      const entry: { child: ChildLike | null; cancel: () => void } = {
        child: null,
        cancel: () => settle(() => reject(new CancelledError(token))),
      };
      entry.child = child as unknown as ChildLike;
      registry.add({ token, child: entry.child, cancel: entry.cancel });
      registered = true;
    }

    if (onProgress) onProgress('running');
    child.stdout.on('data', (d) => (stdout += String(d)));
    child.stderr.on('data', (d) => (stderr += String(d)));

    child.on('error', (err) => {
      settle(() => {
        if (registered && token !== undefined && registry !== undefined) {
          registry.delete(token);
        }
        reject(err);
      });
    });

    child.on('close', (code) => {
      settle(() => {
        if (registered && token !== undefined && registry !== undefined) {
          registry.delete(token);
        }
        if (onProgress) onProgress('done');
        const envelope = parseEnvelope(schema, stdout, command);
        // A non-zero exit that still claims `ok: true` is a lying core: never
        // pass it through. Prefer a visible error envelope.
        if (code !== 0 && envelope.ok) {
          resolve(
            errorEnvelope(
              command,
              'GP9004',
              `core exited ${code === null ? 'abnormally' : code}` +
                (stderr.trim() ? `: ${stderr.trim()}` : ''),
            ),
          );
          return;
        }
        resolve(envelope);
      });
    });
  });
}

/** Run a raw core invocation (no `--json`, no envelope), e.g. bundle/explode. */
export function runRaw(
  location: CoreLocation,
  args: string[],
  cwd?: string,
): Promise<SpawnResult> {
  return spawnCore(location, args, cwd);
}
