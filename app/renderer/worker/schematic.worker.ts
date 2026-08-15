/**
 * Schematic layout worker: runs netlistsvg + elkjs off the UI thread. Consumes a
 * `write_json` netlist and posts back the rendered SVG string.
 */

import { renderSchematic } from './renderSchematic';

interface WorkerMessage {
  id: string;
  netlist: unknown;
}

interface WorkerResult {
  id: string;
  svg?: string;
  error?: string;
}

const scope = self as unknown as {
  onmessage: ((event: MessageEvent<WorkerMessage>) => void) | null;
  postMessage: (message: WorkerResult) => void;
};

scope.onmessage = (event: MessageEvent<WorkerMessage>) => {
  const { id, netlist } = event.data;
  renderSchematic(netlist)
    .then((svg) => scope.postMessage({ id, svg }))
    .catch((err: unknown) =>
      scope.postMessage({ id, error: err instanceof Error ? err.message : String(err) }),
    );
};
