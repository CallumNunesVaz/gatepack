/**
 * Shared helpers for the Electron end-to-end tests. These drive the *real*
 * main process via `_electron.launch` and a hermetic fake core — a standalone
 * Node script (`fake-core.cjs`) that answers every command the bridge can
 * dispatch with a schema-valid envelope, without the Python core or the
 * toolchain.
 *
 * The fake core lives in a real file (readable, cross-checkable against
 * gatepack/api.py) and is copied into a per-run temp directory here so it is
 * always executable regardless of the repo checkout's file mode.
 */

import { _electron, type ElectronApplication, type Page } from '@playwright/test';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';

// `__dirname` is unavailable here: app/package.json is `"type": "module"`, so
// Playwright loads these specs as ESM. Derive the directory from the module
// URL instead of assuming a CommonJS wrapper.
const HERE = path.dirname(fileURLToPath(import.meta.url));
export const APP_DIR = path.resolve(HERE, '..', '..');

const FAKE_CORE_SOURCE = path.join(HERE, 'fake-core.cjs');

let fakeCorePath: string | null = null;

export function getFakeCore(): string {
  if (fakeCorePath === null) {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'gatepack-e2e-'));
    fakeCorePath = path.join(dir, 'gatepack');
    fs.copyFileSync(FAKE_CORE_SOURCE, fakeCorePath);
    fs.chmodSync(fakeCorePath, 0o755);
  }
  return fakeCorePath;
}

export interface LaunchedApp {
  electronApp: ElectronApplication;
  page: Page;
}

/** Launch the real main process, wiring the fake core via GATEPACK_CORE. */
export async function launchApp(
  extraEnv: Record<string, string> = {},
): Promise<LaunchedApp> {
  const electronApp = await _electron.launch({
    args: [APP_DIR],
    env: {
      ...process.env,
      GATEPACK_CORE: getFakeCore(),
      // Hermetic per-launch session: no prior session, so the showcase opens on
      // first launch (§18.1) and tests never leak a last-opened project.
      GATEPACK_SESSION_DIR: fs.mkdtempSync(path.join(os.tmpdir(), 'gatepack-session-')),
      ...extraEnv,
    },
  });
  const page = await electronApp.firstWindow();
  await page.waitForFunction(() => typeof (window as unknown as { gatepack?: unknown }).gatepack !== 'undefined');
  return { electronApp, page };
}

export async function closeApp(launched: LaunchedApp): Promise<void> {
  await launched.electronApp.close();
}

export function makeProjectDir(designText: string): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'gatepack-proj-'));
  fs.writeFileSync(path.join(dir, 'design.yaml'), designText);
  return dir;
}
