/**
 * The §15.2 selection bus. One selection state is shared by every view: a view
 * that knows how to *emit* a selection calls `setSelection`, and a view that
 * knows how to *reflect* it calls `useHighlights` with its own `LinkContext`
 * (or reads the selection directly). The pure mapping lives in `./map.ts` so it
 * is testable without a render cycle.
 */

import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';
import { resolveSelection } from './map';
import { EMPTY_HIGHLIGHTS, type HighlightSet, type LinkContext, type Selection } from './types';

export interface SelectionBus {
  selection: Selection | null;
  setSelection: (selection: Selection | null) => void;
}

const SelectionContext = createContext<SelectionBus | null>(null);

export function SelectionProvider({ children }: { children: ReactNode }) {
  const [selection, setSelection] = useState<Selection | null>(null);
  const value = useMemo(() => ({ selection, setSelection }), [selection]);
  return <SelectionContext.Provider value={value}>{children}</SelectionContext.Provider>;
}

export function useSelection(): SelectionBus {
  const bus = useContext(SelectionContext);
  if (!bus) throw new Error('useSelection must be used inside <SelectionProvider>');
  return bus;
}

/** Resolve the current selection against a link context, or empty when none. */
export function useHighlights(ctx: LinkContext | null): HighlightSet {
  const { selection } = useSelection();
  return useMemo(
    () => (selection && ctx ? resolveSelection(selection, ctx) : EMPTY_HIGHLIGHTS),
    [selection, ctx],
  );
}
