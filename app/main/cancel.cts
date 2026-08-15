/**
 * In-flight child-process bookkeeping, keyed by the caller's token (§16.1).
 *
 * `cancel(token)` must really kill the process *and* ensure the corresponding
 * call never resolves into the renderer. A stale result arriving after a newer
 * edit is a correctness bug, not a performance issue. The registry is pure and
 * dependency-free so its bookkeeping can be unit-tested.
 */

export interface ChildLike {
  kill(signal?: string): boolean;
}

export class CancelledError extends Error {
  readonly token: string;
  constructor(token: string) {
    super(`cancelled: ${token}`);
    this.name = 'CancelledError';
    this.token = token;
  }
}

export interface InFlightEntry {
  token: string;
  child: ChildLike | null;
  /** Settle the caller's promise (reject) without delivering a result. */
  cancel: () => void;
}

export class CancelRegistry {
  private entries = new Map<string, InFlightEntry>();

  add(entry: InFlightEntry): void {
    this.entries.set(entry.token, entry);
  }

  has(token: string): boolean {
    return this.entries.has(token);
  }

  get(token: string): InFlightEntry | undefined {
    return this.entries.get(token);
  }

  delete(token: string): boolean {
    return this.entries.delete(token);
  }

  get size(): number {
    return this.entries.size;
  }

  tokens(): string[] {
    return [...this.entries.keys()];
  }

  /**
   * Cancel one in-flight call: remove it from the registry, reject its promise
   * (so it never resolves into the renderer) and kill its process. Returns
   * false when the token is unknown or already settled.
   */
  cancel(token: string): boolean {
    const entry = this.entries.get(token);
    if (entry === undefined) return false;
    this.entries.delete(token);
    entry.cancel();
    if (entry.child !== null) {
      try {
        entry.child.kill('SIGKILL');
      } catch {
        // The process may already be gone; the promise is settled either way.
      }
    }
    return true;
  }

  cancelAll(): void {
    for (const token of this.tokens()) this.cancel(token);
  }
}
