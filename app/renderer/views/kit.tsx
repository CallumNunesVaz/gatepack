/**
 * Small view-local primitives.
 *
 * The shell owns `ui/` and is adding `Button` / `IconButton` / `Panel` /
 * `EmptyState` / `Spinner` there in parallel. Until they land, these tiny
 * equivalents keep the views honest: they are built from `ui/Icon`, `ui/Tooltip`
 * and `ui/tokens.css` only, so nothing here introduces a colour or a spacing the
 * design system does not already own. When the shell's primitives exist, these
 * should be replaced by them (see BUILD-NOTES).
 */

import type { ReactNode } from 'react';
import { Icon, Tooltip } from '../ui';
import type { IconName } from '../ui';

export function Spinner({ label = 'working' }: { label?: string }) {
  return (
    <span className="gp-spinner" role="status" aria-live="polite">
      <svg className="gp-spinner__ring" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <circle cx="12" cy="12" r="10" />
      </svg>
      <span>{label}</span>
    </span>
  );
}

export interface EmptyStateProps {
  icon: IconName;
  title: string;
  hint?: string;
  testId?: string;
}

export function EmptyState({ icon, title, hint, testId }: EmptyStateProps) {
  return (
    <div className="gp-empty" data-testid={testId ?? 'empty-state'}>
      <Icon name={icon} size={30} decorative />
      <p className="gp-empty__title">{title}</p>
      {hint ? <p className="gp-empty__hint">{hint}</p> : null}
    </div>
  );
}

export interface IconButtonProps {
  icon: IconName;
  label: string;
  onClick?: () => void;
  disabled?: boolean;
  /** Sets `aria-pressed` and the pressed styling (for toggles). */
  active?: boolean;
  /** Toggle semantics: the button reflects on/off state. */
  toggle?: boolean;
  tooltip?: ReactNode;
  testId?: string;
}

/**
 * An icon-only control. `label` is the accessible name and is required — an
 * icon button without one is announced as "button". When a tooltip is supplied
 * it supplements the name (via `aria-describedby`), it never replaces it.
 */
export function IconButton({
  icon,
  label,
  onClick,
  disabled,
  active,
  toggle,
  tooltip,
  testId,
}: IconButtonProps) {
  const button = (
    <button
      type="button"
      className="view-btn view-btn--ghost view-btn--icon"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      aria-pressed={toggle ? (active ?? false) : undefined}
      data-testid={testId}
    >
      <Icon name={icon} decorative />
    </button>
  );
  return tooltip !== undefined ? (
    <Tooltip content={tooltip}>{button}</Tooltip>
  ) : (
    button
  );
}

/** A labelled run/action button with a leading icon and a busy state. */
export function ActionButton({
  icon,
  label,
  busyLabel,
  busy = false,
  disabled = false,
  onClick,
  primary = false,
  testId,
}: {
  icon: IconName;
  label: string;
  busyLabel?: string;
  busy?: boolean;
  disabled?: boolean;
  onClick: () => void;
  primary?: boolean;
  testId?: string;
}) {
  return (
    <button
      type="button"
      className={primary ? 'view-btn view-btn--primary' : 'view-btn'}
      onClick={onClick}
      disabled={disabled || busy}
      data-testid={testId}
    >
      <Icon name={busy ? 'pending' : icon} decorative />
      {busy ? (busyLabel ?? label) : label}
    </button>
  );
}
