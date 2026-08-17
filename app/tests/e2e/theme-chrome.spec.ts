/**
 * The parts of the window the design tokens do not reach on their own.
 *
 * Two of the three pieces of chrome that stayed white inside a dark
 * application are checkable from here: Electron's own `nativeTheme` (which
 * paints the Linux/Windows menu bar and any native dialog) and Monaco, which
 * ships its own light theme and does not read `tokens.css`. The third —
 * scrollbars — is pure CSS in `styles.css`.
 *
 * `nativeTheme.themeSource` defaults to `'system'`. That it is `'dark'` or
 * `'light'` here proves the renderer told main what it was showing; the OS
 * preference alone would leave it at `'system'`.
 */
import { test, expect } from '@playwright/test';
import { launchApp, closeApp, type LaunchedApp } from './helpers';

let app: LaunchedApp | null = null;

test.afterEach(async () => {
  if (app) await closeApp(app);
  app = null;
});

test("Electron's own chrome follows the theme the renderer is showing", async () => {
  app = await launchApp();
  await app.page.waitForSelector('[data-testid="spec-editor"]');

  const rendererDark = await app.page.evaluate(() => {
    const explicit = document.documentElement.getAttribute('data-theme');
    if (explicit) return explicit === 'dark';
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  });

  const native = await app.electronApp.evaluate(({ nativeTheme }) => ({
    source: nativeTheme.themeSource,
    dark: nativeTheme.shouldUseDarkColors,
  }));

  expect(native.source).toBe(rendererDark ? 'dark' : 'light');
  expect(native.dark).toBe(rendererDark);
});

test('the editor is painted from the design tokens, not Monaco\'s own theme', async () => {
  app = await launchApp();
  const { page } = app;
  await page.waitForSelector('[data-testid="spec-editor"]');
  await page.waitForSelector('.monaco-editor', { timeout: 20000 });

  const { editorBg, surface } = await page.evaluate(() => {
    const el =
      document.querySelector('.monaco-editor .monaco-editor-background') ??
      document.querySelector('.monaco-editor')!;
    return {
      editorBg: getComputedStyle(el).backgroundColor,
      surface: getComputedStyle(document.documentElement)
        .getPropertyValue('--gp-surface')
        .trim(),
    };
  });

  // Same colour as the panels around it, whichever theme is in force.
  const hex = (rgb: string) => {
    const [r, g, b] = rgb.match(/\d+/g)!.map(Number);
    return `#${[r, g, b].map((n) => n.toString(16).padStart(2, '0')).join('')}`;
  };
  expect(hex(editorBg)).toBe(surface.toLowerCase());
});
