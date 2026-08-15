import { describe, expect, it, vi } from 'vitest';

import { CancelRegistry, CancelledError, type ChildLike } from './cancel.cjs';

describe('CancelRegistry', () => {
  it('tracks entries by token', () => {
    const registry = new CancelRegistry();
    registry.add({ token: 't1', child: null, cancel: () => {} });
    expect(registry.has('t1')).toBe(true);
    expect(registry.size).toBe(1);
  });

  it('cancel rejects the promise and kills the process', () => {
    const registry = new CancelRegistry();
    const kill = vi.fn(() => true);
    const child: ChildLike = { kill };
    let cancelled = false;
    registry.add({ token: 't1', child, cancel: () => (cancelled = true) });

    expect(registry.cancel('t1')).toBe(true);
    expect(cancelled).toBe(true);
    expect(kill).toHaveBeenCalledWith('SIGKILL');
    expect(registry.has('t1')).toBe(false);
  });

  it('cancel of an unknown token returns false', () => {
    const registry = new CancelRegistry();
    expect(registry.cancel('nope')).toBe(false);
  });

  it('cancelAll clears every entry', () => {
    const registry = new CancelRegistry();
    registry.add({ token: 'a', child: null, cancel: () => {} });
    registry.add({ token: 'b', child: null, cancel: () => {} });
    registry.cancelAll();
    expect(registry.size).toBe(0);
  });

  it('CancelledError carries its token', () => {
    const err = new CancelledError('tok');
    expect(err.name).toBe('CancelledError');
    expect(err.token).toBe('tok');
    expect(err.message).toContain('tok');
  });
});
