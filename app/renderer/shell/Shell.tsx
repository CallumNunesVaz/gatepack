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
import { useApi } from '../bridge/context';
import { nextToken } from '../api';
import {
  deregisterInflightToken,
  inflightTokensSnapshot,
  registerInflightToken,
} from '../hooks/useRevisionedTask';
import { useTheme } from './theme';
import { useDensity } from './density';
import { CommandBusProvider, createCommandBus, useCommandBus } from './commands';
import { requestLinkReload } from '../selection/linkData';
import { RunRequestsProvider, useRunRequests } from './runRequests';
import { useGlobalShortcuts } from './keyboard';
import { CommandPalette } from './CommandPalette';
import { ShortcutsSheet } from './ShortcutsSheet';
import { PanelHost } from './PanelHost';
import { Inspector } from './Inspector';
import { StatusBar } from './StatusBar';
import { PipelineStrip } from './PipelineStrip';
import type { ViewId } from './pipeline';
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
  const api = useApi();
  const toast = useToast();
  useDensity();
  const bus = useCommandBus();
  const { request } = useRunRequests();
  const { model } = useProject();

  const [activeView, setActiveView] = useState<ViewId>('spec');
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);

  // Built-in commands. Panels register the rest (inspect.*, project.*).
  useEffect(() => {
    const unregisters: Array<() => void> = [
      bus.register('app.theme', () => toggle()),
      bus.register('app.palette', () => setPaletteOpen((v) => !v)),
      bus.register('app.shortcuts', () => setShortcutsOpen((v) => !v)),
      ...VIEWS.map((v) => bus.register(v.command, () => setActiveView(v.id))),
      // A reachable command that does nothing is a lie (see commands.tsx). The
      // palette lists `project.new`, so it is wired here rather than left to
      // report itself unhandled — the main process's File > New goes through
      // the same `newProjectDialog`, so the two surfaces cannot diverge.
      bus.register('project.new', () => {
        void api.newProjectDialog();
      }),
      // §GUI-1: reveal the build outputs in the file manager, and copy them to
      // a directory the user picks. Both go straight to the main process; the
      // destination for export is chosen by a native dialog, never by us.
      // Cancelled export is not an error to surface — it is the user changing
      // their mind — so `GP4201` is swallowed rather than toasted.
      bus.register('project.revealOutputs', () => {
        void api.revealOutputs().then((env) => {
          if (!env.ok) toast.push(env.error.message, 'error');
        });
      }),
      bus.register('project.exportOutputs', () => {
        void api.exportOutputs().then((env) => {
          if (env.ok) {
            toast.push(`Exported ${env.data.files.length} file(s) to ${env.data.path}`, 'success');
          } else if (env.error.code !== 'GP4201') {
            toast.push(env.error.message, 'error');
          }
        });
      }),
      // The run.* commands. Each switches to the owning view and *requests* a
      // run; the view performs it (see runRequests.tsx). The switch is issued
      // before the request so the target view is mounted and subscribed — and
      // when React batches the two into one render, the view drains the pending
      // request on mount instead of missing it.
      bus.register('run.build', () => {
        setActiveView('packing');
        request('run.build');
      }),
      bus.register('run.verify', () => {
        setActiveView('verify');
        request('run.verify');
      }),
      bus.register('run.estimate', () => {
        setActiveView('analysis');
        request('run.estimate');
      }),
      bus.register('run.analyse', () => {
        setActiveView('analysis');
        request('run.analyse');
      }),
      // `run.simulate` does NOT go through the run-request bus. The truth
      // table's only revisioned task is the `estimate`-backed cover preview;
      // its divergence column comes from `simulate()` through the linked
      // selection spine, which read it once on mount. Requesting the view's
      // task would have re-run *estimate* while the command said "Simulate
      // truth table" — a command reporting success for something else. The
      // spine now has a reload signal, and this asks it for a fresh read.
      bus.register('run.simulate', () => {
        setActiveView('truthtable');
        requestLinkReload();
      }),
      // `run.compile` has no owning view — the front-end `specification to
      // Verilog` check does not belong to any of the six views, so it runs here
      // and reports through the toast. It registers its token so `run.cancel`
      // can still stop it mid-flight.
      bus.register('run.compile', () => {
        const token = nextToken();
        registerInflightToken(token);
        void api.compile(token).then(
          (env) => {
            deregisterInflightToken(token);
            if (env.ok) {
              toast.push(
                `Compiled ${env.data.stateCount} states, ${env.data.flopCount} flops (${env.data.encoding} encoding)`,
                'success',
              );
            } else {
              toast.push(env.error.message, 'error');
            }
          },
          () => {
            // `api.compile` only rejects on cancellation (§16.1 — main re-throws
            // CancelledError, every other failure arrives as an error envelope).
            deregisterInflightToken(token);
            toast.push('Compile cancelled', 'info');
          },
        );
      }),
      // Cancel every in-flight task. One task is normally in flight; cancelling
      // all of them is correct and simpler than tracking which view is active.
      bus.register('run.cancel', () => {
        for (const token of inflightTokensSnapshot()) {
          void api.cancel(token);
        }
      }),
    ];
    return () => unregisters.forEach((unregister) => unregister());
  }, [bus, toggle, api, toast, request]);

  // Electron's own chrome — on Linux the menu bar drawn inside the window —
  // follows `nativeTheme`, which tracks the OS and knows nothing about the
  // in-app choice. Tell main which theme is actually on screen so a dark
  // window does not sit under a white File/Edit bar.
  useEffect(() => {
    void api.setNativeTheme?.(theme);
  }, [api, theme]);

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
        <PipelineStrip />
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
      {/* Rendered after the palette so its focus capture runs once the palette
          has restored focus to the invoking element. */}
      <PanelHost />
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
      <RunRequestsProvider>
        <ShellContent />
      </RunRequestsProvider>
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
