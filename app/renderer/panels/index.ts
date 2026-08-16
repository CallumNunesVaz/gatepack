/**
 * The inspector/utility panels for the CLI-parity package.
 *
 * Each entry maps a command id from `keys/registry.ts` to its component, so
 * the shell's palette/dispatcher can reach it without a second lookup:
 *
 *   inspect.doctor         -> ToolchainStatusPanel
 *   inspect.provenance     -> ProvenancePanel
 *   inspect.mappedNetlist  -> MappedNetlistPanel
 *   inspect.packedNetlist  -> PackedNetlistPanel
 *   inspect.library        -> LibraryPanel
 *   project.examples       -> ExamplesPanel
 *
 * `PANEL_COMMANDS` is the single source of truth the shell's `PanelHost` uses
 * to register a handler for each command and to decide which component to
 * mount. The registry test (`keys/registry.test.ts`) reads the same table, so
 * a command entry with no handler mapping — or a handler mapping with no
 * command entry — fails the suite rather than silently dispatching to nothing.
 */

import type { ComponentType } from 'react';
import { ToolchainStatusPanel } from './ToolchainStatusPanel';
import { ProvenancePanel } from './ProvenancePanel';
import { MappedNetlistPanel } from './MappedNetlistPanel';
import { PackedNetlistPanel } from './PackedNetlistPanel';
import { LibraryPanel } from './LibraryPanel';
import { ExamplesPanel } from './ExamplesPanel';

export {
  ToolchainStatusPanel,
  ProvenancePanel,
  MappedNetlistPanel,
  PackedNetlistPanel,
  LibraryPanel,
  ExamplesPanel,
};

export interface PanelCommand {
  id: string;
  title: string;
  component: ComponentType;
}

export const PANEL_COMMANDS: PanelCommand[] = [
  { id: 'inspect.doctor', title: 'Toolchain status', component: ToolchainStatusPanel },
  { id: 'inspect.provenance', title: 'Provenance map', component: ProvenancePanel },
  { id: 'inspect.mappedNetlist', title: 'Mapped netlist', component: MappedNetlistPanel },
  { id: 'inspect.packedNetlist', title: 'Packed netlist', component: PackedNetlistPanel },
  { id: 'inspect.library', title: 'Part library', component: LibraryPanel },
  { id: 'project.examples', title: 'Bundled examples', component: ExamplesPanel },
];

export function panelCommandById(id: string): PanelCommand | undefined {
  return PANEL_COMMANDS.find((p) => p.id === id);
}

export {
  getDoctorReport,
  setDoctorReport,
  subscribeDoctorReport,
} from './doctorStore';
