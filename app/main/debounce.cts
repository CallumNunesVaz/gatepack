/**
 * Debounce (250 ms default). File-system events arrive in bursts; the watcher
 * collapses them and emits a single `onFileChanged` per burst. Keeps a `flush`
 * (for shutdown) and a `cancel` (for closing a project) handle.
 */

export interface Debounced<A extends unknown[]> {
  (...args: A): void;
  /** Fire any pending invocation now and clear the timer. */
  flush(): void;
  /** Drop any pending invocation without firing it. */
  cancel(): void;
}

export function debounce<A extends unknown[]>(
  fn: (...args: A) => void,
  ms: number,
): Debounced<A> {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let lastArgs: A | null = null;

  const invoke = () => {
    const args = lastArgs;
    timer = null;
    lastArgs = null;
    if (args !== null) fn(...args);
  };

  const debounced = ((...args: A) => {
    lastArgs = args;
    if (timer !== null) clearTimeout(timer);
    timer = setTimeout(invoke, ms);
  }) as Debounced<A>;

  debounced.flush = () => {
    if (timer !== null) {
      clearTimeout(timer);
      invoke();
    }
  };

  debounced.cancel = () => {
    if (timer !== null) clearTimeout(timer);
    timer = null;
    lastArgs = null;
  };

  return debounced;
}
