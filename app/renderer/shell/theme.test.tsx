/**
 * Theme state: the OS default, the explicit toggle, persistence, and the
 * `data-theme` attribute the tokens read. `matchMedia` is stubbed because jsdom
 * does not implement it — the hook must work without it (the guard in theme.ts).
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { THEME_STORAGE_KEY, useTheme } from './theme';

interface Mql {
  matches: boolean;
  addEventListener: (ev: string, cb: (e: { matches: boolean }) => void) => void;
  removeEventListener: (ev: string, cb: (e: { matches: boolean }) => void) => void;
}

function installMatchMedia(initialDark: boolean) {
  const listeners = new Set<(e: { matches: boolean }) => void>();
  const mql: Mql = {
    matches: initialDark,
    addEventListener: (_ev, cb) => listeners.add(cb),
    removeEventListener: (_ev, cb) => listeners.delete(cb),
  };
  vi.stubGlobal('matchMedia', () => mql);
  return {
    setDark(dark: boolean) {
      mql.matches = dark;
      for (const cb of listeners) cb({ matches: dark });
    },
  };
}

describe('useTheme', () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('defaults to the OS preference and sets no data-theme attribute until the user chooses', () => {
    installMatchMedia(true);
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe('dark');
    // No explicit choice -> the attribute is left unset so the CSS media query
    // (and any later OS flip) keeps governing.
    expect(document.documentElement.getAttribute('data-theme')).toBeNull();
  });

  it('toggles to light, sets data-theme, and persists the choice', () => {
    installMatchMedia(true);
    const { result } = renderHook(() => useTheme());
    act(() => result.current.toggle());
    expect(result.current.theme).toBe('light');
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('light');
  });

  it('restores an explicit stored choice on mount', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    installMatchMedia(false);
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe('dark');
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  });

  it('follows an OS change while the user has not chosen', () => {
    const mql = installMatchMedia(false);
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe('light');
    act(() => mql.setDark(true));
    expect(result.current.theme).toBe('dark');
    // Still no explicit attribute — the OS is authoritative.
    expect(document.documentElement.getAttribute('data-theme')).toBeNull();
  });
});
