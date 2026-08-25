/**
 * The pipeline strip, against the real core.
 *
 * The unit tests drive `FakeGatepack`, so they pin the wiring but say nothing
 * about whether a real unbuilt project actually reaches the states the strip
 * claims. This runs the toolchain: open an example with no build, read the
 * strip, run a real build, read it again.
 *
 * The point of the last assertion is the one that cost the most to establish:
 * `verify` writes nothing to disk, so a *built* project must still show Verify
 * as not-done. If that ever flips to `done` off the back of `mapped.json`, the
 * strip is claiming evidence that does not exist.
 */

import { _electron, expect, test, type Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const APP_DIR = path.resolve(HERE, '..', '..');
const REPO_ROOT = path.resolve(APP_DIR, '..');
const IMAGE = 'gatepack-toolchain:m6';

function toolchainAvailable(): boolean {
  try {
    execFileSync('docker', ['image', 'inspect', IMAGE], { stdio: 'ignore' });
    return true;
  } catch {
    return false;
  }
}

function makeCore(): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'gatepack-tccore-'));
  const p = path.join(dir, 'gatepack');
  fs.writeFileSync(
    p,
    [
      '#!/bin/sh',
      'exec docker run --rm \\',
      `  --user "${process.getuid!()}:${process.getgid!()}" \\`,
      '  -v /tmp:/tmp \\',
      `  -v "${REPO_ROOT}:${REPO_ROOT}" \\`,
      `  -e PYTHONPATH="${REPO_ROOT}" -e HOME=/tmp -w "$PWD" \\`,
      `  ${IMAGE} python3 -m gatepack.cli "$@"`,
      '',
    ].join('\n'),
  );
  fs.chmodSync(p, 0o755);
  return p;
}

const stageState = (page: Page, id: string) =>
  page.locator(`[data-testid="pipeline-stage-${id}"]`).getAttribute('data-state');

test.describe('the pipeline strip', () => {
  test.skip(!toolchainAvailable(), `toolchain image ${IMAGE} not available`);
  test.describe.configure({ timeout: 180_000 });

  test('an unbuilt project shows Build ready; a build makes it done, Verify stays not-done', async () => {
    // A copy with no `.gatepack/`, so "unbuilt" is a fact rather than a hope.
    const work = fs.mkdtempSync(path.join(os.tmpdir(), 'gatepack-strip-'));
    fs.cpSync(path.join(REPO_ROOT, 'examples', 'seven_segment'), work, { recursive: true });
    fs.rmSync(path.join(work, '.gatepack'), { recursive: true, force: true });
    fs.rmSync(path.join(work, 'build'), { recursive: true, force: true });

    const app = await _electron.launch({
      args: [APP_DIR],
      env: {
        ...process.env,
        GATEPACK_CORE: makeCore(),
        GATEPACK_SESSION_DIR: fs.mkdtempSync(path.join(os.tmpdir(), 'gatepack-session-')),
      },
    });
    try {
      const page = await app.firstWindow();
      await page.waitForFunction(() => typeof (window as any).gatepack !== 'undefined');
      const opened = await page.evaluate(
        (p) => (window as any).gatepack.openProjectPath(p),
        work,
      );
      expect(opened.ok, opened.ok ? '' : opened.error?.message).toBe(true);

      await expect(page.getByTestId('pipeline-strip')).toBeVisible();
      await expect
        .poll(() => stageState(page, 'build'), { timeout: 20_000 })
        .toBe('ready');
      expect(await stageState(page, 'spec'), 'a compiling spec is done').toBe('done');
      expect(await stageState(page, 'verify'), 'verify needs no build, so it is ready').toBe(
        'ready',
      );

      // The connector into the actionable stage is the only one animating.
      expect(
        await page.locator('[data-testid="connector-spec-build"]').getAttribute('data-active'),
      ).toBe('true');
      expect(
        await page.locator('[data-testid="connector-build-views"]').getAttribute('data-active'),
      ).toBeNull();

      // Run the build the way a user does: click the strip's own Build node.
      // Driving `api.build()` directly instead leaves the strip stale, and that
      // is worth stating rather than working around — the strip learns a build
      // finished from the reload signal the views fire, so a build run outside
      // the application (the CLI, another window) does not reach it. It then
      // under-reports, showing `ready` for a project that has a netlist, which
      // is the safe direction to be wrong in but is still a limitation.
      await page.getByTestId('pipeline-stage-build').click();
      await expect.poll(() => stageState(page, 'build'), { timeout: 120_000 }).toBe('done');

      // `done` must mean a netlist exists on disk, not merely that a state
      // machine advanced. A strip that goes green without an artefact behind it
      // is the exact defect this whole feature was built to remove.
      expect(
        fs.existsSync(path.join(work, '.gatepack', 'out', 'mapped.json')),
        'the strip says done, so mapped.json must exist',
      ).toBe(true);

      // The assertion this whole design turns on.
      expect(
        await stageState(page, 'verify'),
        'verify writes nothing to disk, so a build cannot evidence it',
      ).not.toBe('done');
    } finally {
      await app.close();
    }
  });
});
