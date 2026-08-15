/**
 * Shared helpers for the Electron end-to-end tests. These drive the *real*
 * main process via `_electron.launch` and a hermetic fake core — a shell script
 * that implements just enough of `gatepack` to exercise the bridge without the
 * Python core (which may not have `--json` yet).
 */

import { _electron, type ElectronApplication, type Page } from '@playwright/test';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';

export const APP_DIR = path.resolve(__dirname, '..', '..', 'app');

const COMPILE_ENVELOPE = JSON.stringify({
  ok: true,
  command: 'compile',
  schema: 1,
  data: {
    verilogPath: '/tmp/build/generated.v',
    propertiesPath: null,
    flopCount: 2,
    stateCount: 3,
    encoding: 'one_hot',
    johnsonSuggestion: null,
  },
  warnings: [],
});

/**
 * A fake `gatepack` core. It implements `project explode`/`project bundle`
 * (single design document: the .gpk is the design.yaml text) and answers any
 * `compile ... --json` invocation with a canned envelope. When
 * `GATEPACK_FAKE_SLEEP_SECS` is set, `compile` sleeps first — used to test
 * cancellation of an in-flight call.
 */
const FAKE_CORE_SCRIPT = `#!/bin/sh
# hermetic fake gatepack core for e2e tests
cmd="$1"
sub="$2"

if [ "$cmd" = "project" ]; then
  if [ "$sub" = "explode" ]; then
    mkdir -p "$5"
    cp "$3" "$5/design.yaml"
    exit 0
  fi
  if [ "$sub" = "bundle" ]; then
    mkdir -p "$(dirname "$5")"
    cp "$3/design.yaml" "$5"
    exit 0
  fi
fi

if [ "$cmd" = "compile" ]; then
  if [ -n "$GATEPACK_FAKE_SLEEP_SECS" ]; then
    sleep "$GATEPACK_FAKE_SLEEP_SECS"
  fi
  printf '%s\\n' '${COMPILE_ENVELOPE}'
  exit 0
fi

printf '%s\\n' '{"ok":false,"command":"unknown","schema":1,"error":{"severity":"error","code":"GP9999","message":"unknown command"},"warnings":[]}'
exit 1
`;

let fakeCorePath: string | null = null;

export function getFakeCore(): string {
  if (fakeCorePath === null) {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'gatepack-e2e-'));
    fakeCorePath = path.join(dir, 'gatepack');
    fs.writeFileSync(fakeCorePath, FAKE_CORE_SCRIPT);
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
