/**
 * `applyHitTargets` — the invisible click targets that make a 1 px wire
 * clickable. Pure DOM, so it runs under jsdom; the *measured* tolerance lives
 * in `app/tests/e2e/schematic-pointer.spec.ts`, which needs a real layout.
 */

import { describe, expect, it } from 'vitest';
import { applyHitTargets, clearHitTargets, HIT_HALF_WIDTH } from './schematicDecorate';

function sheet(): HTMLDivElement {
  const root = document.createElement('div');
  root.innerHTML = `
    <svg>
      <g>
        <line id="w1" class="net_4" x1="0" y1="0" x2="10" y2="0"></line>
        <path id="w2" class="net_7" d="M0 5 L10 5"></path>
        <g id="cell_u1"><rect x="0" y="0" width="4" height="4"></rect></g>
      </g>
    </svg>`;
  return root;
}

describe('applyHitTargets', () => {
  it('gives every wire a wide, transparent, stroke-hit-tested copy', () => {
    const root = sheet();
    expect(applyHitTargets(root)).toBe(2);

    const hits = Array.from(root.querySelectorAll('.gp-hit'));
    expect(hits).toHaveLength(2);
    for (const hit of hits) {
      expect(hit.getAttribute('stroke')).toBe('transparent');
      expect(Number(hit.getAttribute('stroke-width'))).toBe(HIT_HALF_WIDTH * 2);
      // `stroke`, not `visibleStroke`: the stroke area must be hit-tested even
      // though nothing is painted into it.
      expect(hit.getAttribute('pointer-events')).toBe('stroke');
    }
  });

  it('carries the net class through, so the click handlers need no change', () => {
    const root = sheet();
    applyHitTargets(root);
    const classes = Array.from(root.querySelectorAll('.gp-hit')).map((e) => e.getAttribute('class'));
    expect(classes).toContain('net_4 gp-hit');
    expect(classes).toContain('net_7 gp-hit');
  });

  it('never duplicates an id', () => {
    // A clone inherits `id`, and two elements sharing one breaks both
    // `getElementById` and the §15.2 spine's `cell_<instance>` lookups.
    const root = sheet();
    applyHitTargets(root);
    for (const hit of Array.from(root.querySelectorAll('.gp-hit'))) {
      expect(hit.hasAttribute('id')).toBe(false);
    }
    expect(root.querySelectorAll('#w1')).toHaveLength(1);
    expect(root.querySelectorAll('#w2')).toHaveLength(1);
  });

  it('leaves cells alone — their whole body is made clickable by CSS instead', () => {
    const root = sheet();
    applyHitTargets(root);
    expect(root.querySelector('#cell_u1')!.querySelectorAll('.gp-hit')).toHaveLength(0);
  });

  it('is idempotent: re-running never stacks targets on targets', () => {
    // It re-runs on every layout, and a copy of a copy would double the DOM
    // each time while looking identical.
    const root = sheet();
    applyHitTargets(root);
    applyHitTargets(root);
    applyHitTargets(root);
    expect(root.querySelectorAll('.gp-hit')).toHaveLength(2);
    expect(root.querySelectorAll('.gp-hit-layer')).toHaveLength(1);
  });

  it('the targets sit above the sheet, or they would be shadowed by it', () => {
    const root = sheet();
    applyHitTargets(root);
    const svg = root.querySelector('svg')!;
    expect(svg.lastElementChild!.getAttribute('class')).toBe('gp-hit-layer');
  });

  it('clears completely', () => {
    const root = sheet();
    applyHitTargets(root);
    clearHitTargets(root);
    expect(root.querySelectorAll('.gp-hit')).toHaveLength(0);
    expect(root.querySelectorAll('.gp-hit-layer')).toHaveLength(0);
    expect(root.querySelectorAll('line,path')).toHaveLength(2);
  });
});
