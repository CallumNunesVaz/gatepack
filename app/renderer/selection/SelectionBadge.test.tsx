import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import { SelectionBadge } from './SelectionBadge';

describe('SelectionBadge', () => {
  it('renders "no exact link" for a link-less construct', () => {
    const { container } = render(<SelectionBadge confidence="none" />);
    expect(container.querySelector('[data-confidence="none"]')?.textContent).toBe('no exact link');
  });

  it('renders "inferred" distinctly from "exact"', () => {
    const inferred = render(<SelectionBadge confidence="inferred" />);
    const exact = render(<SelectionBadge confidence="exact" />);
    expect(inferred.container.querySelector('[data-confidence="inferred"]')?.textContent).toBe('inferred');
    expect(exact.container.querySelector('[data-confidence="exact"]')?.textContent).toBe('exact');
    expect(inferred.container.querySelector('[data-confidence="exact"]')).toBeNull();
  });
});
