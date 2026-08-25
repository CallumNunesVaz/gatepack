/**
 * Every icon must actually draw something.
 *
 * The type system already covers the obvious failure: `IconName` is a union,
 * `PATHS` is a `Record<IconName, string>` and every consumer takes an
 * `IconName`, so a misspelt icon is a compile error rather than a blank square.
 * That is *not* what this file is for, and a test asserting it would be one of
 * the checks-that-cannot-fail this project keeps finding.
 *
 * What the types do not cover is the path data itself. `Icon` renders with
 * `d={segment}` after splitting on ' M', so an empty or whitespace-only string
 * satisfies `Record<IconName, string>` perfectly and renders a `<path d="">` —
 * a correctly-named, correctly-typed, completely invisible icon. `ICON_NAMES`
 * was exported for "the icon-coverage test", and until now that test did not
 * exist.
 */

import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Icon, ICON_NAMES } from './Icon';

describe('the icon set', () => {
  it('has names to check', () => {
    // Guards the loops below: `for (const x of [])` passes every assertion in
    // it, so an empty registry would make this whole file vacuous.
    expect(ICON_NAMES.length).toBeGreaterThan(20);
  });

  it.each(ICON_NAMES)('%s draws at least one non-empty path', (name) => {
    const { container } = render(<Icon name={name} decorative />);
    const paths = Array.from(container.querySelectorAll('path'));
    expect(paths.length, `${name} rendered no <path>`).toBeGreaterThan(0);
    for (const p of paths) {
      const d = p.getAttribute('d') ?? '';
      expect(d.trim(), `${name} has an empty path`).not.toBe('');
      // A lone move-to draws nothing: it positions the pen and stops. Every
      // segment needs at least one drawing command after the M.
      expect(d, `${name} has a path that only moves the pen`).toMatch(/M[^A-Za-z]*[A-Za-z]/);
    }
  });

  it('gives a labelled icon an accessible name, and hides a decorative one', () => {
    const labelled = render(<Icon name="build" title="Build" />);
    expect(labelled.container.querySelector('svg')?.getAttribute('aria-label')).toBe('Build');
    const decorative = render(<Icon name="build" title="Build" decorative />);
    expect(decorative.container.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true');
  });
});
