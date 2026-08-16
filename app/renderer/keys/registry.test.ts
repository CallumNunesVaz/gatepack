/**
 * The registry's own guarantees.
 *
 * These are the checks that make one central shortcut table worth having: a
 * conflict fails here rather than silently shadowing at runtime, and every CLI
 * command stays reachable from the GUI.
 */

import { describe, expect, it } from 'vitest';
import {
  COMMANDS,
  assertNoConflicts,
  canonicalKeys,
  commandById,
  displayKeys,
  matchesChord,
  type CommandDef,
} from './registry';
import { PANEL_COMMANDS } from '../panels';

describe('shortcut registry', () => {
  it('has no conflicting chords or duplicate ids', () => {
    expect(() => assertNoConflicts()).not.toThrow();
  });

  it('detects a conflict rather than letting one shortcut shadow another', () => {
    const clashing: CommandDef[] = [
      { id: 'a', title: 'A', group: 'app', keys: 'Mod+K' },
      // Same chord, written differently — the canonical form must catch it.
      { id: 'b', title: 'B', group: 'app', keys: 'ctrl+k' },
    ];
    expect(() => assertNoConflicts(clashing)).toThrow(/conflict/i);
  });

  it('detects a duplicate id', () => {
    const dup: CommandDef[] = [
      { id: 'a', title: 'A', group: 'app' },
      { id: 'a', title: 'A again', group: 'app' },
    ];
    expect(() => assertNoConflicts(dup)).toThrow(/duplicate/i);
  });

  it('canonicalises modifier spelling and order', () => {
    expect(canonicalKeys('Ctrl+Shift+K')).toBe(canonicalKeys('Mod+Shift+k'));
    expect(canonicalKeys('Shift+Alt+Mod+p')).toBe('mod+alt+shift+p');
    expect(canonicalKeys('Cmd+S')).toBe(canonicalKeys('Ctrl+S'));
  });

  it('matches a real keyboard event, and rejects a near miss', () => {
    const ev = (init: Partial<KeyboardEvent>) => init as KeyboardEvent;
    expect(matchesChord(ev({ key: 'b', ctrlKey: true, metaKey: false, altKey: false, shiftKey: false }), 'Mod+B')).toBe(true);
    expect(matchesChord(ev({ key: 'b', ctrlKey: false, metaKey: true, altKey: false, shiftKey: false }), 'Mod+B')).toBe(true);
    // Bare `b` must not fire a Mod+B command — the commonest way a shortcut
    // handler eats ordinary typing in a text field.
    expect(matchesChord(ev({ key: 'b', ctrlKey: false, metaKey: false, altKey: false, shiftKey: false }), 'Mod+B')).toBe(false);
    // An extra modifier is a different chord, not a looser match.
    expect(matchesChord(ev({ key: 'b', ctrlKey: true, metaKey: false, altKey: false, shiftKey: true }), 'Mod+B')).toBe(false);
  });

  it('displays platform-appropriate modifier glyphs', () => {
    expect(displayKeys('Mod+K', 'MacIntel')).toEqual(['⌘', 'K']);
    expect(displayKeys('Mod+K', 'Linux x86_64')).toEqual(['Ctrl', 'K']);
    expect(displayKeys('Escape', 'Linux x86_64')).toEqual(['Esc']);
  });

  /**
   * The parity check the user asked for: everything the CLI does must be
   * reachable in the GUI. `lib` and `project` are covered by their own
   * commands; `examples` by the open-example command.
   *
   * This list is the CLI's subcommand set. When a new subcommand is added to
   * `gatepack/cli.py` this test fails until the GUI can reach it — which is the
   * only way "the GUI does what the CLI does" survives contact with time.
   */
  it('reaches every CLI subcommand', () => {
    const CLI_SUBCOMMANDS = [
      'lib',
      'compile',
      'estimate',
      'verify',
      'simulate',
      'build',
      'analyse',
      'provenance',
      'mapped-netlist',
      'packed-netlist',
      'examples',
      'doctor',
      'project',
    ];
    const reachable = new Set(COMMANDS.map((c) => c.cli).filter(Boolean));
    const missing = CLI_SUBCOMMANDS.filter((c) => !reachable.has(c));
    expect(missing).toEqual([]);
  });

  it('gives every command a title and a known group', () => {
    const groups = new Set(['project', 'view', 'run', 'inspect', 'selection', 'app']);
    for (const c of COMMANDS) {
      expect(c.title.length, `${c.id} has no title`).toBeGreaterThan(0);
      expect(groups.has(c.group), `${c.id} has unknown group ${c.group}`).toBe(true);
    }
  });

  it('looks a command up by id', () => {
    expect(commandById('run.build')?.title).toBe('Build');
    expect(commandById('nope')).toBeUndefined();
  });

  /**
   * The sufficiency half of CLI parity. The reachability check above only proves
   * that a command *entry* exists for each CLI subcommand — a necessary
   * condition that says nothing about whether the command does anything. A
   * command tagged `cli` that dispatches to nothing is a lie to the user, so
   * every panel command (`inspect.*`, `project.examples`) must also map to a
   * component the shell's `PanelHost` mounts. `PanelHost.test.tsx` proves those
   * handlers are actually registered; this test proves the registry and the
   * handler table cannot drift apart.
   */
  it('resolves every panel command to a mounted handler, and only to real commands', () => {
    const panelIds = new Set(PANEL_COMMANDS.map((p) => p.id));
    const targets = COMMANDS.filter(
      (c) => c.group === 'inspect' || c.id === 'project.examples',
    );
    expect(targets.length, 'there are panel commands to wire').toBeGreaterThan(0);
    for (const c of targets) {
      expect(panelIds.has(c.id), `${c.id} must map to a mounted panel handler`).toBe(true);
    }
    for (const id of panelIds) {
      expect(commandById(id), `panel handler ${id} must have a registry entry`).toBeTruthy();
    }
  });
});
