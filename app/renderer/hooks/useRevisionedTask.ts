/**
 * A core call whose result is tied to the document revision it was computed
 * against. The moment the document changes:
 *
 *   - any in-flight call is cancelled via `cancel(token)` (§16.1);
 *   - any already-arrived result is flagged stale (`isStale`).
 *
 * Formal verification takes seconds, not milliseconds: a stale result against
 * edited source is a correctness bug, so the UI must never present one as live.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import type { Diagnostic, Envelope } from '../../shared/api';
import { nextToken } from '../api';
import { useApi } from '../bridge/context';

/**
 * The shared in-flight token registry (§16.1).
 *
 * `useRevisionedTask` cancels its own token on re-run and unmount, but nothing
 * else could reach that token — `run.cancel` (Escape) had no way to cancel the
 * task the active view is running. This registry is the seam: the hook
 * registers its token while a call is in flight and clears it on completion,
 * and `run.cancel` cancels every registered token. One task is normally in
 * flight; cancelling all of them is correct and simpler than tracking which
 * view is active.
 */
const inflightTokens = new Set<string>();

export function registerInflightToken(token: string): void {
  inflightTokens.add(token);
}

export function deregisterInflightToken(token: string): void {
  inflightTokens.delete(token);
}

export function inflightTokensSnapshot(): string[] {
  return [...inflightTokens];
}

export interface TaskState<T> {
  status: 'idle' | 'running' | 'success' | 'error';
  data: T | null;
  error: Diagnostic | null;
  revision: number | null;
}

export function useRevisionedTask<T>(
  revision: number,
  start: (token: string) => Promise<Envelope<T>>,
) {
  const api = useApi();
  const tokenRef = useRef<string | null>(null);
  const [state, setState] = useState<TaskState<T>>({
    status: 'idle',
    data: null,
    error: null,
    revision: null,
  });

  const run = useCallback(() => {
    const token = nextToken();
    const previous = tokenRef.current;
    if (previous) {
      api.cancel(previous);
      deregisterInflightToken(previous);
    }
    tokenRef.current = token;
    registerInflightToken(token);
    setState({ status: 'running', data: null, error: null, revision });
    start(token)
      .then((env) => {
        if (tokenRef.current !== token) return; // superseded or cancelled
        if (env.ok) {
          setState({ status: 'success', data: env.data, error: null, revision });
        } else {
          setState({ status: 'error', data: null, error: env.error, revision });
        }
      })
      .catch((e: unknown) => {
        if (tokenRef.current !== token) return;
        setState({
          status: 'error',
          data: null,
          error: {
            severity: 'error',
            code: 'UI0000',
            message: e instanceof Error ? e.message : String(e),
          },
          revision,
        });
      })
      .finally(() => {
        if (tokenRef.current === token) {
          deregisterInflightToken(token);
        }
      });
  }, [revision, api, start]);

  useEffect(() => {
    return () => {
      if (tokenRef.current) {
        api.cancel(tokenRef.current);
        deregisterInflightToken(tokenRef.current);
        tokenRef.current = null;
      }
    };
  }, [revision, api]);

  const isStale = state.revision !== null && state.revision !== revision;

  return { state, run, isStale };
}
