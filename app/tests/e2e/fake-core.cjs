#!/usr/bin/env node
/*
 * Hermetic fake `gatepack` core for the Electron end-to-end tests.
 *
 * Main invokes this executable the same way it invokes the real Python core:
 *   gatepack <command> [sub] ... [--json]
 * so it must (a) answer every command the bridge can dispatch and (b) emit
 * envelopes that validate against the zod schemas in app/main/envelope.cts.
 *
 * The payloads below are hand-copied from the real core's `--json` output
 * (cross-checked against `./start cli ... --json`, which runs
 * `gatepack-toolchain:m6` when yosys is missing) and against the payload
 * builders in gatepack/api.py. They are deliberately small but carry every
 * field the schemas require, with the same names, types and enum values the
 * real core emits — a fake that invented a *different* shape would be a lie
 * that passed main's validation and told the renderer nothing about the real
 * core.
 *
 * Honesty hooks, for the tests:
 *   GATEPACK_FAKE_SLEEP_SECS  — `compile` sleeps this many seconds first
 *                               (exercises cancel() of an in-flight call).
 *   GATEPACK_FAKE_FAIL        — comma-separated list of commands that should
 *                               answer with a well-formed `ok: false` envelope
 *                               and exit non-zero (exercises error surfacing).
 *   GATEPACK_FAKE_NONZERO_OK  — comma-separated list of commands that should
 *                               answer with a well-formed `ok: true` envelope
 *                               and STILL exit non-zero. The real core does this
 *                               for exactly one command: `verify`, whose exit
 *                               code encodes all-green-ness while the envelope
 *                               stays the authoritative answer (missing tools ->
 *                               `not_run` checks with `skippedReason`). This
 *                               hook models that, so e2e can prove the app
 *                               renders the check list rather than discarding
 *                               the envelope as "core exited 1".
 *
 * `project explode` / `project bundle` are raw verbs (no `--json`): the fake
 * copies `design.yaml` exactly as the real project verbs move the spec, so the
 * .gpk open/save paths in app.spec.ts keep working against it.
 */

'use strict';

const fs = require('node:fs');
const path = require('node:path');

// What `project new` writes. Shape only -- the real template lives in
// gatepack/scaffold.py and is tested there; the fake exists so the main
// process's New Project path can be driven without Python.
const FAKE_SPEC = [
  '# a new gatepack design (fake core)',
  'name: from_scratch',
  'timing_model: synchronous',
  'clock: {signal: clk, freq_hz: 1000, source: OSC}',
  'reset: {signal: rst_n, active: low, source: SUPERVISOR}',
  'encoding: one_hot',
  'inputs:',
  '  - {name: go, sync: true}',
  'outputs:',
  '  - {name: active}',
  'states: [IDLE, RUN]',
  'initial: IDLE',
  'transitions:',
  '  - {from: IDLE, to: RUN,  when: "go"}',
  '  - {from: IDLE, to: IDLE, when: "!go"}',
  '  - {from: RUN,  to: RUN,  when: "go"}',
  '  - {from: RUN,  to: IDLE, when: "!go"}',
  'output_logic:',
  '  active: "state == RUN"',
  '',
].join('\n');

const FAKE_PARTS_CSV = 'part_number,cell,package,vcc_min_v,vcc_max_v,citation\n';

const argv = process.argv.slice(2);
const cmd = argv[0] ?? '';
const sub = argv[1] ?? '';

function hasFlag(name) {
  return argv.includes(name);
}

function flagValue(name, fallback) {
  const i = argv.indexOf(name);
  return i >= 0 && i + 1 < argv.length ? argv[i + 1] : fallback;
}

function ok(command, data, warnings) {
  return { ok: true, command, schema: 1, data, warnings: warnings || [] };
}

function err(command, code, message) {
  return {
    ok: false,
    command,
    schema: 1,
    error: { severity: 'error', code, message },
    warnings: [],
  };
}

function emit(envelope, exitCode) {
  process.stdout.write(JSON.stringify(envelope) + '\n');
  process.exit(exitCode);
}

