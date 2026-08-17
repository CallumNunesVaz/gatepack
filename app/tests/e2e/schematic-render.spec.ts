/**
 * The schematic view draws a real schematic.
 *
 * It did not, for two reasons that both hid behind one message ("schematic
 * unavailable — schematic worker failed"):
 *
 *  - the renderer was served from `file://`, whose opaque origin may not
 *    construct a Worker at all; and
 *  - elkjs's fake worker cannot be bundled *inside* a Worker (it detects the
 *    worker scope and installs its own `onmessage` instead of exporting), so
 *    even once the Worker loaded it threw during module evaluation.
 *
 * The layout now runs in-process. This test is the requirement stated
 * executably: open the view, get an SVG and no error.
 */
import { test, expect } from '@playwright/test';
import { launchApp, closeApp, type LaunchedApp } from './helpers';

let app: LaunchedApp | null = null;

test.afterEach(async () => {
  if (app) await closeApp(app);
  app = null;
});

test('opening the schematic renders an SVG rather than reporting a failure', async () => {
  app = await launchApp();
  const { page } = app;
  await page.waitForSelector('[data-testid="spec-editor"]');
  await page.getByRole('button', { name: 'Schematic' }).first().click();

  const svg = page.locator('[data-testid="schematic-svg"] svg');
  await expect(svg).toHaveCount(1, { timeout: 30_000 });
  await expect(page.locator('[data-testid="schematic-error"]')).toHaveCount(0);

  // Drawn in the app's ink, not the skin's hardcoded black: on the dark theme
  // the schematic rendered correctly and was invisible.
  const stroke = await svg.evaluate((el) => getComputedStyle(el).stroke);
  const text = await page.evaluate(() =>
    getComputedStyle(document.documentElement).getPropertyValue('--gp-text').trim(),
  );
  const hex = (rgb: string) => {
    const [r, g, b] = rgb.match(/\d+/g)!.map(Number);
    return `#${[r, g, b].map((n) => n.toString(16).padStart(2, '0')).join('')}`;
  };
  expect(hex(stroke)).toBe(text.toLowerCase());
});
