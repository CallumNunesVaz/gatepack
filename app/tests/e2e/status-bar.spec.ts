/**
 * The status bar reflects the *real* open project, and the design name agrees
 * with it.
 *
 * The regression this guards against: the renderer used to learn the project by
 * calling `openProject()` (the native file picker) on mount; a cancelled dialog
 * reports as an error, so the project stayed null and the status bar said "no
 * project" while a project was demonstrably open. shell.spec.ts pins the
 * showcase case (first-launch pelican); this test pins the general case — a
 * user project reopened from the stored session — and that the design name in
 * the status bar is parsed from that same project's spec rather than a separate
 * source that could disagree.
 *
 * Finding: `status-design` is derived from the spec text read once on mount
 * (renderer/state/project.tsx). Calling `openProjectPath` mid-session updates
 * `status-project` (via onProjectChanged) but never re-reads the spec, so the
 * design name goes stale against the newly opened project. That renderer bug is
 * out of scope here (app/renderer is read-only for this package) and recorded
 * in docs/BUILD-NOTES-e2e.md; the reopen-on-launch flow below is the path that
 * works and is what this test pins.
 */

import { expect, test } from '@playwright/test';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { closeApp, launchApp, makeProjectDir, type LaunchedApp } from './helpers';

const DESIGN_TEXT = `gatepack: 1
kind: design
name: myproj
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

test('the status bar shows the opened project path and an agreeing design name', async () => {
  const sessionDir = fs.mkdtempSync(path.join(os.tmpdir(), 'gatepack-session-'));
  const dir = makeProjectDir(DESIGN_TEXT);
  const designPath = path.join(dir, 'design.yaml');

  // First launch: open the project, which records it as the last-opened one.
  app = await launchApp({ GATEPACK_SESSION_DIR: sessionDir });
  const opened = await app.page.evaluate(
    (p: string) => (window as any).gatepack.openProjectPath(p),
    dir,
  );
  expect(opened.ok).toBe(true);
  await closeApp(app);
  app = null;

  // Second launch with the same session must reopen that project (not the
  // showcase), and the status bar must reflect it.
  app = await launchApp({ GATEPACK_SESSION_DIR: sessionDir });
  const page = app.page;

  // The status bar must show this project's design.yaml, not "no project".
  // expect(...).toContainText retries, and — unlike waitForFunction with an
  // argument — never string-evaluates, so it survives the strict CSP.
  await expect(page.getByTestId('status-project')).toContainText(designPath);

  // And the design name must agree with the project: parsed from the spec just
  // opened, not from a hardcoded or separate source.
  await expect(page.getByTestId('status-design')).toHaveText('myproj');
});
