/**
 * The status bar reflects the *real* open project, and the design name agrees
 * with it — including when the project changes mid-session.
 *
 * The regression this guards against: the renderer read the spec once on mount
 * (`renderer/state/project.tsx`). `onProjectChanged` updated `project` (so
 * `status-project` moved), but the spec was never re-read, so `model.name` —
 * and therefore `status-design` — kept showing the previous project's name
 * after `openProjectPath`. This test opens project A, then project B in the
 * same session and asserts the design name follows.
 */

import { expect, test } from '@playwright/test';
import * as path from 'node:path';
import { closeApp, launchApp, makeProjectDir, type LaunchedApp } from './helpers';

function designText(name: string): string {
  return `gatepack: 1
kind: design
name: ${name}
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
}

let app: LaunchedApp | null = null;

test.afterEach(async () => {
  if (app) {
    await closeApp(app);
    app = null;
  }
});

test('the design name follows the project when a second project is opened mid-session', async () => {
  const dirA = makeProjectDir(designText('myproj'));
  const dirB = makeProjectDir(designText('otherproj'));
  const designPathA = path.join(dirA, 'design.yaml');
  const designPathB = path.join(dirB, 'design.yaml');

  app = await launchApp();
  const page = app.page;

  // Open project A and confirm the path and name agree.
  const openedA = await page.evaluate(
    (p: string) => (window as any).gatepack.openProjectPath(p),
    dirA,
  );
  expect(openedA.ok).toBe(true);

  await expect(page.getByTestId('status-project')).toContainText(designPathA);
  await expect(page.getByTestId('status-design')).toHaveText('myproj');

  // Open project B in the same session. `onProjectChanged` moves
  // `status-project`; the renderer must also re-read the spec so
  // `status-design` moves with it instead of going stale.
  const openedB = await page.evaluate(
    (p: string) => (window as any).gatepack.openProjectPath(p),
    dirB,
  );
  expect(openedB.ok).toBe(true);

  await expect(page.getByTestId('status-project')).toContainText(designPathB);
  await expect(page.getByTestId('status-design')).toHaveText('otherproj');
});
