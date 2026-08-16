/**
 * The host that wires the inspector/utility panels into the command bus.
 *
 * The six panels (`inspect.*` and `project.examples`) exist and are unit-tested,
 * but nothing imported them and no handler was registered for their commands,
 * so dispatching one from the palette showed a "not yet wired" toast and the
 * panel was unreachable. This component is the seam: it registers a handler for
 * every `PANEL_COMMANDS` entry and mounts the chosen panel in a modal dialog.
 *
 * Presentation is a dialog (not a docked pane or a tab) for three reasons:
 *   - it matches the shell's existing modal vocabulary (palette, shortcuts
 *     sheet), so Escape-dismiss and focus restoration are the same code shape
 *     the shell already promises;
 *   - the right-hand inspector already has a meaning (selection context) and
 *     repurposing it would make two very different surfaces share a slot;
 *   - the panels are tall (netlists, tables) and a dialog gives them room
 *     without reshuffling the six-view grid.
 *
 * It is keyboard-dismissible (Escape, or the close button) and returns focus to
 * the element that had it before the panel opened.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import { useCommandBus } from './commands';
import { PANEL_COMMANDS, panelCommandById } from '../panels';
import { IconButton } from '../ui';

export function PanelHost() {
  const bus = useCommandBus();
  const [activeId, setActiveId] = useState<string | null>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);

  // One handler per panel command, registered for as long as the shell lives.
  useEffect(() => {
    const unregisters = PANEL_COMMANDS.map(({ id }) =>
      bus.register(id, () => setActiveId(id)),
    );
    return () => unregisters.forEach((unregister) => unregister());
  }, [bus]);

  // On open: remember where focus was, then put it in the dialog so Escape and
  // the close button are reachable. On close: hand focus back.
  useEffect(() => {
    if (activeId !== null) {
      const active = document.activeElement;
      if (active instanceof HTMLElement) restoreFocusRef.current = active;
      dialogRef.current?.focus();
    } else {
      restoreFocusRef.current?.focus();
      restoreFocusRef.current = null;
    }
  }, [activeId]);

  const close = useCallback(() => setActiveId(null), []);

  if (activeId === null) return null;
  const entry = panelCommandById(activeId);
  if (!entry) return null;
  const PanelComponent = entry.component;

  const onKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Escape') {
      e.stopPropagation();
      close();
    }
  };

  return (
    <div
      className="gp-panel-host-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <div
        ref={dialogRef}
        className="gp-panel-host"
        role="dialog"
        aria-modal="true"
        aria-label={entry.title}
        data-testid="panel-host"
        tabIndex={-1}
        onKeyDown={onKeyDown}
      >
        <div className="gp-panel-host__close">
          <IconButton
            name="close"
            label={`Close ${entry.title}`}
            tooltip="Close panel"
            data-testid="panel-host-close"
            onClick={close}
          />
        </div>
        <div className="gp-panel-host__body">
          <PanelComponent />
        </div>
      </div>
    </div>
  );
}
