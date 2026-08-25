/**
 * Session-scoped verification evidence.
 *
 * `verify` writes nothing to disk. After a restart, a verified design is
 * indistinguishable from an unverified one, so the ONLY thing that can evidence
 * a verification is a run *in this session, for the current revision*. This
 * module holds exactly that and nothing more. The strip must never paint Verify
 * as done from disk state (`hasMappedNetlist`), and must not invent a manifest
 * file to make it easier — report the state that can be evidenced.
 */

import { useEffect, useState } from 'react';

type Listener = () => void;

let verifyRevision: number | null = null;
const revisionListeners = new Set<Listener>();

export function getVerifyRevision(): number | null {
  return verifyRevision;
}

/** Record that a verification ran in this session at `revision`. */
export function setVerifyRevision(revision: number): void {
  if (revision === verifyRevision) return;
  verifyRevision = revision;
  for (const listener of revisionListeners) listener();
}

export function subscribeVerifyRevision(listener: Listener): () => void {
  revisionListeners.add(listener);
  return () => {
    revisionListeners.delete(listener);
  };
}

let running = false;
const runningListeners = new Set<Listener>();

export function setVerifyRunning(next: boolean): void {
  if (next === running) return;
  running = next;
  for (const listener of runningListeners) listener();
}

export function getVerifyRunning(): boolean {
  return running;
}

export function subscribeVerifyRunning(listener: Listener): () => void {
  runningListeners.add(listener);
  return () => {
    runningListeners.delete(listener);
  };
}

export function useVerifyRevision(): number | null {
  const [value, setValue] = useState(getVerifyRevision);
  useEffect(() => subscribeVerifyRevision(() => setValue(getVerifyRevision())), []);
  return value;
}

export function useVerifyRunning(): boolean {
  const [value, setValue] = useState(getVerifyRunning);
  useEffect(() => subscribeVerifyRunning(() => setValue(getVerifyRunning())), []);
  return value;
}

/** Reset the module state between tests. */
export function resetVerifySession(): void {
  verifyRevision = null;
  running = false;
}
