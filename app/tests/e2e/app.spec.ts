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
    'analyse', 'build',
    // `buildState` (2026-08-25): the pipeline strip and the gated views ask
    // which step is still owed (§GUI-5). Widening the bridge is a §5.2
    // decision, so it is declared here rather than allowed to pass by a looser
    // assertion. It is strictly narrowing in capability terms: it takes no
    // argument, names no path, and returns the `readdir` of the main process's
    // own `<project>/.gatepack/out` — a directory the renderer could already
    // learn the contents of by calling `mappedNetlist`/`analyse` and reading
    // the failure messages. It reads; it never writes and never opens anything.
    'buildState',
    'cancel', 'checkLibrary', 'closeProject', 'compile',
    'currentProject', 'doctor', 'estimate',
    // `exportOutputs`/`revealOutputs` (2026-08-25): File > Reveal/Export build
    // outputs (§GUI-1). Widening the bridge is a §5.2 decision, so it is
    // declared here rather than allowed to pass by a looser assertion. The
    // renderer names no path: `revealOutputs` opens the main process's own
    // `<project>/.gatepack/out`, and `exportOutputs`'s destination is chosen
    // by a native dialog in the main process — so no new capability reaches
    // the renderer beyond what `openProjectPath` already allowed.
    'exportOutputs',
    'listExamples', 'mappedNetlist',
    // `newProject`/`newProjectDialog` (2026-08-24): File > New Project. Widening
    // the bridge is a §5.2 decision, so it is declared here rather than allowed
    // to pass by a looser assertion. Both go straight to the main process --
    // `newProject` shells out to `gatepack project new`, `newProjectDialog`
    // opens the directory chooser -- so no new capability reaches the renderer
    // beyond naming a directory, which `openProjectPath` already allowed.
    'newProject', 'newProjectDialog',
    'onFileChanged', 'onProgress', 'onProjectChanged', 'openExample',
    'openProject', 'openProjectPath', 'packedNetlist', 'provenance', 'readSpec',
    'revealOutputs',
    'saveProject', 'saveProjectAs', 'setNativeTheme', 'simulate', 'verify',
    'writeSpec',
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

test('first launch with a clean session opens the showcase', async () => {
  // launchApp() gives every test a clean session dir, so the first launch opens
  // the bundled showcase (§18.1). The renderer's one-shot readSpec() — what it
  // calls on mount — must see the real project, not an empty editor.
  app = await launchApp();

  const spec = await app.page.evaluate(() => (window as any).gatepack.readSpec());
  expect(spec.ok).toBe(true);
  expect(spec.data.text).toContain('name: pelican');
  // Comments are half of what the showcase teaches; they must survive the copy.
  expect(spec.data.text).toContain('Pelican crossing controller');
  // The spec is served from a scratch working copy, never the bundled copy.
  expect(spec.data.path).toContain('gatepack-example-');
  expect(spec.data.path).not.toContain(path.join('examples', 'pelican'));

  // §18.1(4): the showcase is read-only-ish — Save prompts for Save As.
  const saved = await app.page.evaluate(() => (window as any).gatepack.saveProject());
  expect(saved.ok).toBe(false);
  expect(saved.error.code).toBe('GP4109');
});

test('a previously opened project is reopened on the next launch', async () => {
  const sessionDir = fs.mkdtempSync(path.join(os.tmpdir(), 'gatepack-session-'));
  const projectDir = makeProjectDir('name: myproj\n');

  // First launch: open a project, which records it as the last-opened project.
  app = await launchApp({ GATEPACK_SESSION_DIR: sessionDir });
  const opened = await open(app.page, projectDir);
  expect(opened.ok).toBe(true);
  await closeApp(app);
  app = null;

  // Second launch with the same session dir must reopen that project, not the
  // showcase.
  app = await launchApp({ GATEPACK_SESSION_DIR: sessionDir });
  const spec = await app.page.evaluate(() => (window as any).gatepack.readSpec());
  expect(spec.ok).toBe(true);
  expect(spec.data.text).toContain('name: myproj');
});
