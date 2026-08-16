/**
 * The doctor surface — the toolchain self-check.
 *
 * `doctor()` is the one command that must stay answerable exactly when the
 * expensive commands cannot run, because a user whose Build button fails needs
 * to see *which binary is missing and what it was for*, not a stack trace.
 *
 * This spec pins the two wired surfaces of that report:
 *
 *   1. the bridge returns a DoctorReport whose missing tools each carry a
 *      non-empty `purpose` (the field the Toolchain Status panel renders as
 *      "Missing — <purpose>");
 *   2. the status bar's toolchain indicator reflects the missing direct tools.
 *
 * Finding: the Toolchain Status panel itself (app/renderer/panels/
 * ToolchainStatusPanel.tsx) is not mounted in the shell — the `inspect.doctor`
 * palette command has no registered handler, so the panel is unreachable from
 * the UI and its purpose-text rendering is only covered by the renderer's own
 * unit tests (panels.test.tsx). Recorded in docs/BUILD-NOTES-e2e.md. Once the
 * panel is wired, the UI assertion belongs here.
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

test('doctor reports missing tools with their purpose, and the status bar reflects them', async () => {
  app = await launchApp();
  const page = app.page;

  const report = await page.evaluate(() => (window as any).gatepack.doctor());
  expect(report.ok).toBe(true);

  const tools = report.data.tools as Array<{
    name: string;
    direct: boolean;
    found: boolean;
    path: string | null;
    version: string | null;
    purpose: string;
  }>;

  // The fake core models a host without the toolchain: at least one direct
  // tool is missing, and every missing tool says what breaks without it.
  const missing = tools.filter((t) => !t.found);
  expect(missing.length, 'some tools are missing').toBeGreaterThan(0);
  for (const tool of missing) {
    expect(tool.purpose, `${tool.name} has a purpose`).not.toHaveLength(0);
    expect(tool.path, `${tool.name} path is explicit null`).toBeNull();
    expect(tool.version, `${tool.name} version is explicit null`).toBeNull();
  }

  // The status bar reads the same doctor() report and must not claim the tools
  // are ready when they are not.
  await page.waitForFunction(() => {
    const el = document.querySelector('[data-testid="status-toolchain"]');
    return el !== null && /missing/i.test(el.textContent ?? '');
  });
  const toolchain = await page.textContent('[data-testid="status-toolchain"]');
  expect(toolchain).toContain('missing');
});
