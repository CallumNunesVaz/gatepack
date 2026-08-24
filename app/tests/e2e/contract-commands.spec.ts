/**
 * The command contract between the e2e fake core and the real CLI.
 *
 * The e2e suite runs two cores: a hermetic fake (`fake-core.cjs`) for the
 * bridge-level specs, and the real Python CLI for the GUI-audit regressions.
 * The original GUI-audit defect was exactly the seam between the two: the
 * renderer invoked `mapped-netlist`, `provenance` and `analyse`, none of which
 * existed in the real CLI, and every test passed because every test asked the
 * fake. This spec is the general fix rather than a patch for those three:
 *
 *   * enumerate every command the fake answers (from its dispatch, live);
 *   * enumerate every command the real CLI registers (from `gatepack.cli`,
 *     live — `registered_commands()` walks the argparse parser, never a
 *     hand-copied list);
 *   * enumerate every command the renderer invokes (from `session.cts`'s
 *     `buildCommandArgs` plus its raw `project` verbs);
 *
 * then assert three things that would each have caught the defect:
 *
 *   1. the fake answers no command the real core does not have;
 *   2. every command the renderer invokes exists in the real core;
 *   3. every command the renderer invokes exists in the fake core.
 *
 * It runs in milliseconds — no Electron, no toolchain — so it can sit in the
 * e2e suite without costing a synthesis. The last test deletes a command from
 * the real registry and watches the check fail, which proves the check is not
 * vacuous (a check that cannot fail is worth nothing).
 */

import { spawnSync } from 'node:child_process';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { expect, test } from '@playwright/test';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const APP_DIR = path.resolve(HERE, '..', '..');
const REPO_ROOT = path.resolve(APP_DIR, '..');

const FAKE_CORE = path.join(HERE, 'fake-core.cjs');
const SESSION_CTS = path.join(APP_DIR, 'main', 'session.cts');

/** The parent command each fake subcommand belongs to. */
const SUB_PARENT: Record<string, string> = {
  check: 'lib',
  gen: 'lib',
  list: 'examples',
  extract: 'examples',
  explode: 'project',
  bundle: 'project',
  new: 'project',
};

/** Commands the fake core answers, derived from its dispatch source. */
function fakeCommands(source: string): Set<string> {
  const cmds = new Set<string>();
  // Leaf commands: every `case 'X':` in the switch. Parents (lib, examples,
  // project) are answered only through their subcommand, added below.
  const parents = new Set(Object.values(SUB_PARENT));
  for (const m of source.matchAll(/case\s+'([a-z-]+)':/g)) {
    if (!parents.has(m[1])) cmds.add(m[1]);
  }
  // Subcommands: `sub === 'X'` in the project / lib / examples dispatch.
  for (const m of source.matchAll(/sub\s*===\s*'([a-z]+)'/g)) {
    const parent = SUB_PARENT[m[1]];
    if (parent) cmds.add(`${parent} ${m[1]}`);
  }
  return cmds;
}

/** Commands the renderer invokes, derived from `session.cts`'s `buildCommandArgs`. */
function rendererCommands(source: string): Set<string> {
  const cmds = new Set<string>();
  // `return ['cmd', ...]` (optionally `['cmd', 'sub', ...]` for a subcommand).
  const retRe = /return\s+\[\s*'([a-z-]+)'(?:\s*,\s*'([a-z-]+)')?/g;
  for (const m of source.matchAll(retRe)) {
    const sub = m[2];
    // The second literal is a subcommand only when it is a word; the single-token
    // commands return identifiers (`design`, `outDir`) and flags (`-o`, `--build`)
    // after the command, which are never quoted literals, so they do not match.
    cmds.add(sub && /^[a-z][a-z-]*$/.test(sub) ? `${m[1]} ${sub}` : m[1]);
  }
  // The raw project verbs (runRaw ... ['project', 'explode'|'bundle', ...]).
  for (const m of source.matchAll(/\[\s*'project'\s*,\s*'([a-z]+)'/g)) {
    cmds.add(`project ${m[1]}`);
  }
  return cmds;
}

/**
 * Enumerate the real CLI's registered commands by walking `_build_parser`'s
 * subparsers live — never a hand-copied list — so a command removed from the
 * parser disappears here too. Done inline (no gatepack change needed): the
 * argparse walk is the same shape the project uses elsewhere for tests.
 */
const REGISTRY_SCRIPT = [
  'import argparse, json',
  'from gatepack.cli import _build_parser',
  'def subs(p):',
  '    for a in p._actions:',
  '        if isinstance(a, argparse._SubParsersAction):',
  '            return dict(a.choices)',
  '    return {}',
  'out = {}',
  'for cmd, sub in subs(_build_parser()).items():',
  '    out[cmd] = sorted(subs(sub))',
  'print(json.dumps(out))',
].join('\n');

/** Commands the real CLI registers, derived live from `gatepack.cli._build_parser`. */
function realCommands(): Set<string> {
  const py = path.join(REPO_ROOT, '.venv', 'bin', 'python');
  if (!fs.existsSync(py)) {
    throw new Error(`real core not locatable (${py}); the command contract cannot be checked`);
  }
  const r = spawnSync(py, ['-c', REGISTRY_SCRIPT], {
    cwd: REPO_ROOT,
    env: { ...process.env, PYTHONPATH: REPO_ROOT },
    encoding: 'utf8',
  });
  if (r.status !== 0) {
    throw new Error(`CLI registry enumeration failed (${r.status}): ${r.stderr}`);
  }
  const registry = JSON.parse(r.stdout) as Record<string, string[]>;
  const cmds = new Set<string>();
  for (const [cmd, subs] of Object.entries(registry)) {
    if (subs.length === 0) cmds.add(cmd);
    else for (const s of subs) cmds.add(`${cmd} ${s}`);
  }
  return cmds;
}

function diff(asked: Set<string>, answered: Set<string>): string[] {
  return [...asked].filter((c) => !answered.has(c)).sort();
}

test('the fake core answers no command the real core does not have', () => {
  const fake = fakeCommands(fs.readFileSync(FAKE_CORE, 'utf8'));
  const real = realCommands();
  // Sanity: the parsers found a real surface, not an empty one.
  expect(fake.size).toBeGreaterThan(10);
  expect(real.size).toBeGreaterThan(10);
  expect(diff(fake, real)).toEqual([]);
});

test('every command the renderer invokes exists in the real core', () => {
  const renderer = rendererCommands(fs.readFileSync(SESSION_CTS, 'utf8'));
  const real = realCommands();
  expect(renderer.size).toBeGreaterThan(10);
  expect(diff(renderer, real)).toEqual([]);
});

test('every command the renderer invokes exists in the fake core', () => {
  const renderer = rendererCommands(fs.readFileSync(SESSION_CTS, 'utf8'));
  const fake = fakeCommands(fs.readFileSync(FAKE_CORE, 'utf8'));
  expect(diff(renderer, fake)).toEqual([]);
});

test('the contract fails when a command is dropped from the real registry', () => {
  // The original defect, replayed: `mapped-netlist` (or any other command)
  // silently removed from the CLI while the fake and renderer still ask for it.
  // The check must flag it — a contract that passes with a missing command is
  // the exact vacuous pass this suite exists to prevent.
  const real = realCommands();
  const fake = fakeCommands(fs.readFileSync(FAKE_CORE, 'utf8'));
  expect(real.has('mapped-netlist')).toBe(true);

  const shrunk = new Set(real);
  shrunk.delete('mapped-netlist');
  expect(diff(fake, shrunk)).toContain('mapped-netlist');
});
