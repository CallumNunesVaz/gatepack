/**
 * The four things the tool is for, reachable from the keyboard.
 *
 * `Build`, `Verify`, `Estimate`, `Compile` (and the palette-only `Analyse` /
 * `Simulate`) are advertised in the command palette and the shortcuts sheet,
 * but until M they dispatched to nothing — each reported a "is not wired yet"
 * toast. The views could run these tasks through their own buttons; the
 * *advertised route* to them was dead. This spec presses the advertised route
 * and asserts both halves: no "not wired yet" toast, and the effect actually
 * happened (the owning view became active and its task ran to a result).
 */

import { expect, test, type Page } from '@playwright/test';
import { closeApp, launchApp, type LaunchedApp } from './helpers';

let app: LaunchedApp | null = null;

test.afterEach(async () => {
  if (app) {
    await closeApp(app);
    app = null;
  }
});

/** Open the palette, filter to `query`, and run the first result. */
async function runViaPalette(page: Page, query: string): Promise<void> {
  await page.keyboard.press('Control+k');
  await page.getByTestId('command-palette').waitFor();
  await page.keyboard.type(query);
  await page.keyboard.press('Enter');
  await page.getByTestId('command-palette').waitFor({ state: 'hidden' });
}

async function assertNoNotWiredToast(page: Page): Promise<void> {
  await expect(page.locator('.gp-toast', { hasText: 'not wired yet' })).toHaveCount(0);
}

test('every run command works from its shortcut or the palette', async () => {
  app = await launchApp();
  const page = app.page;
  await page.waitForSelector('[data-testid="shell-rail"]');

  // --- run.build (Mod+B) -> packing view, build task ---
  await page.keyboard.press('Control+b');
  await expect(page.getByTestId('bom-view')).toBeVisible();
  await expect(page.getByTestId('packing-stats')).toBeVisible();
  await assertNoNotWiredToast(page);

  // --- run.verify (Mod+Shift+V) -> verification view, verify task ---
  await page.keyboard.press('Control+Shift+V');
  await expect(page.getByTestId('verification-panel')).toBeVisible();
  await expect(page.getByTestId('verification-result')).toBeVisible();
  await assertNoNotWiredToast(page);

  // --- run.estimate (Mod+E) -> analysis view, estimate task ---
  await page.keyboard.press('Control+e');
  await expect(page.getByTestId('analysis-view')).toBeVisible();
  await expect(page.getByTestId('verdict')).toBeVisible();
  await assertNoNotWiredToast(page);

  // --- run.analyse (palette) -> analysis view, analyse task ---
  await runViaPalette(page, 'analyse');
  await expect(page.getByTestId('analysis-view')).toBeVisible();
  await expect(page.getByTestId('analysis-view').getByText('Metrics')).toBeVisible();
  await assertNoNotWiredToast(page);

  // --- run.simulate (palette) -> truth table view ---
  await runViaPalette(page, 'simulate');
  await expect(page.getByTestId('truth-table')).toBeVisible();
  await assertNoNotWiredToast(page);

  // --- run.compile (Mod+Shift+C) -> a toast carrying the counts ---
  await page.keyboard.press('Control+Shift+C');
  await expect(page.locator('.gp-toast', { hasText: 'flops' })).toBeVisible();
  await assertNoNotWiredToast(page);
});

test('Escape cancels an in-flight command', async () => {
  app = await launchApp({ GATEPACK_FAKE_SLEEP_SECS: '30' });
  const page = app.page;
  await page.waitForSelector('[data-testid="shell-rail"]');

  // Start a compile; the fake core sleeps 30s, so it stays in flight long
  // enough to be cancelled. The status bar reports the bridge's own progress.
  await page.keyboard.press('Control+Shift+C');
  await expect(page.getByTestId('status-progress')).toContainText('running');

  await page.keyboard.press('Escape');

  // The cancel actually happened: the in-flight compile was cancelled, which
  // the compile handler reports. Without the token registry + run.cancel
  // handler, Escape reaches the dispatcher with no handler and reports
  // "Cancel running command is not wired yet" instead — so this assertion
  // fails (there is no "Compile cancelled" toast) without the change.
  await expect(page.locator('.gp-toast', { hasText: 'Compile cancelled' })).toBeVisible();
});
