/**
 * The showcase must build from a first launch with nothing else installed
 * (§18.1, §17.1). This test drives the *real* core — the frozen
 * `app/resources/bin/gatepack` binary with its bundled yosys/sby/iverilog/vvp/z3
 * — rather than the fake core the rest of the suite uses, and it strips `PATH`
 * so the build can only succeed on the bundled toolchain, never on a host copy.
 *
 * The showcase ships a single-gate library subset (§10.4), so the first-launch
 * build yields 23 packages; the full `libraries/74aup.csv` (multi-gate parts
 * now carrying verified `gates_per_pkg`) yields 20. What matters here is that
 * the app can build the showcase end-to-end from a clean session with no host
 * tools on PATH — the requirement, stated executably.
 */

import { expect, test } from '@playwright/test';
import * as fs from 'node:fs';
import * as path from 'node:path';

import { APP_DIR, closeApp, launchApp, type LaunchedApp } from './helpers';

const BUNDLED_CORE = path.join(APP_DIR, 'resources', 'bin', 'gatepack');

const bundledCorePresent = fs.existsSync(BUNDLED_CORE);

let app: LaunchedApp | null = null;

test.afterEach(async () => {
  if (app) {
    await closeApp(app);
    app = null;
  }
});

test('first launch builds the showcase with the bundled core and nothing on PATH', async () => {
  test.skip(!bundledCorePresent, 'bundled core not built; run scripts/bundle_core.py');

  // `launchApp` wires a clean session; overriding GATEPACK_CORE points it at
  // the real frozen binary, and PATH='' strips every host tool from view.
  app = await launchApp({ GATEPACK_CORE: BUNDLED_CORE, PATH: '' });

  // §18.1: a clean session opens the showcase on first launch.
  const spec = await app.page.evaluate(() => (window as any).gatepack.readSpec());
  expect(spec.ok).toBe(true);
  expect(spec.data.text).toContain('name: pelican');

  // Build it through the bridge. This runs a real synthesis + pack, so it is
  // the end-to-end proof that the bundled core and toolchain are self-contained.
  const built = await app.page.evaluate(() => (window as any).gatepack.build('showcase-build-token'));
  expect(built.ok).toBe(true);
  // The showcase's embedded single-gate library maps its 23 cells to 23
  // packages (§18.1); a 0 here would mean the build "succeeded" while
  // producing nothing, which is the exact vacuous pass this test exists to
  // catch.
  expect(built.data.packageCount).toBe(23);
  expect(built.data.bom.length).toBeGreaterThan(0);
});
