import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import {
  readStoredSession,
  sessionFile,
  writeStoredSession,
} from './session-store.cjs';

let tmp: string;

beforeEach(() => {
  tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'gatepack-session-'));
});

afterEach(() => {
  fs.rmSync(tmp, { recursive: true, force: true });
});

describe('readStoredSession', () => {
  it('returns null on a first launch (no file)', () => {
    expect(readStoredSession(tmp)).toEqual({ lastProjectPath: null });
  });

  it('returns the stored path after a write', () => {
    writeStoredSession(tmp, { lastProjectPath: '/home/x/proj' });
    expect(readStoredSession(tmp)).toEqual({ lastProjectPath: '/home/x/proj' });
  });

  it('returns null when the file is corrupt', () => {
    fs.writeFileSync(sessionFile(tmp), '{ not json');
    expect(readStoredSession(tmp)).toEqual({ lastProjectPath: null });
  });

  it('returns null when the path field is missing or the wrong type', () => {
    fs.writeFileSync(sessionFile(tmp), JSON.stringify({ other: 1 }));
    expect(readStoredSession(tmp)).toEqual({ lastProjectPath: null });
  });
});

describe('writeStoredSession', () => {
  it('creates the session directory when it does not exist', () => {
    const nested = path.join(tmp, 'a', 'b');
    writeStoredSession(nested, { lastProjectPath: '/p' });
    expect(fs.existsSync(sessionFile(nested))).toBe(true);
  });
});
