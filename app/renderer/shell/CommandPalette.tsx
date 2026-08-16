/**
 * The command palette — `Mod+K`.
 *
 * Fuzzy-filters `COMMANDS` (from `keys/registry.ts`), groups the results, and
 * hands the chosen id to the shell's dispatcher. Enter runs, arrows navigate,
 * Escape closes, and focus returns to the element that had it before the
 * palette opened. It is a view over the registry and nothing else — it never
 * knows what a command does.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import { COMMANDS, displayKeys, type CommandDef, type CommandGroup } from '../keys/registry';
import { filterCommands } from './filter';
import { GROUP_LABELS, GROUP_ORDER } from './groups';
import { Icon } from '../ui';

export interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  onRun: (id: string) => void;
}

interface GroupedCommands {
  group: CommandGroup;
  items: CommandDef[];
}

export function CommandPalette({ open, onClose, onRun }: CommandPaletteProps) {
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);

  const results = useMemo(() => filterCommands(query, COMMANDS), [query]);
  const grouped = useMemo<GroupedCommands[]>(() => {
    const byGroup = new Map<CommandGroup, CommandDef[]>();
    for (const group of GROUP_ORDER) byGroup.set(group, []);
    for (const command of results) byGroup.get(command.group)!.push(command);
    return GROUP_ORDER.filter((g) => byGroup.get(g)!.length > 0).map((group) => ({
      group,
      items: byGroup.get(group)!,
    }));
  }, [results]);
  const flat = useMemo(() => grouped.flatMap((g) => g.items), [grouped]);

  // On open: remember where focus was, reset the query, focus the search box.
  useEffect(() => {
    if (!open) return;
    const active = document.activeElement;
    restoreFocusRef.current = active instanceof HTMLElement ? active : null;
    setQuery('');
    setActiveIndex(0);
    inputRef.current?.focus();
  }, [open]);

  // On close: hand focus back to where it came from.
  useEffect(() => {
    if (!open) restoreFocusRef.current?.focus();
  }, [open]);

  // Any change to the query re-anchors the selection to the top.
  useEffect(() => {
    setActiveIndex(0);
  }, [query]);

  // Keep the active option visible as it moves.
  useEffect(() => {
    if (!open) return;
    const option = listRef.current?.querySelector(
      `[data-palette-index="${activeIndex}"]`,
    ) as HTMLElement | null;
    // jsdom does not implement scrollIntoView; guard the call.
    option?.scrollIntoView?.({ block: 'nearest' });
  }, [activeIndex, open]);

  if (!open) return null;

  const run = (id: string) => {
    onRun(id);
    onClose();
  };

  const onKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Escape') {
      e.stopPropagation();
      onClose();
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, flat.length - 1));
      return;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
      return;
    }
    if (e.key === 'Enter') {
      e.preventDefault();
      const command = flat[activeIndex];
      if (command) run(command.id);
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
        className="gp-palette"
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        data-testid="command-palette"
        onKeyDown={onKeyDown}
      >
        <div className="gp-palette__input-row">
          <Icon name="search" size={16} decorative />
          <input
            ref={inputRef}
            className="gp-palette__input"
            data-testid="palette-input"
            placeholder="Type a command…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search commands"
            role="combobox"
            aria-expanded="true"
            aria-controls="command-palette-list"
            aria-activedescendant={flat[activeIndex] ? `palette-option-${flat[activeIndex].id}` : undefined}
          />
        </div>
        <div className="gp-palette__list" id="command-palette-list" role="listbox" ref={listRef}>
          {grouped.length === 0 ? (
            <p className="gp-palette__empty" data-testid="palette-empty">
              No matching commands.
            </p>
          ) : (
            grouped.map(({ group, items }) => (
              <div key={group} className="gp-palette__group" role="group" aria-label={GROUP_LABELS[group]}>
                <div className="gp-palette__group-label">{GROUP_LABELS[group]}</div>
                {items.map((command) => {
                  const index = flat.indexOf(command);
                  const active = index === activeIndex;
                  return (
                    <button
                      key={command.id}
                      type="button"
                      role="option"
                      aria-selected={active}
                      id={`palette-option-${command.id}`}
                      data-palette-index={index}
                      data-command-id={command.id}
                      className={
                        active
                          ? 'gp-palette__option gp-palette__option--active'
                          : 'gp-palette__option'
                      }
                      onMouseEnter={() => setActiveIndex(index)}
                      onClick={() => run(command.id)}
                    >
                      <span className="gp-palette__option-icon">
                        {command.icon ? <Icon name={command.icon} size={16} decorative /> : null}
                      </span>
                      <span className="gp-palette__option-text">
                        <span className="gp-palette__option-title">{command.title}</span>
                        {command.hint ? (
                          <span className="gp-palette__option-hint">{command.hint}</span>
                        ) : null}
                      </span>
                      {command.keys ? (
                        <span className="gp-palette__option-keys">
                          {displayKeys(command.keys).map((k) => (
                            <kbd key={k} className="gp-kbd">
                              {k}
                            </kbd>
                          ))}
                        </span>
                      ) : null}
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
