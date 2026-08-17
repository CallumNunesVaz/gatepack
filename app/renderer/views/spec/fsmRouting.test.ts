import { describe, expect, it } from 'vitest';
import { nearestSides } from './FsmGraph';

const OPPOSITE: Record<string, string> = { t: 'b', b: 't', l: 'r', r: 'l' };

describe('nearestSides — pick the faces that give the shortest run', () => {
  it('leaves r and arrives l for a target directly to the right', () => {
    expect(nearestSides({ x: 0, y: 0 }, { x: 100, y: 0 })).toEqual({
      source: 'r',
      target: 'l',
    });
  });

  it('leaves l and arrives r for a target directly to the left', () => {
    expect(nearestSides({ x: 0, y: 0 }, { x: -100, y: 0 })).toEqual({
      source: 'l',
      target: 'r',
    });
  });

  it('leaves t and arrives b for a target directly above', () => {
    expect(nearestSides({ x: 0, y: 0 }, { x: 0, y: -100 })).toEqual({
      source: 't',
      target: 'b',
    });
  });

  it('leaves b and arrives t for a target directly below', () => {
    expect(nearestSides({ x: 0, y: 0 }, { x: 0, y: 100 })).toEqual({
      source: 'b',
      target: 't',
    });
  });

  it('always returns the opposite side as the target', () => {
    const targets = [
      { x: 100, y: 0 },
      { x: -100, y: 0 },
      { x: 0, y: -100 },
      { x: 0, y: 100 },
      { x: 60, y: 20 },
      { x: -60, y: -30 },
      { x: 33, y: 71 },
      { x: -5, y: 0 },
    ];
    for (const to of targets) {
      const sides = nearestSides({ x: 12, y: 34 }, to);
      expect(sides.target).toBe(OPPOSITE[sides.source]);
    }
  });

  it('resolves a diagonal to the dominant axis, measured in half-extents', () => {
    // The node box is 112×40, so a horizontal offset is measured in 56px
    // half-widths and a vertical offset in 20px half-heights. 60px right is
    // ~1.07 half-widths; 20px down is exactly one half-height — the right face
    // wins.
    expect(nearestSides({ x: 0, y: 0 }, { x: 60, y: 20 })).toEqual({
      source: 'r',
      target: 'l',
    });
    // 30px down is 1.5 half-heights, more than 60px right's ~1.07 half-widths,
    // so the bottom face wins: a wide-but-short node does not shed an edge off
    // its long (left/right) face just because dx is numerically larger.
    expect(nearestSides({ x: 0, y: 0 }, { x: 60, y: 30 })).toEqual({
      source: 'b',
      target: 't',
    });
  });
});
