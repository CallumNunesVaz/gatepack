/**
 * Shell end-to-end tests — the palette, the shortcut sheet and view switching
 * driven through the real Electron main process against the fake core.
 *
 * These pin the shell's keyboard contract: the palette opens with Mod+K, the
 * shortcut sheet with Mod+/, and a palette command switches the active view.
 */

import { expect, test } from '@playwright/test';
import { closeApp, launchApp, type LaunchedApp } from './helpers';

let app: LaunchedApp | null = null;

test.afterEach(async () => {
  if (app) {
    await closeApp(app);
    app = null;
  }
});

test('Mod+K opens the palette and a command switches views', async () => {
  app = await launchApp();
  const page = app.page;

  await page.waitForSelector('[data-testid="shell-rail"]');

  await page.keyboard.press('Control+k');
  const palette = page.getByTestId('command-palette');
  await expect(palette).toBeVisible();

  await page.keyboard.type('schematic');
  await page.keyboard.press('Enter');

  await expect(page.getByTestId('schematic-view')).toBeVisible();
  await expect(page.getByTestId('command-palette')).toBeHidden();
});

test('Mod+/ opens the shortcuts sheet and Escape closes it', async () => {
  app = await launchApp();
  const page = app.page;

  await page.waitForSelector('[data-testid="shell-rail"]');

  await page.keyboard.press('Control+/');
  await expect(page.getByTestId('shortcuts-sheet')).toBeVisible();

  await page.keyboard.press('Escape');
  await expect(page.getByTestId('shortcuts-sheet')).toBeHidden();
});

test('the status bar names the open project, and never says "no project" when one is open', async () => {
  // The regression this pins: the renderer learned the project by calling
  // openProject() — the native file-picker — on mount. A cancelled dialog is
  // reported as an error, so `project` stayed null and the status bar claimed
  // "no project" while the showcase was demonstrably loaded. Main re-broadcasts
  // projectChanged after page load precisely so a subscriber can catch it, and
  // nothing subscribed.
  app = await launchApp();
  // A web-first assertion, not `waitForFunction`: the renderer is served from
  // a real origin now and the CSP is genuinely enforced, so Playwright's
  // in-page polling loop (which evals) is refused. Locator assertions poll from
  // outside the page and need no `unsafe-eval`.
  // The showcase opens on first launch (§18.1) from a scratch working copy, so
  // the bar must settle on that project's path — "no project" is exactly the
  // wrong answer this pins, and a bare non-empty check would accept it.
  await expect(app.page.locator('[data-testid="status-project"]')).toHaveText(/design\.yaml/);

  const projectText = await app.page.textContent('[data-testid="status-project"]');
  expect(projectText).not.toBe('no project');
  // The showcase opens on first launch (§18.1) from a scratch working copy.
  expect(projectText).toContain('design.yaml');

  // And the design name must agree with it rather than being read separately.
  const design = await app.page.textContent('[data-testid="status-design"]');
  expect(design).toBe('pelican');
});
