/**
 * Palette/shortcut presentation order and labels for the command groups.
 * Shared by the palette and the shortcuts sheet so the two can never disagree
 * about how a group is named or ordered.
 */

import type { CommandGroup } from '../keys/registry';

export const GROUP_ORDER: CommandGroup[] = ['view', 'project', 'run', 'inspect', 'selection', 'app'];

export const GROUP_LABELS: Record<CommandGroup, string> = {
  view: 'View',
  project: 'Project',
  run: 'Run',
  inspect: 'Inspect',
  selection: 'Selection',
  app: 'Application',
};
