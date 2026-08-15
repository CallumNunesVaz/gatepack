/**
 * FSM graph node positions live in a gitignored sidecar (`design.layout.json`),
 * never in `design.yaml` (§10.3). The IPC contract exposes no way to read/write
 * arbitrary project files, so the renderer persists positions through an
 * injectable store; the browser default is `localStorage`, keyed by project
 * path. Positions are cosmetic and are *never* passed to the document editor.
 */

export interface NodePosition {
  x: number;
  y: number;
}

export type LayoutMap = Record<string, NodePosition>;

export interface LayoutStore {
  load(): LayoutMap;
  save(map: LayoutMap): void;
}

export function storageKey(projectPath: string): string {
  return `gatepack.layout:${projectPath}`;
}

export function createLocalStorageLayoutStore(projectPath: string): LayoutStore {
  const key = storageKey(projectPath);
  return {
    load(): LayoutMap {
      try {
        if (typeof localStorage === 'undefined') return {};
        const raw = localStorage.getItem(key);
        if (!raw) return {};
        const parsed: unknown = JSON.parse(raw);
        if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return {};
        const out: LayoutMap = {};
        for (const [k, v] of Object.entries(parsed)) {
          if (
            typeof v === 'object' && v !== null &&
            typeof (v as { x?: unknown }).x === 'number' &&
            typeof (v as { y?: unknown }).y === 'number'
          ) {
            out[k] = { x: (v as { x: number }).x, y: (v as { y: number }).y };
          }
        }
        return out;
      } catch {
        return {};
      }
    },
    save(map: LayoutMap): void {
      try {
        if (typeof localStorage === 'undefined') return;
        localStorage.setItem(key, JSON.stringify(map));
      } catch {
        // storage full/unavailable — positions are cosmetic, ignore.
      }
    },
  };
}

export function createMemoryLayoutStore(): LayoutStore & { map: LayoutMap } {
  const store = { map: {} as LayoutMap };
  return {
    map: store.map,
    load(): LayoutMap {
      return { ...store.map };
    },
    save(map: LayoutMap): void {
      store.map = { ...map };
    },
  };
}
