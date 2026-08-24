/**
 * "Can a user get from an example to a manufacturable output using only the
 * GUI?" — driven for EVERY bundled example, through the real Electron main
 * process, against a real Python core with the real toolchain.
 *
 * Why this exists
 * ---------------
 * Every other e2e spec here either uses the hermetic fake core (contract shape,
 * not behaviour) or drives one design (gui-audit). Neither answers the question
 * a user actually has: *if I open this example and click through, do I get a
 * netlist and a BOM out the other end?* A per-example sweep is the only thing
 * that does, because the examples differ in exactly the ways that break a
 * pipeline — asynchronous vs synchronous, flops vs pure combinational, one
 * package vs many.
 *
 * The toolchain seam
 * ------------------
 * yosys/iverilog/sby are not installed on a typical dev host, but they are in
 * `gatepack-toolchain:m6`. Rather than skip (a skipped end-to-end test is
 * indistinguishable from one that does not exist — docs/TESTING.md), the core
 * is wired through a shim that runs `gatepack.cli` inside that image. `/tmp`
 * and the repo are bind-mounted at their *host* paths, so every absolute path
 * the main process passes resolves identically inside the container. Electron
 * still runs on the host and the main process is unmodified: the only
 * substitution is GATEPACK_CORE, which is the documented seam.
 *
 * What a failure here means
 * -------------------------
 * A failure is a claim about the product, not about the harness: it says a user
 * who opens this example in the GUI cannot complete this step without leaving
 * the GUI.
 */

import { _electron, expect, test, type ElectronApplication, type Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const APP_DIR = path.resolve(HERE, '..', '..');
const REPO_ROOT = path.resolve(APP_DIR, '..');
const TOOLCHAIN_IMAGE = 'gatepack-toolchain:m6';

/** True when docker can run the toolchain image on this host. */
function toolchainAvailable(): boolean {
  try {
    execFileSync('docker', ['image', 'inspect', TOOLCHAIN_IMAGE], { stdio: 'ignore' });
    return true;
  } catch {
    return false;
  }
}

let corePath: string | null = null;

/** A GATEPACK_CORE shim that runs the real core inside the toolchain image. */
function makeToolchainCore(): string {
  if (corePath !== null) return corePath;
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'gatepack-tccore-'));
  corePath = path.join(dir, 'gatepack');
  const uid = process.getuid?.() ?? 0;
  const gid = process.getgid?.() ?? 0;
  fs.writeFileSync(
    corePath,
    [
      '#!/bin/sh',
      'exec docker run --rm \\',
      `  --user "${uid}:${gid}" \\`,
      '  -v /tmp:/tmp \\',
      `  -v "${REPO_ROOT}:${REPO_ROOT}" \\`,
      `  -e PYTHONPATH="${REPO_ROOT}" \\`,
      // The container user has no passwd entry, so HOME is unset and anything
      // that expands `~` (matplotlib, fontconfig) would fail on a read-only /.
      '  -e HOME=/tmp \\',
      '  -w "$PWD" \\',
      `  ${TOOLCHAIN_IMAGE} \\`,
      '  python3 -m gatepack.cli "$@"',
      '',
    ].join('\n'),
  );
  fs.chmodSync(corePath, 0o755);
  return corePath;
}

interface Launched {
  app: ElectronApplication;
  page: Page;
}

async function launch(): Promise<Launched> {
  const app = await _electron.launch({
    args: [APP_DIR],
    env: {
      ...process.env,
      GATEPACK_CORE: makeToolchainCore(),
      GATEPACK_SESSION_DIR: fs.mkdtempSync(path.join(os.tmpdir(), 'gatepack-session-')),
    },
  });
  const page = await app.firstWindow();
  await page.waitForFunction(() => typeof (window as any).gatepack !== 'undefined');
  return { app, page };
}

type Env<T = any> = { ok: true; data: T } | { ok: false; error: { code: string; message: string } };

const call = <T>(page: Page, fn: string): Promise<Env<T>> =>
  page.evaluate((name) => (window as any).gatepack[name](), fn);

/** Every bundled example, so the sweep covers the shipped surface. */
const EXAMPLES = fs
  .readdirSync(path.join(REPO_ROOT, 'examples'), { withFileTypes: true })
  .filter((e) => e.isDirectory() && fs.existsSync(path.join(REPO_ROOT, 'examples', e.name, 'design.yaml')))
  .map((e) => e.name)
  .sort();

