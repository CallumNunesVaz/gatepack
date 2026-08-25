/**
 * The live build state — `buildState()` from the bridge, kept current.
 *
 * `buildState()` reports existence, not freshness (§16.1). This module adds the
 * two things that make it live *without* conflating the two:
 *
 *   - a reload signal (mirroring `selection/linkData.ts`) that every site which
 *     runs `api.build()` fires when the build finishes, so a strip or view that
 *     fetched once on mount is not stale for the rest of the session; and
 *   - a session record of the revision the artefacts were built/observed at, so
 *     a build older than the spec can be reported as `stale` by the strip.
 *
 * The fetch re-runs on mount, on project revision change, and on the reload
 * signal. One missed call site means the strip lies for the rest of the
 * session, so there is a test that reaches each notify and watches it fail when
 * it is deleted.
 */

import { useEffect, useState } from 'react';
import type { BuildState, Diagnostic } from '../../shared/api';
import { useApi } from '../bridge/context';

type Listener = () => void;

/* --- reload signal ---------------------------------------------------- */

let reloads = 0;
const reloadListeners = new Set<Listener>();

/** Ask every `buildState()` reader to re-fetch (a build has just finished). */
export function requestBuildStateReload(): void {
  reloads += 1;
  for (const listener of reloadListeners) listener();
}

export function getBuildStateReloadCount(): number {
  return reloads;
}

export function subscribeBuildStateReload(listener: Listener): () => void {
  reloadListeners.add(listener);
  return () => {
    reloadListeners.delete(listener);
  };
}

/* --- running signal --------------------------------------------------- */

let running = false;
const runningListeners = new Set<Listener>();

/** Publish that a build is in flight (the strip's `running` state). */
export function setBuildRunning(next: boolean): void {
  if (next === running) return;
  running = next;
  for (const listener of runningListeners) listener();
}

export function getBuildRunning(): boolean {
  return running;
}

export function subscribeBuildRunning(listener: Listener): () => void {
  runningListeners.add(listener);
  return () => {
    runningListeners.delete(listener);
  };
}

/* --- build revision --------------------------------------------------- */

let buildRevision: number | null = null;
const revisionListeners = new Set<Listener>();

export function setBuildRevision(next: number): void {
  if (next === buildRevision) return;
  buildRevision = next;
  for (const listener of revisionListeners) listener();
}

export function getBuildRevision(): number | null {
  return buildRevision;
}

export function subscribeBuildRevision(listener: Listener): () => void {
  revisionListeners.add(listener);
  return () => {
    revisionListeners.delete(listener);
  };
}

/* --- the hook --------------------------------------------------------- */

export interface LiveBuildState {
  state: BuildState | null;
  loading: boolean;
  error: Diagnostic | null;
}

export function useBuildState(revision: number): LiveBuildState {
  const api = useApi();
  const [state, setState] = useState<BuildState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Diagnostic | null>(null);
  const [reload, setReload] = useState(getBuildStateReloadCount);

  useEffect(() => subscribeBuildStateReload(() => setReload(getBuildStateReloadCount())), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api.buildState().then((env) => {
      if (cancelled) return;
      setLoading(false);
      if (env.ok) {
        setState(env.data);
        setError(null);
        // The artefacts predate this session, so we cannot know which revision
        // they were built for. Observe them as current *now*; the moment the
        // spec moves on, `buildRevision !== revision` and the strip reports
        // `stale`. Mirror `Schematic`'s `builtAt = revision` on fetch.
        if (env.data.hasMappedNetlist && getBuildRevision() === null) {
          setBuildRevision(revision);
        }
      } else {
        setError(env.error);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [api, reload, revision]);

  return { state, loading, error };
}

export function useBuildRunning(): boolean {
  const [value, setValue] = useState(getBuildRunning);
  useEffect(() => subscribeBuildRunning(() => setValue(getBuildRunning())), []);
  return value;
}

export function useBuildRevision(): number | null {
  const [value, setValue] = useState(getBuildRevision);
  useEffect(() => subscribeBuildRevision(() => setValue(getBuildRevision())), []);
  return value;
}

/** Reset the module state between tests (and on a project close, conceptually). */
export function resetBuildState(): void {
  reloads = 0;
  running = false;
  buildRevision = null;
}
