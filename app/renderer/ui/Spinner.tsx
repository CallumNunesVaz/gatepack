/**
 * Spinner — a CSS-drawn activity indicator.
 *
 * Deliberately not an image or a font glyph: it is a single element with a
 * rotating border, so it works at any size, inherits `currentColor`, and pauses
 * instantly under `prefers-reduced-motion` (the tokens collapse the animation
 * duration to 1ms — a spinner is never the only signal, so it may freeze).
 */

export interface SpinnerProps {
  /** Diameter in px. */
  size?: number;
  /** Accessible text for screen readers. */
  label?: string;
}

export function Spinner({ size = 14, label = 'loading' }: SpinnerProps) {
  return (
    <span
      className="gp-spinner"
      role="status"
      aria-label={label}
      style={{ width: size, height: size }}
    />
  );
}
