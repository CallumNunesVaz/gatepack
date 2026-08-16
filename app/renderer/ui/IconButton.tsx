/**
 * IconButton — an icon-only control with an accessible name and a tooltip.
 *
 * `label` is the button's accessible name; `tooltip` (defaulting to `label`) is
 * the supplemental help shown on hover/focus. The tooltip is `aria-describedby`
 * on the *control*, never a substitute for `aria-label` — a screen-reader user
 * must not have to trigger a tooltip to learn what a button does.
 */

import type { ButtonHTMLAttributes } from 'react';
import { Icon, type IconName } from './Icon';
import { Tooltip, type TooltipSide } from './Tooltip';

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  name: IconName;
  /** The accessible name of the button (and the default tooltip). */
  label: string;
  /** Optional tooltip text; defaults to `label`. */
  tooltip?: string;
  /** Shortcut chord shown in the tooltip, e.g. `['Ctrl', '/']`. */
  keys?: string[];
  /** Pressed/selected state, for toggleable rail entries. */
  active?: boolean;
  size?: number;
  tooltipSide?: TooltipSide;
}

export function IconButton({
  name,
  label,
  tooltip,
  keys,
  active = false,
  size = 18,
  tooltipSide = 'bottom',
  className,
  ...rest
}: IconButtonProps) {
  const cls = [
    'gp-icon-button',
    active ? 'gp-icon-button--active' : '',
    className ?? '',
  ]
    .filter(Boolean)
    .join(' ');
  return (
    <Tooltip content={tooltip ?? label} keys={keys} side={tooltipSide}>
      <button
        type="button"
        className={cls}
        aria-label={label}
        aria-pressed={active || undefined}
        {...rest}
      >
        <Icon name={name} size={size} decorative />
      </button>
    </Tooltip>
  );
}
