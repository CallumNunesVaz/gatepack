import { expect, test, type Page } from '@playwright/test';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';

import {
  closeApp,
  launchApp,
  makeProjectDir,
  type LaunchedApp,
} from './helpers';

const DESIGN_TEXT = `gatepack: 1
kind: design
name: traffic_light
`;

let app: LaunchedApp | null = null;

async function open(page: Page, projectPath: string) {
  return page.evaluate(
    (p: string) => (window as any).gatepack.openProjectPath(p),
    projectPath,
  );
}

test.afterEach(async () => {
  if (app) {
    await closeApp(app);
    app = null;
  }
});

test('the app launches and a window appears', async () => {
  app = await launchApp();
  const title = await app.page.title();
  expect(title.length).toBeGreaterThanOrEqual(0);
  expect(app.page).toBeTruthy();
});

test('the §5.2 posture holds inside the renderer', async () => {
  app = await launchApp();
  const posture = await app.page.evaluate(() => {
    const w = window as any;
    const gate = w.gatepack;
    const proto = gate ? Object.getPrototypeOf(gate) : null;
    const leaky = ['require', 'process', 'Buffer', 'module', 'ipcRenderer', 'child_process'];
    return {
      hasRequire: typeof w.require !== 'undefined',
      hasProcess: typeof w.process !== 'undefined',
      hasGatepack: typeof gate !== 'undefined',
      leakedViaProto:
        proto !== null && leaky.some((k) => k in proto),
      leakedOnBridge: leaky.filter((k) => k in gate),
      gatepackKeys: gate ? Object.keys(gate).sort() : [],
    };
  });

  expect(posture.hasRequire).toBe(false);
  expect(posture.hasProcess).toBe(false);
  expect(posture.hasGatepack).toBe(true);
  expect(posture.leakedViaProto).toBe(false);
  expect(posture.leakedOnBridge).toEqual([]);
  // The bridge exposes exactly the documented methods, nothing else.
  expect(posture.gatepackKeys).toEqual([
    'analyse', 'build', 'cancel', 'closeProject', 'compile', 'estimate',
    'mappedNetlist', 'onFileChanged', 'onProgress', 'onProjectChanged',
    'openProject', 'openProjectPath', 'provenance', 'readSpec', 'saveProject',
    'saveProjectAs', 'verify', 'writeSpec',
  ]);
});

test('opening a project directory produces a valid ProjectInfo', async () => {
  app = await launchApp();
  const dir = makeProjectDir(DESIGN_TEXT);
  const env = await open(app.page, dir);
  expect(env.ok).toBe(true);
  expect(env.data.form).toBe('directory');
  expect(env.data.path).toBe(dir);
  expect(env.data.designPath).toBe(path.join(dir, 'design.yaml'));
  expect(env.data.dirty).toBe(false);
});

test('opening a .gpk explodes it, and saving re-bundles it', async () => {
  app = await launchApp();
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'gatepack-gpk-'));
  const gpk = path.join(dir, 'project.gpk');
  fs.writeFileSync(gpk, DESIGN_TEXT);

  const env = await open(app.page, gpk);
  expect(env.ok).toBe(true);
  expect(env.data.form).toBe('gpk');
  expect(env.data.path).toBe(gpk);
  // The exploded design.yaml lives in a temp working dir, not beside the .gpk.
  expect(env.data.designPath).not.toBe(gpk);
  expect(fs.existsSync(env.data.designPath)).toBe(true);
  expect(fs.readFileSync(env.data.designPath, 'utf8')).toBe(DESIGN_TEXT);

  // Write a new spec through the bridge, then save; the .gpk is re-bundled.
  const updated = 'gatepack: 1\nkind: design\nname: changed\n';
  await app.page.evaluate((text: string) => (window as any).gatepack.writeSpec(text), updated);
  const saved = await app.page.evaluate(() => (window as any).gatepack.saveProject());
  expect(saved.ok).toBe(true);
  expect(fs.readFileSync(gpk, 'utf8')).toBe(updated);
});

test('invoking a core command returns a well-formed envelope', async () => {
  app = await launchApp();
  const dir = makeProjectDir(DESIGN_TEXT);
  await open(app.page, dir);

  const env = await app.page.evaluate(() => (window as any).gatepack.compile('tok-1'));
  expect(env.ok).toBe(true);
  expect(env.command).toBe('compile');
  expect(env.schema).toBe(1);
  expect(env.data.flopCount).toBe(2);
});

test('a cancelled call never resolves into the renderer', async () => {
  app = await launchApp({ GATEPACK_FAKE_SLEEP_SECS: '30' });
  const dir = makeProjectDir(DESIGN_TEXT);
  await open(app.page, dir);

  const result = await app.page.evaluate(async () => {
    const gate = (window as any).gatepack;
    const p = gate.compile('slow-token');
    await gate.cancel('slow-token');
    try {
      await p;
      return { resolved: true };
    } catch (err) {
      return { resolved: false, name: (err as Error).name };
    }
  });
  expect(result.resolved).toBe(false);
});

test('path traversal outside the project root is refused', async () => {
  app = await launchApp();
  const dir = makeProjectDir(DESIGN_TEXT);
  await open(app.page, dir);

  const env = await app.page.evaluate(() =>
    (window as any).gatepack.saveProjectAs('../../outside.gpk'),
  );
  expect(env.ok).toBe(false);
  expect(env.error.code).toBe('GP4108');
});
