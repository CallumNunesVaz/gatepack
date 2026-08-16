/**
 * Theme state for the whole application.
 *
 * One source of truth: the `app.theme` key in localStorage holds the user's
 * explicit choice (`'light'` | `'dark'`); when it is absent, the OS preference
 * decides and the renderer does **not** set `data-theme` at all, so the
 * `prefers-color-scheme` rules in `tokens.css` stay live (a mid-session OS
 * flip is honoured). An explicit choice pins the attribute and persists.
 */

import { useCallback, useEffect, useState } from 'react';

export type Theme = 'light' | 'dark';

export const THEME_STORAGE_KEY = 'app.theme';

function prefersDark(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return false;
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

function readStoredTheme(): Theme | null {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === 'light' || stored === 'dark') return stored;
  } catch {
    // localStorage can throw in private/blocked contexts; treat as "not chosen".
  }
  return null;
}

export function useTheme(): { theme: Theme; toggle: () => void } {
  const [theme, setTheme] = useState<Theme>(() => readStoredTheme() ?? (prefersDark() ? 'dark' : 'light'));

  // Reflect the effective theme onto <html> as `data-theme`, which is what the
  // tokens read. No explicit choice -> no attribute -> CSS media query governs.
  useEffect(() => {
    const stored = readStoredTheme();
    if (stored === 'light' || stored === 'dark') {
      document.documentElement.setAttribute('data-theme', stored);
    } else {
      document.documentElement.removeAttribute('data-theme');
    }
  }, [theme]);

  // While the user has not chosen, follow OS changes live so `theme` (used for
  // the toggle icon/label) never lies about what the CSS is actually showing.
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return;
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => {
      if (readStoredTheme() !== null) return;
      setTheme(mq.matches ? 'dark' : 'light');
    };
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);

  const toggle = useCallback(() => {
    setTheme((prev) => {
      const next: Theme = prev === 'dark' ? 'light' : 'dark';
      try {
        window.localStorage.setItem(THEME_STORAGE_KEY, next);
      } catch {
        // Persisting failed; the in-memory choice still applies this session.
      }
      return next;
    });
  }, []);

  return { theme, toggle };
}
