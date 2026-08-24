/**
 * A tiny module-scoped store for the one piece of link data that is NOT fetched
 * by `useLinkContext` itself: the `verify()` result.
 *
 * `provenance()`, `mappedNetlist()`, `simulate()` and `packedNetlist()` are
 * cheap reads the link context can fetch on mount. `verify()` runs sby — a
 * multi-second child process that must only run when the user asks, and must be
 * cancellable against the document revision. The VerificationPanel owns that
 * (through `useRevisionedTask`); this store is how it *publishes* the result to
 * the selection spine without a provider wrapper (App.tsx is out of scope for
 * M16), so a property selection resolves against the same verified result the
 * panel just showed.
 */

import type { VerifyResult } from '../../shared/api';

type Listener = () => void;

let verify: VerifyResult | null = null;
const listeners = new Set<Listener>();

export function getVerifyResult(): VerifyResult | null {
  return verify;
}

export function setVerifyResult(next: VerifyResult | null): void {
  verify = next;
  for (const listener of listeners) listener();
}

export function subscribeVerifyResult(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/**
 * A reload signal for the four artefacts `useLinkContext` reads on mount.
 *
 * They are fetched once, from whatever the last `build` left on disk, and there
 * was no way to ask for them again. That made `run.simulate` unimplementable:
 * the truth table's divergence column comes from `simulate()` through this
 * spine, not from a revisioned task, so "Simulate truth table" had nothing to
 * trigger. Wiring it to the truth table's *other* task (the `estimate`-backed
 * cover preview) would have made the command report success having run
 * something else.
 *
 * The signal is deliberately not per-artefact: all four are cheap file reads
 * describing the same build, and a caller that wants a fresh `simulate()` has
 * no reason to want a stale `packedNetlist()` beside it.
 */
let reloads = 0;
const reloadListeners = new Set<Listener>();

export function getLinkReloadCount(): number {
  return reloads;
}

export function requestLinkReload(): void {
  reloads += 1;
  for (const listener of reloadListeners) listener();
}

export function subscribeLinkReload(listener: Listener): () => void {
  reloadListeners.add(listener);
  return () => {
    reloadListeners.delete(listener);
  };
}
