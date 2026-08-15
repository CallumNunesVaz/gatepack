/**
 * Thin client for the schematic layout worker. Falls back to an in-process
 * render when a Worker is unavailable (jsdom tests), so the exact same
 * `renderSchematic` seam is exercised either way.
 */

export function renderInWorker(netlist: unknown): Promise<string> {
  try {
    const worker = new Worker(new URL('./schematic.worker.ts', import.meta.url), { type: 'module' });
    return new Promise<string>((resolve, reject) => {
      const id = `sch-${Math.random().toString(36).slice(2)}`;
      worker.onmessage = (event: MessageEvent) => {
        const data = event.data as { id: string; svg?: string; error?: string };
        if (data.id !== id) return;
        worker.terminate();
        if (data.error) reject(new Error(data.error));
        else resolve(data.svg ?? '');
      };
      worker.onerror = (event: ErrorEvent) => {
        worker.terminate();
        reject(event.error ?? new Error('schematic worker failed'));
      };
      worker.postMessage({ id, netlist });
    });
  } catch {
    // Worker unavailable (e.g. jsdom tests) — render in-process, lazily so
    // netlistsvg/elkjs stay out of the main bundle.
    return import('./renderSchematic').then((m) => m.renderSchematic(netlist));
  }
}
