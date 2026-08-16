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
