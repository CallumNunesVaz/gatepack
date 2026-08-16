/**
 * The table-driven test Defect 2 unlocks: every bridge method that reaches the
 * core must return an envelope the main process *accepts* — i.e. one that
 * validated against the zod schemas in app/main/envelope.cts and was passed
 * through to the renderer with `ok: true`.
 *
 * Before the fake core was extended it answered only `compile` and `project`;
 * every other command returned the GP9999 "unknown command" sentinel, so the
 * e2e suite could only ever exercise error paths. This table pins the whole
 * surface: if any one payload stops validating (wrong field name, wrong type,
 * wrong enum member), main returns GP9003 and the corresponding row goes red.
 */

import { expect, test, type Page } from '@playwright/test';
import * as fs from 'node:fs';
import * as path from 'node:path';

import { closeApp, launchApp, makeProjectDir, type LaunchedApp } from './helpers';

const DESIGN_TEXT = `gatepack: 1
kind: design
name: bridge_test
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

const PARTS_CSV = `cell,tier,family,part_suffix,function,inputs,gates_per_pkg,package,manufacturers,vcc_min,vcc_max
INV,G,AUP,04,"!A",1,1,SOT-353,"TI;Nexperia;Diodes",0.8,3.6
`;

let app: LaunchedApp | null = null;

test.afterEach(async () => {
  if (app) {
    await closeApp(app);
    app = null;
  }
});

test('every core-backed bridge method returns an envelope main accepts', async () => {
  app = await launchApp();
  const page = app.page;

  const dir = makeProjectDir(DESIGN_TEXT);
  const partsPath = path.join(dir, 'parts.csv');
  fs.writeFileSync(partsPath, PARTS_CSV);

  const opened = await page.evaluate(
    (p: string) => (window as any).gatepack.openProjectPath(p),
    dir,
  );
  expect(opened.ok).toBe(true);

  // (name, expected core `command`, invocation) — one row per bridge method
  // that reaches the core. `command` is what the real core prints in the
  // envelope's `command` field (cross-checked via `./start cli ... --json`);
  // asserting it here pins that the fake core did not invent a different one.
  const rows: Array<{ name: string; command: string; call: (p: Page) => Promise<unknown> }> = [
    { name: 'compile', command: 'compile', call: (p) => p.evaluate(() => (window as any).gatepack.compile('tok-1')) },
    { name: 'estimate', command: 'estimate', call: (p) => p.evaluate(() => (window as any).gatepack.estimate('tok-2')) },
    { name: 'verify', command: 'verify', call: (p) => p.evaluate(() => (window as any).gatepack.verify('tok-3')) },
    { name: 'build', command: 'build', call: (p) => p.evaluate(() => (window as any).gatepack.build('tok-4')) },
    { name: 'analyse', command: 'analyse', call: (p) => p.evaluate(() => (window as any).gatepack.analyse('tok-5')) },
    { name: 'simulate', command: 'simulate', call: (p) => p.evaluate(() => (window as any).gatepack.simulate('tok-6')) },
    { name: 'provenance', command: 'provenance', call: (p) => p.evaluate(() => (window as any).gatepack.provenance()) },
    { name: 'mappedNetlist', command: 'mapped-netlist', call: (p) => p.evaluate(() => (window as any).gatepack.mappedNetlist()) },
    { name: 'packedNetlist', command: 'packed-netlist', call: (p) => p.evaluate(() => (window as any).gatepack.packedNetlist()) },
    { name: 'doctor', command: 'doctor', call: (p) => p.evaluate(() => (window as any).gatepack.doctor()) },
    { name: 'listExamples', command: 'examples', call: (p) => p.evaluate(() => (window as any).gatepack.listExamples()) },
    { name: 'checkLibrary', command: 'lib', call: (p) => p.evaluate((arg: string) => (window as any).gatepack.checkLibrary(arg), partsPath) },
  ];

  for (const row of rows) {
    const env = (await row.call(page)) as {
      ok: boolean;
      command: string;
      schema: number;
      data?: unknown;
      error?: { code: string; message: string };
    };
    // `ok: true` here means main's zod validation accepted the payload; any
    // divergence from the schema surfaces as GP9003 with `ok: false`.
    expect(env.ok, `${row.name} should be accepted by main`).toBe(true);
    expect(env.schema, `${row.name} schema version`).toBe(1);
    expect(env.command, `${row.name} command field`).toBe(row.command);
    expect(env.data, `${row.name} carries a data payload`).toBeDefined();
    expect(env.error, `${row.name} has no error`).toBeUndefined();
  }
});
