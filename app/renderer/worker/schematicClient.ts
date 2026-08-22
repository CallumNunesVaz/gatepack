/**
 * Entry point for schematic layout.
 *
 * This *was* a web worker, so netlistsvg + elkjs would lay out off the UI
 * thread. It cannot be, and the reason is worth recording so nobody restores it
 * and gets the same silent failure:
 *
 *   elkjs's default "fake worker" is `lib/elk-worker.min.js`, whose last line
 *   is `if (typeof document === 'undefined' && typeof self !== 'undefined')
 *   { self.onmessage = … } else if (module.exports) { module.exports = {
 *   Worker: … } }`. Inside a real Web Worker the first branch wins: the module
 *   decides it *is* the elk worker, never assigns its exports, and — worse —
 *   installs its own `self.onmessage`, which would replace ours. `new ELK()`
 *   then reads `require('./elk-worker.min.js').Worker` as `undefined` and
 *   throws `is not a constructor` during module evaluation, so the worker died
 *   on load and the view reported "schematic worker failed".
 *
 * Rendering in-process is the honest answer: on the main thread `document`
 * exists, elk's module takes the export branch, and the layout runs. It is a
 * real layout by the real library either way — the cost is that a very large
 * netlist blocks the UI for the duration of its layout rather than running
 * beside it.
 *
 * The import stays lazy so netlistsvg and elkjs (~1.5 MB) are fetched only when
 * the schematic view is first opened, which was the other reason for the split.
 */

import type { SchematicRender } from './renderSchematic';

export function renderSchematicAsync(netlist: unknown): Promise<SchematicRender> {
  return import('./renderSchematic').then((m) => m.renderSchematic(netlist));
}
