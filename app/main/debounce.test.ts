import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { debounce } from './debounce.cjs';

describe('debounce', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('collapses a burst into a single call', () => {
    const fn = vi.fn<(s: string) => void>();
    const d = debounce<[string]>((s) => fn(s), 250);
    d('a');
    d('b');
    d('c');
    expect(fn).not.toHaveBeenCalled();
    vi.advanceTimersByTime(250);
    expect(fn).toHaveBeenCalledTimes(1);
    expect(fn).toHaveBeenCalledWith('c');
  });

  it('delays the first call by the full window', () => {
    const fn = vi.fn<(s: string) => void>();
    const d = debounce<[string]>((s) => fn(s), 250);
    d('a');
    vi.advanceTimersByTime(249);
    expect(fn).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it('flush fires the pending invocation immediately', () => {
    const fn = vi.fn<(s: string) => void>();
    const d = debounce<[string]>((s) => fn(s), 250);
    d('a');
    d.flush();
    expect(fn).toHaveBeenCalledWith('a');
    vi.advanceTimersByTime(250);
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it('cancel drops the pending invocation', () => {
    const fn = vi.fn<(s: string) => void>();
    const d = debounce<[string]>((s) => fn(s), 250);
    d('a');
    d.cancel();
    vi.advanceTimersByTime(250);
    expect(fn).not.toHaveBeenCalled();
  });
});
