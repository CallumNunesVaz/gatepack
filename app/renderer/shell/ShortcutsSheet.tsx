/**
 * The keyboard-shortcuts help sheet — `Mod+/`.
 *
 * Generated directly from `COMMANDS`, so it cannot drift from what is actually
 * bound: the same table drives the global key handler, the palette and this
 * sheet. There is no second, hand-maintained list to fall out of sync.
 */

import { useEffect, useRef } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import { COMMANDS, displayKeys } from '../keys/registry';
import { GROUP_LABELS, GROUP_ORDER } from './groups';
import { Icon } from '../ui';

export interface ShortcutsSheetProps {
  open: boolean;
  onClose: () => void;
}

export function ShortcutsSheet({ open, onClose }: ShortcutsSheetProps) {
  const rootRef = useRef<HTMLDivElement | null>(null);

  // Take focus so Escape (handled on the sheet) reaches it, and so a keyboard
  // user lands inside the sheet rather than behind it.
  useEffect(() => {
    if (open) rootRef.current?.focus();
  }, [open]);

  if (!open) return null;

  const onKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Escape') {
      e.stopPropagation();
      onClose();
    }
  };

  return (
    <div
      className="gp-palette-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={rootRef}
        className="gp-shortcuts"
        role="dialog"
        aria-modal="true"
        aria-label="Keyboard shortcuts"
        data-testid="shortcuts-sheet"
        tabIndex={-1}
        onKeyDown={onKeyDown}
      >
        <header className="gp-shortcuts__header">
          <h2 className="gp-shortcuts__title">Keyboard shortcuts</h2>
          <button type="button" className="gp-icon-button" aria-label="Close" onClick={onClose}>
            <Icon name="close" size={16} decorative />
          </button>
        </header>
        <div className="gp-shortcuts__body">
          {GROUP_ORDER.map((group) => {
            const items = COMMANDS.filter((c) => c.group === group);
            if (items.length === 0) return null;
            return (
              <section key={group} className="gp-shortcuts__group">
                <h3 className="gp-shortcuts__group-label">{GROUP_LABELS[group]}</h3>
                <ul className="gp-shortcuts__list">
                  {items.map((command) => (
                    <li key={command.id} className="gp-shortcuts__row" data-command-id={command.id}>
                      <span className="gp-shortcuts__name">
                        {command.icon ? <Icon name={command.icon} size={16} decorative /> : null}
                        <span>{command.title}</span>
                      </span>
                      {command.hint ? (
                        <span className="gp-shortcuts__hint">{command.hint}</span>
                      ) : null}
                      {command.keys ? (
                        <span className="gp-shortcuts__keys">
                          {displayKeys(command.keys).map((k) => (
                            <kbd key={k} className="gp-kbd">
                              {k}
                            </kbd>
                          ))}
                        </span>
                      ) : (
                        <span className="gp-shortcuts__keys gp-shortcuts__keys--none">—</span>
                      )}
                    </li>
                  ))}
                </ul>
              </section>
            );
          })}
        </div>
      </div>
    </div>
  );
}
