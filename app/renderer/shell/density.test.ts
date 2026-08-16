/**
 * Density bands, matched to the media-query breakpoints in tokens.css so the
 * shell's `data-density` attribute and the token shrinking can never disagree.
 */

import { describe, expect, it } from 'vitest';
import { densityForWidth } from './density';

describe('densityForWidth', () => {
  it('maps widths to the three bands', () => {
    expect(densityForWidth(1920)).toBe('spacious');
    expect(densityForWidth(1501)).toBe('spacious');
    expect(densityForWidth(1500)).toBe('cozy');
    expect(densityForWidth(1400)).toBe('cozy');
    expect(densityForWidth(1201)).toBe('cozy');
    expect(densityForWidth(1200)).toBe('compact');
    expect(densityForWidth(900)).toBe('compact');
  });
});
