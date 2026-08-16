/**
 * A cheap, single-shot task for panels that read a core artefact on open.
 *
 * `useRevisionedTask` is for commands whose result is tied to the document
 * revision (build/verify/analyse); these inspector panels read build
 * artefacts and the toolchain, which are not revisioned the same way, so they
 * get a lighter task with the same four visible states: idle, loading,
 * success, error — plus a `run()` for the manual refresh button.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import type { Diagnostic, Envelope } from '../../shared/api';

export type PanelTaskStatus = 'idle' | 'loading' | 'success' | 'error';

export interface PanelTaskState<T> {
  status: PanelTaskStatus;
  data: T | null;
  error: Diagnostic | null;
}

export function usePanelTask<T>(start: () => Promise<Envelope<T>>, autoRun = false) {
  const [state, setState] = useState<PanelTaskState<T>>({
    status: 'idle',
    data: null,
    error: null,
  });
  const seqRef = useRef(0);
  const startedRef = useRef(false);

  const run = useCallback(() => {
    const seq = ++seqRef.current;
    setState({ status: 'loading', data: null, error: null });
    start()
      .then((env) => {
        if (seqRef.current !== seq) return;
        if (env.ok) {
          setState({ status: 'success', data: env.data, error: null });
        } else {
          setState({ status: 'error', data: null, error: env.error });
        }
      })
      .catch((e: unknown) => {
        if (seqRef.current !== seq) return;
        setState({
          status: 'error',
          data: null,
          error: {
            severity: 'error',
            code: 'UI0000',
            message: e instanceof Error ? e.message : String(e),
          },
        });
      });
  }, [start]);

  useEffect(() => {
    if (!autoRun || startedRef.current) return;
    startedRef.current = true;
    run();
  }, [autoRun, run]);

  return { state, run };
}
