/**
 * The exit-code/envelope contract, end to end.
 *
 * The real core answers `verify` with a schema-valid `ok: true` envelope and
 * *still exits non-zero* when not every check ran or passed (e.g. a machine
 * without yosys). The envelope is the answer; the exit code is the shell's
 * all-green signal. The main process must let that envelope reach the renderer
 * intact, so the Verification panel shows the check list with its `not run`
 * states and skip reasons — never a bare "core exited 1".
 *
 * The fake core is told to model exactly this via `GATEPACK_FAKE_NONZERO_OK`,
 * which emits `verifyNotRunData()` (missing toolchain -> `not_run` checks with
 * `skippedReason`) and exits 1, mirroring the real core's output byte-for-byte
 * in shape.
 */

import { expect, test } from '@playwright/test';
import { closeApp, launchApp, makeProjectDir, type LaunchedApp } from './helpers';

const DESIGN_TEXT = `gatepack: 1
kind: design
name: verify_missing_tools
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

test('a verify that exits non-zero with ok:true renders the check list, not "core exited 1"', async () => {
  app = await launchApp({ GATEPACK_FAKE_NONZERO_OK: 'verify' });
  const page = app.page;

  const dir = makeProjectDir(DESIGN_TEXT);
  await page.evaluate(
    (p: string) => (window as any).gatepack.openProjectPath(p),
    dir,
  );

  await page.click('[data-testid="nav-verify"]');
  await page.getByRole('button', { name: 'Run verification' }).click();

  // The result panel is what renders the envelope's check list.
  const result = page.getByTestId('verification-result');
  await expect(result).toBeVisible();
  await expect(result).toContainText('Not all checks passed');

  // No error surface: the envelope was not discarded as a "lying core".
  await expect(page.getByTestId('verification-error')).toHaveCount(0);

  // The checks that could not run are shown, with their skip reasons, not a
  // bare exit-code string.
  const checkList = page.locator('.check-list');
  await expect(checkList.getByTestId('status-badge').first()).toHaveAttribute(
    'data-status',
    'not_run',
  );
  await expect(page.locator('.check-row[data-check="equivalence"]')).toContainText('not run');
  await expect(checkList.getByTestId('status-badge').first()).toHaveAttribute(
    'title',
    /yosys/,
  );
});
