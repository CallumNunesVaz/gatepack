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
