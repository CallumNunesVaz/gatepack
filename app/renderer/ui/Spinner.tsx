/**
 * Spinner — an SVG activity indicator.
 *
 * There was briefly a second, incompatible `.gp-spinner`: this component
 * rendered a bare span styled as a rotating border, while `views/views.css`
 * defined the same class as a flex row expecting an SVG ring child. Whichever
 * stylesheet loaded last won, so the spinner rendered as a static, malformed
 * dot. One class, one implementation, one stylesheet block — in `styles.css`
 * beside the other `ui/` primitives.
 *
 * The arc is drawn with a dash gap rather than a transparent border edge
 * because a stroked arc stays circular at every size and antialiases cleanly;
 * a 2px border at 14px does neither.
 *
 * Under `prefers-reduced-motion` the rotation slows rather than stopping: a
 * frozen spinner reads as a hung application. It is never the only signal that
 * something is running — callers pair it with text — so slowing is safe.
 */

export interface SpinnerProps {
  /** Diameter of the ring in px. */
  size?: number;
  /**
   * Accessible name, announced by screen readers. Also rendered visibly when
   * `showLabel` is set — a spinner alone says "wait", never "wait for what".
   */
  label?: string;
  /** Render `label` beside the ring. */
  showLabel?: boolean;
  className?: string;
}

export function Spinner({
  size = 16,
  label = 'Loading',
  showLabel = false,
  className,
}: SpinnerProps) {
  return (
    <span
      className={className ? `gp-spinner ${className}` : 'gp-spinner'}
      role="status"
      aria-live="polite"
    >
      <svg
        className="gp-spinner__ring"
        width={size}
        height={size}
        viewBox="0 0 24 24"
        aria-hidden="true"
        focusable="false"
      >
        {/* The full circle, faint: it gives the arc something to travel along,
            so the motion reads as progress rather than a flickering fragment. */}
        <circle className="gp-spinner__track" cx="12" cy="12" r="9" />
        <circle className="gp-spinner__arc" cx="12" cy="12" r="9" />
      </svg>
      <span className={showLabel ? 'gp-spinner__label' : 'gp-visually-hidden'}>
        {label}
      </span>
    </span>
  );
}
