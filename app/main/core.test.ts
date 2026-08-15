import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { CancelRegistry, CancelledError } from './cancel.cjs';
import { locateCore, runEnvelope, spawnCore, type CoreLocation } from './core.cjs';
import { CompileResultSchema } from './envelope.cjs';

const COMPILE_ENVELOPE = JSON.stringify({
  ok: true,
  command: 'compile',
  schema: 1,
  data: {
    verilogPath: '/tmp/build/generated.v',
    propertiesPath: null,
    flopCount: 2,
    stateCount: 3,
    encoding: 'one_hot',
    johnsonSuggestion: null,
  },
  warnings: [],
});

function writeFakeCore(dir: string, body: string): string {
  const p = path.join(dir, 'fake-gatepack');
  fs.writeFileSync(p, `#!/bin/sh\n${body}\n`);
  fs.chmodSync(p, 0o755);
  return p;
}

let tmp: string;

beforeEach(() => {
  tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'gatepack-core-'));
});

afterEach(() => {
  fs.rmSync(tmp, { recursive: true, force: true });
});

describe('locateCore', () => {
  it('returns null when nothing is available', () => {
    const loc = locateCore({
      appRoot: tmp,
      projectRoot: tmp,
      env: { GATEPACK_CORE: undefined, PATH: '' },
    });
    expect(loc).toBeNull();
  });

  it('prefers the GATEPACK_CORE override', () => {
    const fake = writeFakeCore(tmp, "printf '%s\\n' '{}'");
    const loc = locateCore({
      appRoot: tmp,
      projectRoot: tmp,
      env: { GATEPACK_CORE: fake, PATH: '' },
    });
    expect(loc?.executable).toBe(fake);
    expect(loc?.source).toBe('GATEPACK_CORE');
  });
});

describe('runEnvelope', () => {
  it('returns a validated ok envelope from a fake core', async () => {
    const fake = writeFakeCore(tmp, `printf '%s\\n' '${COMPILE_ENVELOPE}'`);
    const location: CoreLocation = { executable: fake, prefixArgs: [], source: 'test' };
    const env = await runEnvelope(location, CompileResultSchema, 'compile', [], {});
    expect(env.ok).toBe(true);
    if (env.ok) expect(env.data.flopCount).toBe(2);
  });

  it('surfaces a non-zero exit that claimed ok as an error envelope', async () => {
    const fake = writeFakeCore(tmp, `printf '%s\\n' '${COMPILE_ENVELOPE}'\nexit 1`);
    const location: CoreLocation = { executable: fake, prefixArgs: [], source: 'test' };
    const env = await runEnvelope(location, CompileResultSchema, 'compile', [], {});
    expect(env.ok).toBe(false);
    if (!env.ok) expect(env.error.code).toBe('GP9004');
  });

  it('rejects when the executable cannot be spawned', async () => {
    const location: CoreLocation = {
      executable: path.join(tmp, 'does-not-exist'),
      prefixArgs: [],
      source: 'test',
    };
    await expect(runEnvelope(location, CompileResultSchema, 'compile', [], {})).rejects.toThrow();
  });
});

describe('runEnvelope cancellation', () => {
  it('a cancelled call rejects with CancelledError and never resolves', async () => {
    const fake = writeFakeCore(tmp, `sleep 30\nprintf '%s\\n' '${COMPILE_ENVELOPE}'`);
    const location: CoreLocation = { executable: fake, prefixArgs: [], source: 'test' };
    const registry = new CancelRegistry();

    const promise = runEnvelope(location, CompileResultSchema, 'compile', [], {
      token: 'tok',
      registry,
    });

    expect(registry.has('tok')).toBe(true);
    registry.cancel('tok');

    await expect(promise).rejects.toBeInstanceOf(CancelledError);
    expect(registry.has('tok')).toBe(false);
  });
});

describe('spawnCore (raw)', () => {
  it('runs the real command if the core is a script that echoes', async () => {
    const fake = writeFakeCore(tmp, `printf 'hello\\n'`);
    const location: CoreLocation = { executable: fake, prefixArgs: [], source: 'test' };
    const res = await spawnCore(location, []);
    expect(res.code).toBe(0);
    expect(res.stdout).toBe('hello\n');
  });
});
