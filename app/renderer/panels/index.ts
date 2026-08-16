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
 */

export { ToolchainStatusPanel } from './ToolchainStatusPanel';
export { ProvenancePanel } from './ProvenancePanel';
export { MappedNetlistPanel } from './MappedNetlistPanel';
export { PackedNetlistPanel } from './PackedNetlistPanel';
export { LibraryPanel } from './LibraryPanel';
export { ExamplesPanel } from './ExamplesPanel';

export {
  getDoctorReport,
  setDoctorReport,
  subscribeDoctorReport,
} from './doctorStore';