test.describe('end-to-end through the GUI, every bundled example', () => {
  test.skip(!toolchainAvailable(), `toolchain image ${TOOLCHAIN_IMAGE} not available`);
  // NOT serial: one example failing must not hide the state of the other
  // twelve. The point of the sweep is the whole picture.
  test.describe.configure({ mode: 'default', timeout: 180_000 });

  let launched: Launched | null = null;

  test.beforeAll(async () => {
    launched = await launch();
  });

  test.afterAll(async () => {
    if (launched) await launched.app.close();
  });

  test('the GUI lists every bundled example', async () => {
    const page = launched!.page;
    const env = await call<{ examples: Array<{ name: string }> }>(page, 'listExamples');
    expect(env.ok, `listExamples: ${env.ok ? '' : env.error.message}`).toBe(true);
    if (!env.ok) return;
    const listed = env.data.examples.map((e) => e.name).sort();
    // A user can only reach what the menu offers. An example that ships but is
    // not listed is unreachable from the GUI, whatever the CLI can do with it.
    expect(listed).toEqual(EXAMPLES);
  });

  test('New Project is reachable from the File menu, not just the bridge', async () => {
    // The tests around this one drive `window.gatepack` directly, which proves
    // the plumbing works and nothing about whether a user can get to it. A
    // capability with no menu entry is not a capability -- it is an API. This
    // reads the real Electron application menu out of the main process.
    const menu = await launched!.app.evaluate(({ Menu }) => {
      const file = Menu.getApplicationMenu()?.items.find((i) => i.label === 'File');
      return (file?.submenu?.items ?? []).map((i) => ({
        label: i.label,
        accelerator: i.accelerator ?? null,
        enabled: i.enabled,
      }));
    });
    const item = menu.find((i) => i.label.startsWith('New Project'));
    expect(item, `File menu had: ${menu.map((i) => i.label).join(', ')}`).toBeTruthy();
    expect(item!.enabled).toBe(true);
    expect(item!.accelerator).toBe('CmdOrCtrl+N');
  });

  test('a user can create a design from nothing and reach a build', async () => {
    // The other tests all start from a bundled example. This one asks the
    // harder half of the question: can someone *create* a design in the GUI,
    // rather than only open one that already exists?
    //
    // This test was written before that was possible and pinned as an expected
    // failure, because the GUI had no New Project command and openProjectPath
    // refuses a directory with no design.yaml -- so every original design had
    // to start outside the application. `gatepack project new` and File > New
    // closed it, and the test is now the positive form it was always written
    // as: from an empty directory, through the bridge only, to a BOM.
    const page = launched!.page;
    const parent = fs.mkdtempSync(path.join(os.tmpdir(), 'gatepack-fromscratch-'));
    const dir = path.join(parent, 'my first board');

    const created = await page.evaluate(
      (d) => (window as any).gatepack.newProject(d),
      dir,
    );
    expect(created.ok, `newProject: ${created.ok ? '' : created.error.message}`).toBe(true);
    if (!created.ok) return;

    // Scaffolded *and* opened: a New Project that leaves the user with no
    // project open has not created anything they can work on.
    expect(created.data.path).toBe(dir);
    expect(fs.existsSync(path.join(dir, 'design.yaml'))).toBe(true);
    expect(fs.existsSync(path.join(dir, 'parts.csv'))).toBe(true);

    // The directory name is not an identifier; the design name derived from it
    // must be one, because it reaches generated Verilog as a module name.
    const spec = await call<{ text: string }>(page, 'readSpec');
    expect(spec.ok, 'readSpec on the new project').toBe(true);
    if (spec.ok) expect(spec.data.text).toContain('name: my_first_board');

    // The whole point: the scaffold is a working design, not a stub. A user
    // who presses verify immediately after File > New must get a verdict, not
    // an error about a file they did not write.
    const compiled = await call<any>(page, 'compile');
    expect(compiled.ok, `compile: ${compiled.ok ? '' : compiled.error.message}`).toBe(true);
    const verified = await call<{ checks: any[] }>(page, 'verify');
    expect(verified.ok, `verify: ${verified.ok ? '' : verified.error.message}`).toBe(true);
    if (verified.ok) {
      expect(verified.data.checks.filter((c) => c.status === 'failed')).toEqual([]);
    }
    const built = await call<any>(page, 'build');
    expect(built.ok, `build: ${built.ok ? '' : built.error.message}`).toBe(true);
    if (built.ok) expect(fs.existsSync(built.data.bomPath)).toBe(true);
  });

  test('New Project refuses to scaffold over an existing design', async () => {
    // A file dialog makes it easy to land on a directory that already holds a
    // project. Overwriting it would destroy work, and the refusal has to be
    // legible -- the user needs to know to pick another directory, not that
    // something went wrong.
    const page = launched!.page;
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'gatepack-occupied-'));
    fs.writeFileSync(path.join(dir, 'design.yaml'), 'name: mine\n');

    const created = await page.evaluate((d) => (window as any).gatepack.newProject(d), dir);
    expect(created.ok).toBe(false);
    if (created.ok) return;
    expect(created.error.message.length).toBeGreaterThan(0);
    expect(fs.readFileSync(path.join(dir, 'design.yaml'), 'utf8')).toBe('name: mine\n');
  });

  for (const name of EXAMPLES) {
    test(`${name}: open -> compile -> estimate -> verify -> build`, async () => {
      const page = launched!.page;

      // -- open ------------------------------------------------------------
      const opened = await page.evaluate(
        (n) => (window as any).gatepack.openExample(n),
        name,
      );
      expect(opened.ok, `openExample(${name})`).toBe(true);
      const root = opened.data.path as string;

      // The library must travel with the example. Without a parts.csv beside
      // the design, session.cts silently drops `--library`, and the user gets
      // a verify/build over the default library without ever being told.
      expect(
        fs.existsSync(path.join(root, 'parts.csv')),
        `${name} opened without a parts.csv beside it`,
      ).toBe(true);

      // -- the spec is editable in the GUI ---------------------------------
      const spec = await call<{ text: string }>(page, 'readSpec');
      expect(spec.ok, 'readSpec').toBe(true);
      if (spec.ok) expect(spec.data.text.length).toBeGreaterThan(0);

      // -- compile ---------------------------------------------------------
      const compiled = await call<any>(page, 'compile');
      expect(compiled.ok, `compile: ${compiled.ok ? '' : compiled.error.message}`).toBe(true);

      // -- estimate --------------------------------------------------------
      // §6 is synchronous-only and an asynchronous design is refused by
      // design. That refusal is acceptable *if the GUI can render it* — a
      // legible error envelope. GP9002 ("no parseable JSON envelope") is not
      // legible: it is the sentinel for a command the core did not recognise,
      // and it would leave the user staring at a broken button.
      const estimated = await call<any>(page, 'estimate');
      if (!estimated.ok) {
        expect(estimated.error.code, `${name} estimate error is legible`).not.toBe('GP9002');
        expect(estimated.error.message.length).toBeGreaterThan(0);
      }

      // -- verify ----------------------------------------------------------
      const verified = await call<{ checks: any[]; allPassed: boolean }>(page, 'verify');
      expect(verified.ok, `verify: ${verified.ok ? '' : verified.error.message}`).toBe(true);
      if (verified.ok) {
        expect(verified.data.checks.length, `${name} produced no checks`).toBeGreaterThan(0);
        // No check may have failed. `not_run` is allowed only when it is not
        // the whole story — see the evidence assertion below.
        const failed = verified.data.checks.filter((c) => c.status === 'failed');
        expect(failed, `${name} failing checks`).toEqual([]);
        // A verdict must rest on evidence: at least one check that measured
        // what the design *does* actually passed. Hazard checks say the
        // netlist does not glitch, not that it implements the design.
        const behavioural = verified.data.checks.filter(
          (c) =>
            ['equivalence', 'simulation', 'property'].includes(c.kind) &&
            (c.status === 'passed' || c.status === 'bounded'),
        );
        expect(
          behavioural.length,
          `${name} verified with no behavioural evidence: ` +
            verified.data.checks.map((c) => `${c.name}=${c.status}`).join(', '),
        ).toBeGreaterThan(0);
      }

      // -- build -----------------------------------------------------------
      const built = await call<any>(page, 'build');
      expect(built.ok, `build: ${built.ok ? '' : built.error.message}`).toBe(true);
      if (!built.ok) return;

      // The three artefacts a user needs to actually make the board. Each is
      // reported by path, so each must exist where the GUI says it does.
      for (const key of ['bomPath', 'netlistPath', 'reportPath'] as const) {
        const p = built.data[key] as string;
        expect(p, `${name} build reported no ${key}`).toBeTruthy();
        expect(fs.existsSync(p), `${name} ${key} missing on disk: ${p}`).toBe(true);
        expect(fs.statSync(p).size, `${name} ${key} is empty`).toBeGreaterThan(0);
      }
      expect(built.data.bom.length, `${name} built an empty BOM`).toBeGreaterThan(0);
      expect(built.data.packageCount, `${name} built zero packages`).toBeGreaterThan(0);

      // -- the post-build views the GUI offers ------------------------------
      // Each of these backs a tab the user can click. A tab may legitimately
      // have nothing to show for a given design class -- provenance needs a
      // pre-map netlist, and an asynchronous design is synthesised straight
      // from its flow table, so it has none (§7.3). What it may NOT do is fail
      // in a way the user cannot act on, and the specific trap is an error
      // that instructs them to do what they have just done: after a successful
      // build, "run `gatepack build` first" sends them round a loop that
      // cannot terminate.
      for (const view of ['analyse', 'mappedNetlist', 'packedNetlist'] as const) {
        const env = await call<any>(page, view);
        expect(env.ok, `${name} ${view}: ${env.ok ? '' : env.error.message}`).toBe(true);
      }
      const prov = await call<any>(page, 'provenance');
      if (!prov.ok) {
        expect(prov.error.code, `${name} provenance error is legible`).not.toBe('GP9002');
        expect(
          prov.error.message,
          `${name} provenance told the user to build after a successful build`,
        ).not.toContain('run `gatepack build` first');
        expect(prov.error.message.length).toBeGreaterThan(0);
      }

      // The truth-table view's divergence column needs `actual` from the
      // mapped netlist; without it the column can never diverge and the view
      // is decorative (the M14 finding in gui-audit.spec.ts).
      const sim = await call<{ rows: any[] }>(page, 'simulate');
      expect(sim.ok, `${name} simulate: ${sim.ok ? '' : sim.error.message}`).toBe(true);
    });
  }
});