function sleepMs(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function refsPathFor(csvPath) {
  return csvPath.replace(/\.csv$/, '') + '.refs.md';
}

/* ------------------------------------------------------------------ */
/* payloads (field-for-field with gatepack/api.py + envelope.cts)      */
/* ------------------------------------------------------------------ */

function compileData() {
  const out = flagValue('-o', 'build');
  return {
    verilogPath: path.join(out, 'generated.v'),
    propertiesPath: path.join(out, 'properties.sv'),
    flopCount: 2,
    stateCount: 3,
    encoding: 'one_hot',
    johnsonSuggestion: null,
  };
}

function estimateData() {
  return {
    verdict: 'amber',
    reasons: ['flop count is amber (value 2)'],
    packageCount: 4,
    flopCount: 2,
    cellCounts: { INV: 1, NAND2: 2, DFF_R: 2 },
    alternative: null,
  };
}

function verifyData() {
  return {
    checks: [
      { name: 'equivalence', kind: 'equivalence', status: 'passed', durationMs: 0 },
      { name: 'exhaustive simulation', kind: 'simulation', status: 'passed', durationMs: 0 },
      { name: 'mutation', kind: 'mutation', status: 'passed', durationMs: 0 },
      { name: 'property never_walk_with_traffic', kind: 'property', status: 'passed', durationMs: 0 },
    ],
    allPassed: true,
  };
}

// The real core's `verify` output when the toolchain is absent: the command
// executed and this envelope is its answer (`ok: true`), but the checks that
// need yosys/iverilog/sby could not run, so `allPassed` is false and each
// `not_run` check names its missing tool. The core exits 1 to signal "not
// all-green" — a legitimate state, not a lying core.
function verifyNotRunData() {
  return {
    checks: [
      {
        name: 'equivalence',
        kind: 'equivalence',
        status: 'not_run',
        skippedReason: 'yosys not installed (logic synthesis, §C3)',
        durationMs: 0,
      },
      {
        name: 'exhaustive simulation',
        kind: 'simulation',
        status: 'not_run',
        skippedReason: 'iverilog not installed (Icarus — compiles the simulation testbench)',
        durationMs: 0,
      },
      {
        name: 'mutation',
        kind: 'mutation',
        status: 'not_run',
        skippedReason: 'yosys + iverilog required (synthesis + simulation)',
        durationMs: 0,
      },
      {
        name: 'property never_walk_with_traffic',
        kind: 'property',
        status: 'not_run',
        skippedReason: 'sby not found on PATH (SymbiYosys — runs the §11 formal property checks)',
        durationMs: 0,
      },
    ],
    allPassed: false,
  };
}

function analysisSummary() {
  return {
    metrics: [
      { name: 'package count', value: 4, unit: 'packages', limit: null, violated: false },
      { name: 'flop count', value: 2, unit: 'flops', limit: null, violated: false },
    ],
    scoap: [],
    faults: { detected: 0, undetected: 0, redundant: 0, untestable: 0 },
    cpldBlockers: [],
  };
}

function buildData() {
  const out = flagValue('--out', 'out');
  return {
    bomPath: path.join(out, 'bom.csv'),
    netlistPath: path.join(out, 'netlist.net'),
    reportPath: path.join(out, 'report.md'),
    mappedJsonPath: path.join(out, 'mapped.json'),
    packageCount: 4,
    spareCount: 1,
    packCost: 6.4,
    bom: [
      {
        partNumber: '74AUP1G04',
        manufacturers: ['TI', 'Nexperia', 'Diodes'],
        package: 'SOT-353',
        quantity: 2,
        refdes: ['U1', 'U2'],
        tier: 'G',
        singleSourced: false,
        gatesPerPackage: 1,
      },
      {
        partNumber: '74AUP1G175',
        manufacturers: ['TI', 'Nexperia'],
        package: 'SOT-353',
        quantity: 2,
        refdes: ['U3', 'U4'],
        tier: 'F',
        singleSourced: false,
        gatesPerPackage: 1,
      },
    ],
    analysis: analysisSummary(),
    stableCellNames: { '$abc$148$99$154': 'NAND2__5150c006' },
  };
}

function provenanceData() {
  return {
    entries: [
      {
        pointer: 'design.yaml:12:transitions[0]',
        nets: ['t_0'],
        cells: ['$abc$139$auto$blifparse.cc:386:parse_blif$144'],
        confidence: 'exact',
      },
      {
        pointer: 'design.yaml:19:output_logic.y',
        nets: ['y_int'],
        cells: [],
        confidence: 'inferred',
      },
    ],
    coverage: 0.75,
  };
}

function simulateData() {
  return {
    inputNames: ['a', 'b'],
    outputNames: ['y'],
    rows: [
      { inputs: { a: '0', b: '0' }, expected: { y: '0' }, actual: { y: '0' }, diverges: false },
      { inputs: { a: '0', b: '1' }, expected: { y: '1' }, actual: { y: '1' }, diverges: false },
      { inputs: { a: '1', b: '0' }, expected: { y: '1' }, actual: { y: '1' }, diverges: false },
      { inputs: { a: '1', b: '1' }, expected: { y: '0' }, actual: { y: '0' }, diverges: false },
    ],
    dontCareCount: 0,
    unreachableCount: 0,
    exhaustive: true,
  };
}

function mappedNetlistData() {
  return {
    creator: 'Yosys 0.23',
    modules: {
      top: {
        ports: {
          a: { direction: 'input', bits: [0] },
          b: { direction: 'input', bits: [1] },
          y: { direction: 'output', bits: [2] },
        },
        netnames: { a: { bits: [0] }, b: { bits: [1] }, y: { bits: [2] } },
        cells: {
          '$abc$148$99$154': {
            hide_name: 1,
            type: 'NAND2',
            parameters: {},
            attributes: {},
            connections: { A: [0], B: [1], Y: [2] },
          },
        },
      },
    },
  };
}

function packedNetlistData() {
  return {
    packages: [
      {
        refdes: 'U1',
        partNumber: '74AUP1G00',
        cells: ['NAND2__5150c006'],
        instanceCells: ['$abc$148$99$154'],
        capacity: 1,
        spare: 0,
        rationale: 'function group: NAND2 (1G00) holds 1 gate(s)',
      },
    ],
  };
}

function doctorData() {
  return {
    allToolsPresent: false,
    tools: [
      {
        name: 'yosys',
        direct: true,
        found: false,
        path: null,
        version: null,
        purpose: 'logic synthesis (C3): behavioural Verilog -> mapped netlist',
      },
      {
        name: 'sby',
        direct: true,
        found: false,
        path: null,
        version: null,
        purpose: 'formal property checking + equivalence fallback',
      },
      {
        name: 'iverilog',
        direct: true,
        found: false,
        path: null,
        version: null,
        purpose: 'compiles the exhaustive-simulation testbench (Icarus)',
      },
      {
        name: 'vvp',
        direct: true,
        found: false,
        path: null,
        version: null,
        purpose: 'Icarus runtime: runs the compiled simulation testbench',
      },
      {
        name: 'z3',
        direct: false,
        found: false,
        path: null,
        version: null,
        purpose: "SMT solver used by sby's smtbmc engine (reached indirectly)",
      },
    ],
    resources: { commonFrontendYs: true, mcellModels: true, mcellCount: 1 },
  };
}

function libraryCheckData() {
  const csvPath = argv[2] ?? 'parts.csv';
  return {
    path: csvPath,
    refsPath: refsPathFor(csvPath),
    refsPresent: false,
    cellCount: 1,
    includedCount: 1,
    excludedCount: 0,
    missingCitations: ['INV'],
    parts: [
      {
        cell: 'INV',
        tier: 'G',
        family: 'AUP',
        partNumber: '74AUP1G04',
        function: '!A',
        inputs: 1,
        gatesPerPackage: 1,
        package: 'SOT-353',
        manufacturers: ['TI', 'Nexperia', 'Diodes'],
        equivalents: 0,
        secondSourceCount: 3,
        citation: null,
        unverified: false,
        excluded: false,
        exclusionReason: null,
      },
    ],
  };
}

function examplesListData() {
  return {
    examples: [
      {
        name: 'pelican',
        summary: 'Pelican crossing controller — the showcase project (§18.1)',
        isShowcase: true,
      },
    ],
  };
}

/* ------------------------------------------------------------------ */
/* dispatch                                                            */
/* ------------------------------------------------------------------ */

async function main() {
  // Raw verbs (no --json), used by the session manager and the menu.
  if (cmd === 'project') {
    const out = flagValue('-o', '');
    if (sub === 'explode') {
      const gpk = argv[2];
      fs.mkdirSync(out, { recursive: true });
      fs.copyFileSync(gpk, path.join(out, 'design.yaml'));
      process.exit(0);
    }
    if (sub === 'bundle') {
      const dir = argv[2];
      fs.mkdirSync(path.dirname(out), { recursive: true });
      fs.copyFileSync(path.join(dir, 'design.yaml'), out);
      process.exit(0);
    }
    // `project new` scaffolds a project. The fake mirrors the two properties
    // the main process actually depends on: both files land, and an existing
    // design.yaml is refused rather than overwritten.
    if (sub === 'new') {
      const dir = argv[2];
      const design = path.join(dir, 'design.yaml');
      if (fs.existsSync(design)) {
        process.stderr.write(`error: ${design} already exists\n`);
        process.exit(2);
      }
      fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(design, FAKE_SPEC);
      const parts = path.join(dir, 'parts.csv');
      if (!fs.existsSync(parts)) fs.writeFileSync(parts, FAKE_PARTS_CSV);
      process.stdout.write(`wrote ${design}\nwrote ${parts}\n`);
      process.exit(0);
    }
    process.exit(2);
  }

  // The Examples submenu reads `examples list` WITHOUT `--json`.
  if (cmd === 'examples' && sub === 'list' && !hasFlag('--json')) {
    process.stdout.write(
      'pelican (showcase)\n' +
        '    Pelican crossing controller — the showcase project (§18.1)\n',
    );
    process.exit(0);
  }

  if (cmd === 'compile' && process.env.GATEPACK_FAKE_SLEEP_SECS) {
    await sleepMs(Number(process.env.GATEPACK_FAKE_SLEEP_SECS) * 1000);
  }

  const failList = (process.env.GATEPACK_FAKE_FAIL || '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);

  if (failList.includes(cmd)) {
    emit(err(cmd, 'GP1003', 'yosys is not available; synthesis cannot run'), 1);
    return;
  }

  const nonzeroOkList = (process.env.GATEPACK_FAKE_NONZERO_OK || '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);

  if (nonzeroOkList.includes(cmd) && cmd === 'verify') {
    emit(ok('verify', verifyNotRunData()), 1);
    return;
  }

  switch (cmd) {
    case 'compile':
      return emit(ok('compile', compileData()), 0);
    case 'estimate':
      return emit(ok('estimate', estimateData()), 0);
    case 'verify':
      return emit(ok('verify', verifyData()), 0);
    case 'build':
      return emit(ok('build', buildData()), 0);
    case 'analyse':
      return emit(ok('analyse', analysisSummary()), 0);
    case 'provenance':
      return emit(ok('provenance', provenanceData()), 0);
    case 'simulate':
      return emit(ok('simulate', simulateData()), 0);
    case 'mapped-netlist':
      return emit(ok('mapped-netlist', mappedNetlistData()), 0);
    case 'packed-netlist':
      return emit(ok('packed-netlist', packedNetlistData()), 0);
    case 'doctor':
      return emit(ok('doctor', doctorData()), 0);
    case 'lib':
      if (sub === 'check') return emit(ok('lib', libraryCheckData()), 0);
      break;
    case 'examples':
      if (sub === 'list') return emit(ok('examples', examplesListData()), 0);
      break;
    default:
      break;
  }

  // Anything else is an unknown command, exactly like the real core's
  // argparse failure, only as a well-formed error envelope.
  emit(err(cmd, 'GP9999', `unknown command: ${cmd}`), 2);
}

main().catch((e) => {
  process.stderr.write(String(e && e.stack ? e.stack : e) + '\n');
  process.exit(1);
});
