/**
 * The palette's actual behaviour — not its absence. Each test asserts that
 * commands render, filter and run, so a palette that renders nothing fails
 * every one of these.
 */

import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { CommandPalette } from './CommandPalette';

function renderPalette() {
  const onRun = vi.fn();
  const onClose = vi.fn();
  render(<CommandPalette open onClose={onClose} onRun={onRun} />);
  return { onRun, onClose };
}

describe('CommandPalette', () => {
  it('lists commands from the registry when opened with no query', () => {
    renderPalette();
    expect(screen.getByText('Build')).toBeInTheDocument();
    expect(screen.getByText('Open project…')).toBeInTheDocument();
  });

  it('filters as you type and runs the selected command on Enter', () => {
    const { onRun, onClose } = renderPalette();
    const input = screen.getByTestId('palette-input');
    fireEvent.change(input, { target: { value: 'build' } });

    // The query reduced the list — "Open project…" is gone, "Build" remains.
    expect(screen.getByText('Build')).toBeInTheDocument();
    expect(screen.queryByText('Open project…')).toBeNull();

    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onRun).toHaveBeenCalledWith('run.build');
    expect(onClose).toHaveBeenCalled();
  });

  it('closes on Escape', () => {
    const { onClose } = renderPalette();
    fireEvent.keyDown(screen.getByTestId('palette-input'), { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });

  it('reports the empty state honestly for a query that matches nothing', () => {
    renderPalette();
    fireEvent.change(screen.getByTestId('palette-input'), { target: { value: 'zzzzqqqq' } });
    expect(screen.getByTestId('palette-empty')).toBeInTheDocument();
    expect(screen.queryByText('Build')).toBeNull();
  });

  it('navigates with the arrow keys and runs the moved-to command', () => {
    const { onRun } = renderPalette();
    const input = screen.getByTestId('palette-input');
    fireEvent.change(input, { target: { value: 'schematic' } });
    // A single match: Down stays on it, Enter runs it.
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onRun).toHaveBeenCalledWith('view.schematic');
  });
});
