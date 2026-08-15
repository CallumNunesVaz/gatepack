/**
 * netlistsvg + elkjs schematic rendering, isolated so it is testable without a
 * Worker. netlistsvg consumes Yosys `write_json` directly and produces IEEE gate
 * symbols with orthogonal routing; elkjs (used internally by netlistsvg) runs
 * the layout. This module is imported by the web worker so the layout never
 * blocks the UI thread.
 */

import netlistsvg from 'netlistsvg';
import skin from 'netlistsvg/lib/default.svg?raw';

export async function renderSchematic(netlist: unknown): Promise<string> {
  return netlistsvg.render(skin, netlist);
}
