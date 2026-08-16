/**
 * Button — the one place a pressed surface is defined, so every control that
 * looks like a button behaves like one. Variants map onto the tokens, never
 * onto ad hoc hex values in views.
 */

import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { Spinner } from './Spinner';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: 'sm' | 'md';
  /** Swaps the label for a spinner and disables the button. */
  loading?: boolean;
  children?: ReactNode;
}

export function Button({
  variant = 'secondary',
  size = 'md',
  loading = false,
  children,
  disabled,
  className,
  ...rest
}: ButtonProps) {
  const cls = [
    'gp-button',
    `gp-button--${variant}`,
    `gp-button--${size}`,
    className ?? '',
  ]
    .filter(Boolean)
    .join(' ');
  return (
    <button type="button" className={cls} disabled={disabled || loading} {...rest}>
      {loading ? <Spinner size={12} label="working" /> : null}
      {children}
    </button>
  );
}
