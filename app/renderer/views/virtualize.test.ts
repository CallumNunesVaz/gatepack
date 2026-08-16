import { describe, expect, it } from 'vitest';
import { computeRowWindow } from './virtualize';

describe('computeRowWindow — truth-table windowing', () => {
  it('returns the whole table when the viewport cannot be measured', () => {
    const w = computeRowWindow({
      scrollTop: 0,
      viewportHeight: 0,
      rowHeight: 28,
      totalRows: 4096,
    });
    expect(w.start).toBe(0);
    expect(w.end).toBe(4096);
    expect(w.topOffset).toBe(0);
    expect(w.bottomOffset).toBe(0);
  });

  it('windows a large table with overscan and correct offsets', () => {
    const w = computeRowWindow({
      scrollTop: 1400, // row 50 is first visible
      viewportHeight: 560, // 20 rows visible
      rowHeight: 28,
      totalRows: 1000,
      overscan: 5,
    });
    expect(w.start).toBe(45);
    // firstVisible(50) + visibleCount(20) + overscan(5) = 75
    expect(w.end).toBe(75);
    expect(w.topOffset).toBe(45 * 28);
    expect(w.bottomOffset).toBe((1000 - 75) * 28);
  });

  it('clamps the window at both ends of the table', () => {
    const top = computeRowWindow({ scrollTop: 0, viewportHeight: 560, rowHeight: 28, totalRows: 1000 });
    expect(top.start).toBe(0);
    expect(top.end).toBe(25); // 0 + 20 + 5

    const bottom = computeRowWindow({ scrollTop: 28 * 999, viewportHeight: 560, rowHeight: 28, totalRows: 1000 });
    expect(bottom.end).toBe(1000);
    expect(bottom.start).toBeLessThan(bottom.end);
  });

  it('never produces an empty or inverted window for a non-empty table', () => {
    for (const scrollTop of [0, 100, 9999]) {
      const w = computeRowWindow({ scrollTop, viewportHeight: 560, rowHeight: 28, totalRows: 1000 });
      expect(w.end).toBeGreaterThan(w.start);
    }
  });

  it('returns an empty window for an empty table', () => {
    const w = computeRowWindow({ scrollTop: 0, viewportHeight: 560, rowHeight: 28, totalRows: 0 });
    expect(w.start).toBe(0);
    expect(w.end).toBe(0);
  });
});
