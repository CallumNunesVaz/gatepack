import { describe, expect, it } from 'vitest';
import { nextDir, sortBomLines } from './bomSort';
import type { BomLine } from '../../shared/api';

function line(partNumber: string, quantity: number, gatesPerPackage = 1): BomLine {
  return {
    partNumber,
    manufacturers: ['TI'],
    package: 'SOT-353',
    quantity,
    refdes: Array.from({ length: quantity }, (_, i) => `U${i + 1}`),
    tier: 'G',
    singleSourced: false,
    gatesPerPackage,
  };
}

const LINES = [line('74AUP2G00', 3, 2), line('74AUP1G02', 1, 1), line('74AUP1G00', 2, 1)];

describe('sortBomLines — C13 column ordering', () => {
  it('sorts by quantity ascending and descending', () => {
    const asc = sortBomLines(LINES, 'quantity', 'asc');
    expect(asc.map((l) => l.partNumber)).toEqual(['74AUP1G02', '74AUP1G00', '74AUP2G00']);

    const desc = sortBomLines(LINES, 'quantity', 'desc');
    expect(desc.map((l) => l.partNumber)).toEqual(['74AUP2G00', '74AUP1G00', '74AUP1G02']);
  });

  it('sorts by part number lexically', () => {
    const asc = sortBomLines(LINES, 'partNumber', 'asc');
    expect(asc.map((l) => l.partNumber)).toEqual(['74AUP1G00', '74AUP1G02', '74AUP2G00']);
  });

  it('sorts by gates-per-package numerically', () => {
    const desc = sortBomLines(LINES, 'gatesPerPackage', 'desc');
    expect(desc.map((l) => l.partNumber)).toEqual(['74AUP2G00', '74AUP1G02', '74AUP1G00']);
  });

  it('does not mutate the input array', () => {
    const before = LINES.map((l) => l.partNumber);
    sortBomLines(LINES, 'quantity', 'asc');
    expect(LINES.map((l) => l.partNumber)).toEqual(before);
  });

  it('toggles direction asc <-> desc', () => {
    expect(nextDir('asc')).toBe('desc');
    expect(nextDir('desc')).toBe('asc');
  });
});
