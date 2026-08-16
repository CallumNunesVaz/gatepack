/**
 * The application shell — the workspace that hosts the six views.
 *
 * Layout (CSS grid, tokens-only): a left icon rail for the six views, a main
 * region (top bar + the active view, scrolling inside itself), a right
 * inspector, and a status bar spanning the bottom. Below the inspector
 * breakpoint the inspector is shed rather than crushing the main region; the
 * page body never scrolls horizontally — wide content scrolls in its own
 * container.
 *
 * The shell owns the command bus, the theme, the global shortcut handler, the
 * palette and the shortcuts sheet. Panels own the commands they implement;
 * anything else reaches the dispatcher and reports "not yet wired".
 */

import { useEffect, useMemo, useState, type ComponentType } from 'react';
import { useProject } from '../state/project';
import { useTheme } from './theme';
import { useDensity } from './density';
import { CommandBusProvider, createCommandBus, useCommandBus } from './commands';
import { useGlobalShortcuts } from './keyboard';
import { CommandPalette } from './CommandPalette';
import { ShortcutsSheet } from './ShortcutsSheet';
import { Inspector } from './Inspector';
import { StatusBar } from './StatusBar';
import { Icon, IconButton, ToastProvider, useToast } from '../ui';
import { commandById, displayKeys } from '../keys/registry';
import type { IconName } from '../ui';
import type { CommandHandler } from './commands';

import { SpecEditor } from '../views/SpecEditor';
import { TruthTable } from '../views/TruthTable';
import { Schematic } from '../views/Schematic';
import { BomView } from '../views/BomView';
import { AnalysisView } from '../views/AnalysisView';
import { VerificationPanel } from '../views/VerificationPanel';

type ViewId = 'spec' | 'truthtable' | 'schematic' | 'packing' | 'analysis' | 'verify';

interface ViewDef {
  id: ViewId;
  command: string;
  label: string;
  icon: IconName;
  component: ComponentType;
}

const VIEWS: ViewDef[] = [
  { id: 'spec', command: 'view.spec', label: 'Spec editor', icon: 'spec', component: SpecEditor },
  { id: 'truthtable', command: 'view.truthTable', label: 'Truth table', icon: 'truthTable', component: TruthTable },
  { id: 'schematic', command: 'view.schematic', label: 'Schematic', icon: 'schematic', component: Schematic },
  { id: 'packing', command: 'view.packing', label: 'Packing & BOM', icon: 'packing', component: BomView },
  { id: 'analysis', command: 'view.analysis', label: 'Analysis', icon: 'analysis', component: AnalysisView },
  { id: 'verify', command: 'view.verify', label: 'Verification', icon: 'verify', component: VerificationPanel },
];

function ShellContent() {
  const { theme, toggle } = useTheme();
  useDensity();
  const bus = useCommandBus();
  const { model } = useProject();

  const [activeView, setActiveView] = useState<ViewId>('spec');
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);

  // Built-in commands. Panels register the rest (run.*, inspect.*, project.*).
  useEffect(() => {
    const unregisters: Array<() => void> = [
      bus.register('app.theme', () => toggle()),
      bus.register('app.palette', () => setPaletteOpen((v) => !v)),
      bus.register('app.shortcuts', () => setShortcutsOpen((v) => !v)),
      ...VIEWS.map((v) => bus.register(v.command, () => setActiveView(v.id))),
    ];
    return () => unregisters.forEach((unregister) => unregister());
  }, [bus, toggle]);

  useGlobalShortcuts(bus.dispatch);

  const activeDef = VIEWS.find((v) => v.id === activeView) ?? VIEWS[0];
  const ActiveView = activeDef.component;

  const run = (id: string) => {
    bus.dispatch(id);
  };

  return (
    <div className="shell">
      <nav className="shell__rail" aria-label="Views" data-testid="shell-rail">
        <div className="shell__brand" aria-hidden="true">
          <Icon name="chip" size={22} decorative />
        </div>
        {VIEWS.map((v) => (
          <IconButton
            key={v.id}
            name={v.icon}
            label={v.label}
            tooltip={v.label}
            active={activeView === v.id}
            tooltipSide="right"
            data-testid={`nav-${v.id}`}
            onClick={() => bus.dispatch(v.command)}
          />
        ))}
        <div className="shell__rail-spacer" />
        <IconButton
          name="theme"
          label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
          tooltip="Toggle theme"
          tooltipSide="right"
          data-testid="nav-theme"
          onClick={() => bus.dispatch('app.theme')}
        />
        <IconButton
          name="keyboard"
          label="Keyboard shortcuts"
          tooltip="Keyboard shortcuts"
          keys={displayKeys('Mod+/')}
          tooltipSide="right"
          data-testid="nav-shortcuts"
          onClick={() => bus.dispatch('app.shortcuts')}
        />
      </nav>

      <main className="shell__main">
        <header className="shell__topbar">
          <span className="shell__title">gatepack</span>
          {model ? <span className="shell__design">{model.name}</span> : null}
          <button
            type="button"
            className="shell__search"
            data-testid="palette-trigger"
            onClick={() => bus.dispatch('app.palette')}
          >
            <Icon name="search" size={14} decorative />
            <span className="shell__search-text">Search commands</span>
            <span className="shell__search-keys">
              {displayKeys('Mod+K').map((k) => (
                <kbd key={k} className="gp-kbd">
                  {k}
                </kbd>
              ))}
            </span>
          </button>
        </header>
        <div className="shell__content">
          <ActiveView />
        </div>
      </main>

      <aside className="shell__inspector" data-testid="shell-inspector">
        <Inspector />
      </aside>

      <StatusBar />

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} onRun={run} />
      <ShortcutsSheet open={shortcutsOpen} onClose={() => setShortcutsOpen(false)} />
    </div>
  );
}

/**
 * Creates the command bus inside the ToastProvider (so an unwired command can
 * be reported as a toast) and provides it to the shell below.
 */
function ShellWithBus() {
  const toast = useToast();
  const bus = useMemo(
    () =>
      createCommandBus((id) => {
        const def = commandById(id);
        toast.push(
          def ? `"${def.title}" is not wired yet` : `Command "${id}" is not wired yet`,
        );
      }),
    [toast],
  );
  return (
    <CommandBusProvider bus={bus}>
      <ShellContent />
    </CommandBusProvider>
  );
}

export function Shell() {
  return (
    <ToastProvider>
      <ShellWithBus />
    </ToastProvider>
  );
}

// Re-exported so panels can type their registration without a deep import.
export type { CommandHandler };
