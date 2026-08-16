/**
 * The dispatch seam: a command id reaches its registered handler, an
 * unregistered id is reported (never dropped silently), and unregister works.
 */

import { describe, expect, it, vi } from 'vitest';
import { createCommandBus } from './commands';

describe('createCommandBus', () => {
  it('dispatches a command id to its registered handler', () => {
    const handler = vi.fn();
    const bus = createCommandBus();
    bus.register('run.build', handler);
    expect(bus.isRegistered('run.build')).toBe(true);
    expect(bus.dispatch('run.build')).toBe(true);
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it('reports an unregistered id rather than failing silently', () => {
    const onUnhandled = vi.fn();
    const bus = createCommandBus(onUnhandled);
    expect(bus.dispatch('run.build')).toBe(false);
    expect(onUnhandled).toHaveBeenCalledWith('run.build');
  });

  it('unregisters a handler so it no longer fires', () => {
    const handler = vi.fn();
    const bus = createCommandBus();
    const unregister = bus.register('run.build', handler);
    unregister();
    expect(bus.isRegistered('run.build')).toBe(false);
    expect(bus.dispatch('run.build')).toBe(false);
    expect(handler).not.toHaveBeenCalled();
  });
});
