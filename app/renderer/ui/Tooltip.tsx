/**
 * Tooltip — hover/focus help that is also reachable from the keyboard.
 *
 * Deliberately not a library: a tooltip is a positioned element plus correct
 * ARIA, and every library that does it also wants to do portals, transitions
 * and a popper engine we do not need.
 *
 * Two rules it enforces, both of which are usually got wrong:
 *
 * 1. It shows on **focus** as well as hover, so a keyboard user can read it.
 * 2. It is `aria-describedby`, never `aria-label` — a tooltip supplements the
 *    control's name, it does not replace it. An IconButton still needs its own
 *    label, because a screen-reader user should not have to trigger a tooltip
 *    to learn what a button does.
 *
 * A tooltip may never be the only place a piece of information exists.
 */

import { useId, useRef, useState, type ReactNode } from 'react';

export type TooltipSide = 'top' | 'bottom' | 'left' | 'right';

export interface TooltipProps {
  /** The tip text. Keep it to one short sentence; longer belongs in the view. */
  content: ReactNode;
  side?: TooltipSide;
  /**
   * Keyboard shortcut shown on the right of the tip, e.g. `['Ctrl', 'B']`.
   * Rendered as <kbd>, so it is visibly a key and not part of the sentence.
   */
  keys?: string[];
  /** Milliseconds before showing on hover. Focus always shows immediately. */
  delay?: number;
  children: ReactNode;
}

export function Tooltip({
  content,
  side = 'bottom',
  keys,
  delay = 300,
  children,
}: TooltipProps) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clear = () => {
    if (timer.current !== null) {
      clearTimeout(timer.current);
      timer.current = null;
    }
  };
  const show = (immediate: boolean) => {
    clear();
    if (immediate || delay <= 0) setOpen(true);
    else timer.current = setTimeout(() => setOpen(true), delay);
  };
  const hide = () => {
    clear();
    setOpen(false);
  };

  return (
    <span
      className="gp-tooltip-anchor"
      onMouseEnter={() => show(false)}
      onMouseLeave={hide}
      onFocusCapture={() => show(true)}
      onBlurCapture={hide}
      // Escape dismisses without moving focus — the tip is not a dialog.
      onKeyDown={(e) => {
        if (e.key === 'Escape' && open) {
          e.stopPropagation();
          hide();
        }
      }}
    >
      <span aria-describedby={open ? id : undefined} className="gp-tooltip-target">
        {children}
      </span>
      {open ? (
        <span role="tooltip" id={id} className={`gp-tooltip gp-tooltip--${side}`}>
          <span className="gp-tooltip__text">{content}</span>
          {keys && keys.length > 0 ? (
            <span className="gp-tooltip__keys">
              {keys.map((k) => (
                <kbd key={k} className="gp-kbd">
                  {k}
                </kbd>
              ))}
            </span>
          ) : null}
        </span>
      ) : null}
    </span>
  );
}
