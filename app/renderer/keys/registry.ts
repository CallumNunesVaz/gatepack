/**
 * The keyboard shortcut registry — one table, so conflicts are impossible.
 *
 * Every shortcut in the app is declared here and nowhere else. The reason is
 * not tidiness: shortcuts registered ad hoc in the components that use them
 * cannot be checked for collisions, cannot be listed in a help sheet without
 * drifting from what is actually bound, and silently shadow each other when two
 * panels are mounted at once.
 *
 * `COMMANDS` is the source of truth for the palette, the help sheet and the
 * key handler alike. A command with no `keys` is still reachable from the
 * palette — that is the point: everything the CLI can do must be reachable
 * here, and only the frequent things earn a chord.
 */

import type { IconName } from '../ui/Icon';

/** Where a command appears, and how it is grouped in the palette. */
export type CommandGroup =
  | 'project'
  | 'view'
  | 'run'
  | 'inspect'
  | 'selection'
  | 'app';

export interface CommandDef {
  /** Stable id — what the handler dispatches on. Never shown to the user. */
  id: string;
  /** Imperative, as it reads in the palette: "Build netlist", not "Building". */
  title: string;
  group: CommandGroup;
  icon?: IconName;
  /**
   * Chord in the canonical form `Mod+Shift+K`. `Mod` is Ctrl everywhere except
   * macOS, where the shell maps it to Cmd — never write `Ctrl` directly unless
   * the binding must be Ctrl on a Mac too.
   */
  keys?: string;
  /** One sentence for the tooltip and the palette's second line. */
  hint?: string;
  /**
   * The CLI subcommand this corresponds to, when there is one. Present so the
   * parity test can assert that every CLI command is reachable from the GUI —
   * the check that keeps "the GUI does what the CLI does" true over time.
   */
  cli?: string;
}

/**
 * Canonicalise a chord so `ctrl+shift+k`, `Ctrl+Shift+K` and `Mod+Shift+K`
 * compare equal. Modifier order is fixed: Mod, Alt, Shift.
 */
export function canonicalKeys(chord: string): string {
  const parts = chord.split('+').map((p) => p.trim().toLowerCase());
  const key = parts[parts.length - 1];
  const mods = new Set(parts.slice(0, -1).map((m) => (m === 'ctrl' || m === 'cmd' || m === 'meta' ? 'mod' : m)));
  const order = ['mod', 'alt', 'shift'].filter((m) => mods.has(m));
  return [...order, key].join('+');
}

/** Match a keyboard event against a canonical chord. */
export function matchesChord(e: KeyboardEvent, chord: string): boolean {
  const want = canonicalKeys(chord).split('+');
  const key = want[want.length - 1];
  const mods = new Set(want.slice(0, -1));
  const mod = e.ctrlKey || e.metaKey;
  if (mods.has('mod') !== mod) return false;
  if (mods.has('alt') !== e.altKey) return false;
  if (mods.has('shift') !== e.shiftKey) return false;
  return e.key.toLowerCase() === key;
}

/** Render a chord for display, with the platform's modifier glyphs. */
export function displayKeys(chord: string, platform: string = navigator.platform): string[] {
  const mac = /mac|iphone|ipad/i.test(platform);
  return canonicalKeys(chord)
    .split('+')
    .map((part) => {
      if (part === 'mod') return mac ? '⌘' : 'Ctrl';
      if (part === 'alt') return mac ? '⌥' : 'Alt';
      if (part === 'shift') return mac ? '⇧' : 'Shift';
      if (part === 'escape') return 'Esc';
      if (part === 'arrowleft') return '←';
      if (part === 'arrowright') return '→';
      if (part === 'arrowup') return '↑';
      if (part === 'arrowdown') return '↓';
      return part.length === 1 ? part.toUpperCase() : part[0].toUpperCase() + part.slice(1);
    });
}

/**
 * Every command in the application.
 *
 * Owned by the shell package. Other packages add entries here rather than
 * binding keys locally; `assertNoConflicts` is run by a test, so a duplicate
 * chord fails the build rather than silently shadowing.
 */
