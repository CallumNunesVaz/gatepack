/**
 * The command dispatch seam.
 *
 * The shell owns a single `dispatch(id, payload?)` entry point. Every command
 * in `keys/registry.ts` is reached by id through it — the palette, the global
 * key handler, and the rail all call the same bus. Panels that implement a
 * command (the run panel, the doctor panel, …) call `register(id, handler)` on
 * mount and `unregister` on unmount; the shell wires the built-ins (view
 * switching, theme, palette, shortcuts).
 *
 * A command id that reaches `dispatch` with no registered handler is **not**
 * silently dropped: the bus reports it to `onUnhandled`, and the shell turns
 * that into a visible "not yet wired" toast. A reachable command that does
 * nothing is a lie; a reachable command that says so is a promise.
 */

import { createContext, useContext, type ReactNode } from 'react';

export type CommandHandler = (payload?: unknown) => void;

export interface CommandBus {
  /** Run a command by id. Returns false when no handler is registered. */
  dispatch(id: string, payload?: unknown): boolean;
  /** Register a handler; returns an unregister function. */
  register(id: string, handler: CommandHandler): () => void;
  isRegistered(id: string): boolean;
}

export function createCommandBus(onUnhandled?: (id: string) => void): CommandBus {
  const handlers = new Map<string, CommandHandler>();
  return {
    dispatch(id, payload) {
      const handler = handlers.get(id);
      if (handler) {
        handler(payload);
        return true;
      }
      onUnhandled?.(id);
      return false;
    },
    register(id, handler) {
      handlers.set(id, handler);
      return () => {
        if (handlers.get(id) === handler) handlers.delete(id);
      };
    },
    isRegistered(id) {
      return handlers.has(id);
    },
  };
}

const CommandBusContext = createContext<CommandBus | null>(null);

export function CommandBusProvider({ bus, children }: { bus: CommandBus; children: ReactNode }) {
  return <CommandBusContext.Provider value={bus}>{children}</CommandBusContext.Provider>;
}

export function useCommandBus(): CommandBus {
  const bus = useContext(CommandBusContext);
  if (!bus) throw new Error('useCommandBus must be used inside <CommandBusProvider>');
  return bus;
}
