/**
 * Error surfacing: a core command that fails must be shown to the user, never
 * swallowed into an empty panel.
 *
 * With the fake core wired to fail `verify` (GATEPACK_FAKE_FAIL=verify), the
 * Verification view's "Run verification" action must render the core's error —
 * code and message — in `verification-error` rather than showing an idle or
 * blank pane. Before this test existed, a failing command and an answer that
 * never arrived were visually indistinguishable.
 */

import { expect, test } from '@playwright/test';
import { closeApp, launchApp, makeProjectDir, type LaunchedApp } from './helpers';

const DESIGN_TEXT = `gatepack: 1
kind: design
name: error_surfacing
timing_model: synchronous
clock: {signal: clk, freq_hz: 1000, source: OSC}
reset: {signal: rst_n, active: low, source: SUPERVISOR}
encoding: one_hot
inputs:
  - {name: a, sync: false}
outputs:
  - {name: y}
states: [S0]
initial: S0
transitions:
  - {from: S0, to: S0, when: "1"}
output_logic:
  y: "a"
`;

let app: LaunchedApp | null = null;

test.afterEach(async () => {
  if (app) {
    await closeApp(app);
    app = null;
  }
});

test('a failing verify surfaces its error instead of an empty panel', async () => {
  app = await launchApp({ GATEPACK_FAKE_FAIL: 'verify' });
  const page = app.page;

  const dir = makeProjectDir(DESIGN_TEXT);
  await page.evaluate(
    (p: string) => (window as any).gatepack.openProjectPath(p),
    dir,
  );

  await page.click('[data-testid="nav-verify"]');
  await page.getByRole('button', { name: 'Run verification' }).click();

  const error = page.getByTestId('verification-error');
  await expect(error).toBeVisible();
  await expect(error).toContainText('yosys is not available');
});
