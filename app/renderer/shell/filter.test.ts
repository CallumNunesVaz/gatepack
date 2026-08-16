/**
 * Palette filter: the ranking that decides what the palette shows, tested in
 * isolation so a change to the matching rules is a deliberate, visible thing.
 */

import { describe, expect, it } from 'vitest';
import { COMMANDS } from '../keys/registry';
import { filterCommands } from './filter';

describe('filterCommands', () => {
  it('returns every command for an empty query', () => {
    expect(filterCommands('', COMMANDS)).toHaveLength(COMMANDS.length);
  });

  it('ranks a title match first for the query "build"', () => {
    const results = filterCommands('build', COMMANDS);
    expect(results.length).toBeGreaterThan(0);
    expect(results[0].id).toBe('run.build');
    // The query filtered something out — the result is a real reduction, not
    // the whole registry reordered.
    expect(results.length).toBeLessThan(COMMANDS.length);
    expect(results.some((c) => c.id === 'project.open')).toBe(false);
  });

  it('matches fields other than the title (cli tag / hint)', () => {
    const byCli = filterCommands('doctor', COMMANDS);
    expect(byCli.length).toBeGreaterThan(0);
    expect(byCli[0].id).toBe('inspect.doctor');
  });

  it('narrows an exact title to a single result', () => {
    const results = filterCommands('schematic', COMMANDS);
    expect(results.map((c) => c.id)).toEqual(['view.schematic']);
  });

  it('returns an empty list for a query that matches nothing', () => {
    expect(filterCommands('zzzzqqqq', COMMANDS)).toEqual([]);
  });
});
