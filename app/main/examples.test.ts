import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { findExamplesRoot, parseExamplesList } from './examples.cjs';

let tmp: string;

beforeEach(() => {
  tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'gatepack-examples-'));
});

afterEach(() => {
  fs.rmSync(tmp, { recursive: true, force: true });
});

describe('findExamplesRoot', () => {
  it('returns null when no examples directory is present', () => {
    expect(findExamplesRoot(tmp, tmp)).toBeNull();
  });

  it('finds an examples root containing a design.yaml-bearing subdirectory', () => {
    const projectRoot = path.join(tmp, 'repo');
    const examples = path.join(projectRoot, 'examples');
    fs.mkdirSync(path.join(examples, 'pelican'), { recursive: true });
    fs.writeFileSync(path.join(examples, 'pelican', 'design.yaml'), 'name: pelican\n');
    expect(findExamplesRoot(tmp, projectRoot)).toBe(examples);
  });

  it('ignores a directory that contains no example subdirectories', () => {
    const projectRoot = path.join(tmp, 'repo');
    const examples = path.join(projectRoot, 'examples');
    fs.mkdirSync(examples, { recursive: true });
    fs.writeFileSync(path.join(examples, 'README.md'), 'nothing\n');
    expect(findExamplesRoot(tmp, projectRoot)).toBeNull();
  });
});

describe('parseExamplesList', () => {
  it('parses names and the showcase marker, ignoring summaries', () => {
    const output = [
      'pelican (showcase)',
      '    Pelican crossing controller',
      'sync_interlock',
      '    A synchronised interlock',
      '',
    ].join('\n');
    expect(parseExamplesList(output)).toEqual([
      { name: 'pelican', isShowcase: true },
      { name: 'sync_interlock', isShowcase: false },
    ]);
  });

  it('returns an empty list for empty output', () => {
    expect(parseExamplesList('')).toEqual([]);
  });
});
