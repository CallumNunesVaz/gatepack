/**
 * Last-opened-project persistence for C9 (§16, §18.1).
 *
 * The showcase is the no-prior-session default: the first launch opens it, and
 * a project the user opens afterwards is remembered so the *next* launch
 * reopens that project instead. A tiny JSON file in the session directory
 * (Electron `userData`, or `GATEPACK_SESSION_DIR` in tests) holds it; there is
 * nothing else worth persisting yet, so the format is deliberately minimal.
 */

import * as fs from 'node:fs';
import * as path from 'node:path';

export interface StoredSession {
  /** Absolute path of the last-opened project (directory or `.gpk`), or null. */
  lastProjectPath: string | null;
}

const FILE_NAME = 'session.json';

export function sessionFile(dir: string): string {
  return path.join(dir, FILE_NAME);
}

/** Read the stored session; a missing/corrupt file means no prior session. */
export function readStoredSession(dir: string): StoredSession {
  try {
    const raw = fs.readFileSync(sessionFile(dir), 'utf8');
    const parsed = JSON.parse(raw) as unknown;
    if (
      parsed !== null &&
      typeof parsed === 'object' &&
      typeof (parsed as Record<string, unknown>).lastProjectPath === 'string'
    ) {
      return {
        lastProjectPath: (parsed as { lastProjectPath: string }).lastProjectPath,
      };
    }
  } catch {
    // Missing, unreadable or malformed -> treat as a first launch.
  }
  return { lastProjectPath: null };
}

/** Write the stored session, creating the session directory if needed. */
export function writeStoredSession(dir: string, session: StoredSession): void {
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(sessionFile(dir), JSON.stringify(session, null, 2) + '\n');
}
