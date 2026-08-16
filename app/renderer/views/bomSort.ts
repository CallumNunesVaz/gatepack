/**
 * BOM column sorting (§C13). Pure re-ordering of the rows the core already
 * produced — it never recomputes a value, only chooses an order to show them
 * in. Kept pure so the ordering rules are testable without a render.
 */

import type { BomLine } from '../../shared/api';

export type BomSortKey =
  | 'partNumber'
  | 'quantity'
  | 'package'
  | 'refdes'
  | 'manufacturers'
  | 'gatesPerPackage';

export type SortDir = 'asc' | 'desc';

const ACCESSOR: Record<BomSortKey, (line: BomLine) => string | number> = {
  partNumber: (l) => l.partNumber,
  quantity: (l) => l.quantity,
  package: (l) => l.package,
  refdes: (l) => l.refdes.join(' '),
  manufacturers: (l) => l.manufacturers.join('; '),
  gatesPerPackage: (l) => l.gatesPerPackage,
};

export function sortBomLines(lines: BomLine[], key: BomSortKey, dir: SortDir): BomLine[] {
  const factor = dir === 'asc' ? 1 : -1;
  return [...lines].sort((a, b) => {
    const av = ACCESSOR[key](a);
    const bv = ACCESSOR[key](b);
    if (typeof av === 'number' && typeof bv === 'number') {
      return (av - bv) * factor;
    }
    return String(av).localeCompare(String(bv)) * factor;
  });
}

/** The next direction when a column header is clicked: asc -> desc -> asc. */
export function nextDir(current: SortDir): SortDir {
  return current === 'asc' ? 'desc' : 'asc';
}
