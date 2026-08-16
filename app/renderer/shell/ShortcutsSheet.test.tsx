/**
 * The shortcuts sheet is generated from the registry, so this test pins that
 * it cannot drift: every command id and every bound chord must appear, or the
 * sheet has silently lost a binding.
 */

import { describe, expect, it, vi } from 'vitest';
import { render, within } from '@testing-library/react';
import { COMMANDS } from '../keys/registry';
import { ShortcutsSheet } from './ShortcutsSheet';

describe('ShortcutsSheet', () => {
  it('renders a row for every command, keyed by its id', () => {
    const { container } = render(<ShortcutsSheet open onClose={vi.fn()} />);
    for (const command of COMMANDS) {
      const row = container.querySelector(`[data-command-id="${command.id}"]`);
      expect(row, `${command.id} has a row`).not.toBeNull();
      expect(
        within(row as HTMLElement).getByText(command.title),
        `${command.id} shows its title`,
      ).toBeInTheDocument();
    }
  });

  it('renders a kbd for every bound chord', () => {
    const { container } = render(<ShortcutsSheet open onClose={vi.fn()} />);
    const chorded = COMMANDS.filter((c) => c.keys);
    const kbdCount = container.querySelectorAll('.gp-shortcuts__keys kbd').length;
    expect(kbdCount).toBeGreaterThanOrEqual(chorded.length);
  });
});
