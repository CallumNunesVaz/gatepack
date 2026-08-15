import { describe, expect, it } from 'vitest';

import {
  parseBranch,
  parseStatusPorcelain,
  readGitStatus,
  type Exec,
} from './git.cjs';

describe('parseBranch', () => {
  it('returns the branch name', () => {
    expect(parseBranch('main\n')).toBe('main');
  });
  it('returns null for detached HEAD', () => {
    expect(parseBranch('HEAD\n')).toBeNull();
  });
  it('returns null for empty output', () => {
    expect(parseBranch('')).toBeNull();
  });
});

describe('parseStatusPorcelain', () => {
  it('strips the XY prefix and keeps paths', () => {
    const out = ' M design.yaml\n?? parts.csv\nA  new/thing.v\n';
    expect(parseStatusPorcelain(out)).toEqual(['design.yaml', 'parts.csv', 'new/thing.v']);
  });

  it('resolves a rename to its target path', () => {
    const out = 'R  old.yaml -> new.yaml\n';
    expect(parseStatusPorcelain(out)).toEqual(['new.yaml']);
  });

  it('ignores blank lines', () => {
    expect(parseStatusPorcelain('\n\n')).toEqual([]);
  });
});

describe('readGitStatus', () => {
  const fake: Exec = (args) => {
    const joined = args.join(' ');
    if (joined === 'rev-parse --show-toplevel') {
      return Promise.resolve({ code: 0, stdout: '/repo\n', stderr: '' });
    }
    if (joined === 'rev-parse --abbrev-ref HEAD') {
      return Promise.resolve({ code: 0, stdout: 'main\n', stderr: '' });
    }
    if (joined === 'status --porcelain') {
      return Promise.resolve({ code: 0, stdout: ' M design.yaml\n?? parts.csv\n', stderr: '' });
    }
    return Promise.resolve({ code: -1, stdout: '', stderr: 'unexpected' });
  };

  it('returns branch and dirty files inside a repo', async () => {
    const status = await readGitStatus('/repo/project', fake);
    expect(status).toEqual({ branch: 'main', dirtyFiles: ['design.yaml', 'parts.csv'] });
  });

  it('returns null when not in a git working tree', async () => {
    const notRepo: Exec = () => Promise.resolve({ code: 128, stdout: '', stderr: 'not a repo' });
    expect(await readGitStatus('/somewhere', notRepo)).toBeNull();
  });
});