export const COMMANDS: CommandDef[] = [
  // --- project -----------------------------------------------------------
  { id: 'project.new', title: 'New project…', group: 'project', icon: 'open', keys: 'Mod+N', cli: 'project', hint: 'Scaffold a design.yaml and parts.csv, then open them' },
  { id: 'project.open', title: 'Open project…', group: 'project', icon: 'open', keys: 'Mod+O', hint: 'Open a project directory or .gpk file' },
  { id: 'project.save', title: 'Save', group: 'project', icon: 'save', keys: 'Mod+S', hint: 'Write the specification back to disk' },
  // `project bundle` / `project explode` are what saving and opening a .gpk
  // run underneath, which is why this carries the `project` CLI tag.
  { id: 'project.saveAs', title: 'Save as…', group: 'project', icon: 'save', keys: 'Mod+Shift+S', cli: 'project' },
  { id: 'project.close', title: 'Close project', group: 'project', icon: 'close' },
  { id: 'project.examples', title: 'Open bundled example…', group: 'project', icon: 'open', cli: 'examples' },

  // --- views -------------------------------------------------------------
  { id: 'view.spec', title: 'Spec editor', group: 'view', icon: 'spec', keys: 'Mod+1' },
  { id: 'view.truthTable', title: 'Truth table', group: 'view', icon: 'truthTable', keys: 'Mod+2' },
  { id: 'view.schematic', title: 'Schematic', group: 'view', icon: 'schematic', keys: 'Mod+3' },
  { id: 'view.packing', title: 'Packing & BOM', group: 'view', icon: 'packing', keys: 'Mod+4' },
  { id: 'view.analysis', title: 'Analysis', group: 'view', icon: 'analysis', keys: 'Mod+5' },
  { id: 'view.verify', title: 'Verification', group: 'view', icon: 'verify', keys: 'Mod+6' },

  // --- run ---------------------------------------------------------------
  { id: 'run.compile', title: 'Compile', group: 'run', icon: 'compile', keys: 'Mod+Shift+C', hint: 'Front end only: specification to Verilog', cli: 'compile' },
  { id: 'run.estimate', title: 'Estimate viability', group: 'run', icon: 'estimate', keys: 'Mod+E', hint: 'Package count and verdict before a full build', cli: 'estimate' },
  { id: 'run.build', title: 'Build', group: 'run', icon: 'build', keys: 'Mod+B', hint: 'Synthesise, pack, verify and emit the BOM', cli: 'build' },
  { id: 'run.verify', title: 'Verify', group: 'run', icon: 'verify', keys: 'Mod+Shift+V', hint: 'Formal equivalence, properties and exhaustive simulation', cli: 'verify' },
  { id: 'run.simulate', title: 'Simulate truth table', group: 'run', icon: 'simulate', cli: 'simulate' },
  { id: 'run.analyse', title: 'Analyse', group: 'run', icon: 'analysis', cli: 'analyse' },
  { id: 'run.cancel', title: 'Cancel running command', group: 'run', icon: 'cancel', keys: 'Escape' },

  // --- inspect -----------------------------------------------------------
  { id: 'inspect.provenance', title: 'Provenance map', group: 'inspect', icon: 'provenance', cli: 'provenance' },
  { id: 'inspect.mappedNetlist', title: 'Mapped netlist', group: 'inspect', icon: 'chip', cli: 'mapped-netlist' },
  { id: 'inspect.packedNetlist', title: 'Packed netlist', group: 'inspect', icon: 'packing', cli: 'packed-netlist' },
  { id: 'inspect.doctor', title: 'Toolchain status', group: 'inspect', icon: 'doctor', keys: 'Mod+Shift+D', hint: 'Which external tools the core can reach', cli: 'doctor' },
  { id: 'inspect.library', title: 'Check part library', group: 'inspect', icon: 'chip', cli: 'lib' },

  // --- app ---------------------------------------------------------------
  { id: 'app.palette', title: 'Command palette', group: 'app', icon: 'search', keys: 'Mod+K', hint: 'Every command, searchable' },
  { id: 'app.shortcuts', title: 'Keyboard shortcuts', group: 'app', icon: 'keyboard', keys: 'Mod+/' },
  { id: 'app.theme', title: 'Toggle theme', group: 'app', icon: 'theme' },
];

/**
 * Throw if two commands bind the same chord, or an id repeats.
 *
 * Called by a test rather than at import time: a conflict should fail CI
 * loudly, not break the app at runtime for a user.
 */
export function assertNoConflicts(commands: CommandDef[] = COMMANDS): void {
  const byChord = new Map<string, string>();
  const ids = new Set<string>();
  for (const c of commands) {
    if (ids.has(c.id)) throw new Error(`duplicate command id: ${c.id}`);
    ids.add(c.id);
    if (!c.keys) continue;
    const chord = canonicalKeys(c.keys);
    const existing = byChord.get(chord);
    if (existing) {
      throw new Error(`shortcut conflict: ${chord} bound by both ${existing} and ${c.id}`);
    }
    byChord.set(chord, c.id);
  }
}

export function commandById(id: string): CommandDef | undefined {
  return COMMANDS.find((c) => c.id === id);
}
