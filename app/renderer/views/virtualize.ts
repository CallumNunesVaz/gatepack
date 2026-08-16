/**
 * Windowed row rendering for the truth-table grid.
 *
 * A 2^n truth table grows as 2^n; rendering every row for a wide design is the
 * difference between a scroll and a hang. The view therefore renders only the
 * rows in the current scroll window plus a fixed overscan, with two spacer rows
 * reserving the scroll height above and below the window — every visible row is
 * still a real `<tr>`, so sticky headers, zebra striping and the divergence
 * highlight keep working, and column widths stay aligned.
 *
 * Pure so the window arithmetic is testable without a browser; the view feeds it
 * `scrollTop` + `viewportHeight` (both 0 in jsdom, where the fallback is "render
 * everything").
 */

export interface RowWindow {
  /** First rendered row index (inclusive). */
  start: number;
  /** Last rendered row index (exclusive). */
  end: number;
  /** Scroll height reserved above the window, in px. */
  topOffset: number;
  /** Scroll height reserved below the window, in px. */
  bottomOffset: number;
}

export interface WindowInput {
  scrollTop: number;
  viewportHeight: number;
  rowHeight: number;
  totalRows: number;
  overscan?: number;
}

/**
 * Compute the visible row range.
 *
 * When the viewport cannot be measured (height 0 — jsdom, or a container not yet
 * laid out) the entire table is returned so nothing is ever silently hidden.
 */
export function computeRowWindow(input: WindowInput): RowWindow {
  const overscan = input.overscan ?? 5;
  const totalRows = Math.max(0, Math.floor(input.totalRows));
  const rowHeight = input.rowHeight > 0 ? input.rowHeight : 1;
  const viewportHeight = Math.max(0, input.viewportHeight);

  if (totalRows === 0) {
    return { start: 0, end: 0, topOffset: 0, bottomOffset: 0 };
  }

  if (viewportHeight <= 0 || rowHeight <= 0) {
    return { start: 0, end: totalRows, topOffset: 0, bottomOffset: 0 };
  }

  const firstVisible = Math.floor(input.scrollTop / rowHeight);
  const visibleCount = Math.ceil(viewportHeight / rowHeight);

  const start = Math.max(0, firstVisible - overscan);
  const end = Math.min(totalRows, firstVisible + visibleCount + overscan);

  return {
    start,
    end,
    topOffset: start * rowHeight,
    bottomOffset: (totalRows - end) * rowHeight,
  };
}
