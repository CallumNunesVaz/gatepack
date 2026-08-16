import { describe, expect, it } from 'vitest';
import {
  buildGroups,
  groupsToForceGroups,
  mixedFunctionError,
  rationaleFor,
  regroup,
  type PackingCell,
} from './packing';

const nor = (name: string): PackingCell => ({ name, func: 'NOR2' });
const nand = (name: string): PackingCell => ({ name, func: 'NAND2' });

describe('buildGroups', () => {
  it('keeps persisted force groups verbatim and makes unforced cells singletons', () => {
    const cells = [nor('g0'), nor('g1'), nor('g2')];
    const groups = buildGroups(cells, [['g1', 'g0']]);
    expect(groups.map((g) => g.cells)).toEqual([['g0', 'g1'], ['g2']]);
    expect(groups[0].forced).toBe(true);
    expect(groups[1].forced).toBe(false);
  });

  it('uses the cell type as the function identity', () => {
    const cells = [nor('g0'), nand('g1')];
    const groups = buildGroups(cells, []);
    expect(groups.map((g) => g.func).sort()).toEqual(['NAND2', 'NOR2']);
  });
});

describe('regroup', () => {
  it('moves a cell into a same-function group and persists a two-cell force group', () => {
    const groups = buildGroups([nor('g0'), nor('g1')], []);
    const { groups: next, error } = regroup(groups, 'g0', groups[1].id);
    expect(error).toBeNull();
    expect(groupsToForceGroups(next)).toEqual([['g0', 'g1']]);
  });

  it('refuses a mixed-function move with a message, leaving groups unchanged', () => {
    const groups = buildGroups([nor('g0'), nand('g1')], []);
    const target = groups.find((g) => g.func === 'NAND2') as (typeof groups)[number];
    const { groups: next, error } = regroup(groups, 'g0', target.id);
    expect(error).toContain('not the same function');
    expect(error).toContain('g0');
    expect(next).toEqual(groups);
    expect(groupsToForceGroups(next)).toEqual([]);
  });

  it('returns an error for an unknown cell or group', () => {
    const groups = buildGroups([nor('g0')], []);
    expect(regroup(groups, 'ghost', groups[0].id).error).toContain('unknown cell');
    expect(regroup(groups, 'g0', 'nope').error).toContain('unknown group');
  });

  it('does nothing when the cell is already in the target group', () => {
    const groups = buildGroups([nor('g0'), nor('g1')], [['g0', 'g1']]);
    const { groups: next, error } = regroup(groups, 'g0', groups[0].id);
    expect(error).toBeNull();
    expect(next).toEqual(groups);
  });
});

describe('groupsToForceGroups', () => {
  it('emits only groups of two or more cells, deterministically', () => {
    const groups = buildGroups([nor('g0'), nor('g1'), nand('g2')], [['g1', 'g0']]);
    expect(groupsToForceGroups(groups)).toEqual([['g0', 'g1']]);
  });
});

describe('rationaleFor', () => {
  it('distinguishes a forced group from an unpacked singleton', () => {
    const forced = buildGroups([nor('g0'), nor('g1')], [['g0', 'g1']])[0];
    const singleton = buildGroups([nor('g2')], [])[0];
    expect(rationaleFor(forced)).toContain('forced group');
    expect(rationaleFor(forced)).toContain('NOR2');
    expect(rationaleFor(singleton)).toContain('unpacked');
    expect(rationaleFor(singleton)).toContain('one NOR2');
  });
});

describe('mixedFunctionError', () => {
  it('names the cell and both functions', () => {
    const msg = mixedFunctionError('g0', 'NOR2', 'NAND2');
    expect(msg).toContain('g0');
    expect(msg).toContain('NOR2');
    expect(msg).toContain('NAND2');
    expect(msg).toContain('not the same function');
  });
});
