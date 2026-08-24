/**
 * The run-request bus — the second half of "a command must work from any view".
 *
 * The shell owns the command bus and the built-ins (view switching, theme,
 * palette). But the code that *runs* a toolchain task lives inside the view
 * that owns it: `BomView` owns the build task, `VerificationPanel` the verify
 * task, and so on. A `run.*` command therefore has to do two things — switch
 * to the owning view and *ask* it to run — and the two halves meet at this bus:
 *
 *   - `request(id)` bumps a nonce for the command id;
 *   - `useRunRequest(id, fn)` fires `fn` whenever that nonce changes.
 *
 * `useRunRequest` must not fire on mount. Switching to a view and asking it to
 * run are different events, and if mounting were enough to fire, every view
 * switch would silently launch a toolchain job. The shell switches the view
 * *before* requesting a run, but React batches both state updates into one
 * render, so the target view mounts *after* the nonce has already been bumped.
 * To close that race the bus remembers an *undelivered* request (a `pending`
 * flag per id); `useRunRequest` drains a pending request once on mount, and
 * thereafter only fires on nonce changes. No `setTimeout`, no extra tick.
 */

import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';

export interface RunRequestBus {
  /** Ask every mounted subscriber of `id` to run, now or when it mounts. */
  request(id: string): void;
}

interface RunRequestStore extends RunRequestBus {
  getNonce(id: string): number;
  consumePending(id: string): boolean;
  subscribe(listener: () => void): () => void;
}

function createRunRequestStore(): RunRequestStore {
  const nonces = new Map<string, number>();
  const pending = new Set<string>();
  const listeners = new Set<() => void>();

  return {
    request(id) {
      nonces.set(id, (nonces.get(id) ?? 0) + 1);
      pending.add(id);
      for (const listener of listeners) listener();
    },
    getNonce(id) {
      return nonces.get(id) ?? 0;
    },
    consumePending(id) {
      return pending.delete(id);
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}

const RunRequestsContext = createContext<RunRequestStore | null>(null);

export function RunRequestsProvider({ children }: { children: ReactNode }) {
  const [store] = useState(createRunRequestStore);
  return <RunRequestsContext.Provider value={store}>{children}</RunRequestsContext.Provider>;
}

/** The bus itself: `request(id)` for a command the shell has switched to. */
export function useRunRequests(): RunRequestBus {
  const store = useContext(RunRequestsContext);
  if (!store) throw new Error('useRunRequests must be used inside <RunRequestsProvider>');
  return store;
}

/**
 * Fire `fn` when the nonce for `id` changes after mount, or once on mount if a
 * request arrived while this view was not yet mounted (the switch-then-request
 * ordering). Never fires on mount otherwise.
 *
 * Degrades to a no-op when the provider is absent: view components are unit
 * tested in isolation (ApiProvider + ProjectProvider + SelectionProvider, no
 * shell), and the run-request wiring is only meaningful inside the shell. The
 * dedicated tests in runRequests.test.tsx exercise the real behaviour.
 */
export function useRunRequest(id: string, fn: () => void): void {
  const store = useContext(RunRequestsContext);

  const fnRef = useRef(fn);
  fnRef.current = fn;
  const lastNonce = useRef(store ? store.getNonce(id) : 0);

  useEffect(() => {
    if (!store) return;
    // Drain a request that raced mount: the shell switched the view and bumped
    // the nonce in the same tick, so by the time this view mounted the request
    // had already been made and no further notification is coming.
    if (store.consumePending(id)) {
      lastNonce.current = store.getNonce(id);
      fnRef.current();
    }
    const unsubscribe = store.subscribe(() => {
      const nonce = store.getNonce(id);
      if (nonce !== lastNonce.current) {
        lastNonce.current = nonce;
        store.consumePending(id);
        fnRef.current();
      }
    });
    return unsubscribe;
  }, [store, id]);
}
