/**
 * GUI-audit regression tests (docs/GUI-AUDIT.md).
 *
 * These drive the REAL main process against the REAL Python core (no fake), and
 * pin two contract breaches found while auditing M13–M16:
 *
 *  1. M14 — `gatepack simulate` returns `actual: "x"` for every output of every
 *     design, combinational included, so the C11 divergence column can never
 *     diverge. The post-ABC Yosys `write_json` carries no `port_directions`, and
 *     `simulate` never resolves pin directions from the parts table, so the
 *     combinational-cone evaluator skips every cell. `diverges` is always false.
 *  2. M15/M16 — the main process invokes `gatepack mapped-netlist`, `gatepack
 *     provenance` and `gatepack analyse`, none of which exist in the CLI, so the
 *     schematic's netlist, the linked-selection spine and the analysis dashboard
 *     are all unreachable.
 *
 * These are REGRESSION tests: they assert the fixed behaviour and therefore fail
 * against the current core. They are hermetic — the simulated-netlist test seeds
 * a `mapped.json` shaped exactly like real Yosys output, so no Yosys is needed.
 */

import { _electron, expect, test, type ElectronApplication, type Page } from '@playwright/test';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const APP_DIR = path.resolve(HERE, '..', '..');
const REPO_ROOT = path.resolve(APP_DIR, '..');

const XOR2_DESIGN = `name: xor2
timing_model: synchronous
clock: {signal: clk, freq_hz: 1000, source: OSC}
reset: {signal: rst_n, active: low, source: SUPERVISOR}
encoding: one_hot
inputs:
  - {name: a, sync: false}
  - {name: b, sync: false}
outputs:
  - {name: y}
states: [S0]
initial: S0
transitions:
  - {from: S0, to: S0, when: "1"}
output_logic:
  y: "a ^ b"
`;

/**
 * A `mapped.json` shaped exactly like real Yosys 0.23 post-ABC output: cells
 * carry `hide_name`/`type`/`parameters`/`attributes`/`connections` and NO
 * `port_directions` (verified against `gatepack-toolchain:m6` — `mapped.json`
 * has zero `port_directions` occurrences while `premap.json` has them).
 */
const XOR2_MAPPED_JSON = JSON.stringify({
  modules: {
    xor2: {
      ports: {
        a: { direction: 'input', bits: [0] },
        b: { direction: 'input', bits: [1] },
        y: { direction: 'output', bits: [2] },
      },
      netnames: {
        a: { bits: [0] },
        b: { bits: [1] },
        y: { bits: [2] },
      },
      cells: {
        $xor: {
          hide_name: 1,
          type: 'XOR2',
          parameters: {},
          attributes: {},
          connections: { A: [0], B: [1], Y: [2] },
        },
      },
    },
  },
});

let realCorePath: string | null = null;

function getRealCore(): string | null {
  const py = path.join(REPO_ROOT, '.venv', 'bin', 'python');
  if (!fs.existsSync(py)) return null;
  if (realCorePath === null) {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'gatepack-realcore-'));
    realCorePath = path.join(dir, 'gatepack');
    // PYTHONPATH is required: the core is spawned with cwd = the opened
    // project directory, not the repo root, so `python -m gatepack.cli` only
    // resolves `gatepack` when PYTHONPATH points at the repo root (this is the
    // same thing `main/core.cts` does in its `.venv/bin/python` fallback).
    fs.writeFileSync(
      realCorePath,
      `#!/bin/sh\nexport PYTHONPATH="${REPO_ROOT}"\nexec "${py}" -m gatepack.cli "$@"\n`,
    );
    fs.chmodSync(realCorePath, 0o755);
  }
  return realCorePath;
}

interface Launched {
  app: ElectronApplication;
  page: Page;
}

async function launchRealCoreApp(): Promise<Launched> {
  const core = getRealCore();
  if (core === null) throw new Error('real core not locatable (.venv/bin/python)');
  const app = await _electron.launch({
    args: [APP_DIR],
    env: {
      ...process.env,
      GATEPACK_CORE: core,
      GATEPACK_SESSION_DIR: fs.mkdtempSync(path.join(os.tmpdir(), 'gatepack-session-')),
    },
  });
  const page = await app.firstWindow();
  await page.waitForFunction(() => typeof (window as any).gatepack !== 'undefined');
  return { app, page };
}

function makeProjectDir(files: Record<string, string>): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'gatepack-audit-'));
  for (const [name, content] of Object.entries(files)) {
    const p = path.join(dir, name);
    fs.mkdirSync(path.dirname(p), { recursive: true });
    fs.writeFileSync(p, content);
  }
  return dir;
}

const LIBRARY_CSV = path.join(REPO_ROOT, 'libraries', '74aup.csv');
const realCoreAvailable = fs.existsSync(path.join(REPO_ROOT, '.venv', 'bin', 'python'));

