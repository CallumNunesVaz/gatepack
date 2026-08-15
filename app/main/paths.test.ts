import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { isInside, PathScopeError, realpathExisting, resolveWithin } from './paths.cjs';

let tmp: string;

beforeEach(() => {
  tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'gatepack-paths-'));
});

afterEach(() => {
  fs.rmSync(tmp, { recursive: true, force: true });
});

describe('isInside', () => {
  it('accepts the root itself', () => {
    expect(isInside('/a/b', '/a/b')).toBe(true);
  });
  it('accepts a descendant', () => {
    expect(isInside('/a/b', '/a/b/c/d')).toBe(true);
  });
  it('rejects a sibling with a shared prefix', () => {
    expect(isInside('/a/b', '/a/bc')).toBe(false);
  });
  it('rejects a parent', () => {
    expect(isInside('/a/b', '/a')).toBe(false);
  });
});

describe('resolveWithin', () => {
  it('returns the resolved absolute path for an in-scope file', () => {
    const got = resolveWithin(tmp, 'design.yaml');
    expect(got).toBe(path.join(tmp, 'design.yaml'));
  });

  it('refuses a `../../etc/passwd`-style traversal', () => {
    expect(() => resolveWithin(tmp, '../../etc/passwd')).toThrow(PathScopeError);
  });

  it('refuses an absolute path outside the root', () => {
    expect(() => resolveWithin(tmp, '/etc/passwd')).toThrow(PathScopeError);
  });

  it('resolves a not-yet-existing file inside the root', () => {
    const got = resolveWithin(tmp, path.join('nested', 'new.yaml'));
    expect(got).toBe(path.join(tmp, 'nested', 'new.yaml'));
  });

  it('refuses a symlink that escapes the root', () => {
    const outside = fs.mkdtempSync(path.join(os.tmpdir(), 'gatepack-outside-'));
    try {
      fs.writeFileSync(path.join(outside, 'secret.txt'), 'secret');
      fs.symlinkSync(outside, path.join(tmp, 'escape'));
      expect(() => resolveWithin(tmp, path.join('escape', 'secret.txt'))).toThrow(PathScopeError);
    } finally {
      fs.rmSync(outside, { recursive: true, force: true });
    }
  });
});

describe('realpathExisting', () => {
  it('resolves an existing path', () => {
    fs.writeFileSync(path.join(tmp, 'a.txt'), 'x');
    expect(realpathExisting(path.join(tmp, 'a.txt'))).toBe(fs.realpathSync(path.join(tmp, 'a.txt')));
  });

  it('resolves the ancestor of a missing path', () => {
    const got = realpathExisting(path.join(tmp, 'no', 'such', 'file'));
    expect(got).toBe(path.join(fs.realpathSync(tmp), 'no', 'such', 'file'));
  });
});
