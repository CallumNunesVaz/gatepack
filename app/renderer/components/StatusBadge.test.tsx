import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatusBadge } from './StatusBadge';

describe('StatusBadge — four states, unmistakable', () => {
  it('renders passed distinctly', () => {
    render(<StatusBadge status="passed" />);
    const badge = screen.getByTestId('status-badge');
    expect(badge).toHaveAttribute('data-status', 'passed');
    expect(badge.textContent).toContain('passed');
    expect(screen.queryByTestId('status-bound')).toBeNull();
  });

  it('renders bounded with its bound (never as a plain pass)', () => {
    render(<StatusBadge status="bounded" bound={64} />);
    const badge = screen.getByTestId('status-badge');
    expect(badge).toHaveAttribute('data-status', 'bounded');
    expect(badge.textContent).toContain('bounded');
    expect(screen.getByTestId('status-bound').textContent).toBe('(k = 64)');
    // distinct from a pass
    expect(badge).not.toHaveAttribute('data-status', 'passed');
  });

  it('renders failed distinctly', () => {
    render(<StatusBadge status="failed" />);
    expect(screen.getByTestId('status-badge')).toHaveAttribute('data-status', 'failed');
  });

  it('carries a failed check\'s detail in its tooltip', () => {
    render(<StatusBadge status="failed" detail="ERROR: engine returned 2" />);
    const badge = screen.getByTestId('status-badge');
    expect(badge).toHaveAttribute('data-status', 'failed');
    expect(badge.title).toContain('ERROR: engine returned 2');
  });

  it('renders not_run as a visible state with its reason', () => {
    render(<StatusBadge status="not_run" skippedReason="yosys not installed" />);
    const badge = screen.getByTestId('status-badge');
    expect(badge).toHaveAttribute('data-status', 'not_run');
    expect(badge.textContent).toContain('not run');
    expect(badge.title).toContain('yosys not installed');
    expect(badge).not.toHaveAttribute('data-status', 'passed');
    expect(badge).not.toHaveAttribute('data-status', 'failed');
  });

  it('shows all four states with mutually distinct data-status attributes', () => {
    const { rerender } = render(<StatusBadge status="passed" />);
    const seen = new Set<string>();
    for (const s of ['passed', 'bounded', 'failed', 'not_run'] as const) {
      rerender(<StatusBadge status={s} bound={s === 'bounded' ? 8 : undefined} />);
      seen.add(screen.getByTestId('status-badge').getAttribute('data-status') ?? '');
    }
    expect(seen).toEqual(new Set(['passed', 'bounded', 'failed', 'not_run']));
  });
});