test.describe('GUI audit regression', () => {
  let launched: Launched | null = null;

  test.afterEach(async () => {
    if (launched) {
      await launched.app.close();
      launched = null;
    }
  });

  test.skip(!realCoreAvailable, 'real core (.venv/bin/python) not present');

  test('M14: simulate() returns real (non-x) `actual` for a combinational netlist', async () => {
    launched = await launchRealCoreApp();
    const page = launched.page;

    const dir = makeProjectDir({
      'design.yaml': XOR2_DESIGN,
      'parts.csv': fs.readFileSync(LIBRARY_CSV, 'utf8'),
      '.gatepack/build/mapped.json': XOR2_MAPPED_JSON,
    });
    const opened = await page.evaluate(
      (p) => (window as any).gatepack.openProjectPath(p),
      dir,
    );
    expect(opened.ok).toBe(true);

    const env = await page.evaluate(() => (window as any).gatepack.simulate());
    expect(env.ok).toBe(true);
    const rows = env.data.rows as Array<{ inputs: Record<string, string>; actual?: Record<string, string>; expected: Record<string, string>; diverges: boolean }>;

    // A pure combinational XOR: the mapped netlist must evaluate, so `actual`
    // carries 0/1 values (not `x`) and agrees with the spec. The buggy core
    // returns `actual: { y: "x" }` on every row, so this fails today.
    const byInputs = new Map(
      rows.map((r) => [JSON.stringify(r.inputs), r]),
    );
    expect(byInputs.size).toBe(4);
    for (const [key, expected] of [
      ['{"a":"0","b":"0"}', '0'],
      ['{"a":"0","b":"1"}', '1'],
      ['{"a":"1","b":"0"}', '1'],
      ['{"a":"1","b":"1"}', '0'],
    ] as const) {
      const row = byInputs.get(key)!;
      expect(row, key).toBeTruthy();
      expect(row.actual, `${key} actual`).toBeTruthy();
      expect(row.actual!.y, `${key} actual.y`).toBe(expected);
      expect(row.actual!.y, `${key} actual.y is not x`).not.toBe('x');
      expect(row.diverges, `${key} diverges`).toBe(false);
    }
  });

  test('M13: a graph edit mutates the YAML, and positions never enter design.yaml', async () => {
    launched = await launchRealCoreApp();
    const page = launched.page;

    // First launch opens the pelican showcase (5 states, 7 transitions).
    const spec = await page.evaluate(() => (window as any).gatepack.readSpec());
    expect(spec.ok).toBe(true);
    const text0 = spec.data.text as string;
    expect(text0).toContain('states: [GO, WARN, STOP, CROSS, CLEAR]');
    // No layout positions may ever appear in the spec text.
    for (const marker of ['position', 'layout', '"x"', '"y"', 'x:', 'y:']) {
      expect(text0, `no '${marker}' in spec text`).not.toContain(marker);
    }

    // Switch to the FSM graph tab and confirm all five states render as nodes.
    await page.getByRole('button', { name: 'FSM graph' }).click();
    await page.waitForSelector('.react-flow__node');
    const nodeCount = await page.locator('.react-flow__node').count();
    expect(nodeCount).toBe(5);

    // A graph edit is a document mutation: adding a state must rewrite the YAML.
    await page.getByRole('button', { name: '+ state' }).click();
    await expect(page.locator('.react-flow__node')).toHaveCount(6);
    // The debounced writeSpec (400 ms) lands in the scratch project.
    await page.waitForTimeout(600);
    const spec2 = await page.evaluate(() => (window as any).gatepack.readSpec());
    const text2 = spec2.data.text as string;
    expect(text2).toContain('S5');
    // Positions still never enter the document after an edit.
    for (const marker of ['position', 'layout', '"x"', '"y"', 'x:', 'y:']) {
      expect(text2, `no '${marker}' in spec text after edit`).not.toContain(marker);
    }
  });

  test('M15/M16: mappedNetlist()/provenance()/analyse() are recognised by the core', async () => {
    launched = await launchRealCoreApp();
    const page = launched.page;

    const dir = makeProjectDir({ 'design.yaml': XOR2_DESIGN });
    const opened = await page.evaluate(
      (p) => (window as any).gatepack.openProjectPath(p),
      dir,
    );
    expect(opened.ok).toBe(true);

    // The main process invokes `gatepack mapped-netlist`, `gatepack provenance`
    // and `gatepack analyse` (main/session.cts). None of these subcommands
    // exists in the CLI, so the core exits 2 with an argparse "invalid choice"
    // and the bridge surfaces GP9002 ("core emitted no parseable JSON
    // envelope"). A fixed core recognises them — the honest "not built" state
    // is a *different* envelope, never the unrecognised-command sentinel.
    for (const [name, call] of [
      ['mappedNetlist', () => (window as any).gatepack.mappedNetlist()],
      ['provenance', () => (window as any).gatepack.provenance()],
      ['analyse', () => (window as any).gatepack.analyse()],
    ] as const) {
      const env = await page.evaluate(call);
      expect(env.ok || env.error?.code !== 'GP9002', `${name} recognised`).toBe(true);
    }
  });
});
