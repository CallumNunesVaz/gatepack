/**
 * Thin client over the authoritative IPC bridge (`window.gatepack`).
 *
 * `window.gatepack` does not exist in this worktree (another agent owns
 * `app/main/` and `app/preload/`), so every caller goes through this module.
 * Tests inject a fake via `setApi`; the real bridge is used only when present.
 */

import type { GatepackApi } from '../shared/api';

let injected: GatepackApi | null = null;

export function setApi(api: GatepackApi | null): void {
  injected = api;
}

function readWindowApi(): GatepackApi | null {
  if (typeof window === 'undefined') return null;
  const candidate = (window as unknown as { gatepack?: GatepackApi }).gatepack;
  return candidate ?? null;
}

export function getApi(): GatepackApi {
  if (injected) return injected;
  const real = readWindowApi();
  if (real) return real;
  throw new Error('gatepack bridge is not available (window.gatepack missing)');
}

export function hasApi(): boolean {
  return injected !== null || readWindowApi() !== null;
}

/** A fresh, unique cancellation token for an in-flight core call (§16.1). */
let tokenCounter = 0;
export function nextToken(): string {
  tokenCounter += 1;
  return `tok-${tokenCounter}`;
}
