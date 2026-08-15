/**
 * Shared check-status badge (§C15 [R4-25]). Four states, four unmistakable
 * visuals, used everywhere a check result is shown:
 *
 *   - `passed`   — solid green tick.
 *   - `bounded`  — amber, and it *must* show its bound (a bounded pass is not a
 *                  pass; rendering it green recreates the vacuous-pass failure).
 *   - `failed`   — solid red cross.
 *   - `not_run`  — grey, dashed, "not run"; a legitimate visible state, never
 *                  styled as pass or fail.
 */

import type { CheckStatus } from '../../shared/api';

const ICONS: Record<CheckStatus, string> = {
  passed: '\u2713',
  bounded: '\u2248',
  failed: '\u2715',
  not_run: '\u2013',
};

const LABELS: Record<CheckStatus, string> = {
  passed: 'passed',
  bounded: 'bounded',
  failed: 'failed',
  not_run: 'not run',
};

const CLASSES: Record<CheckStatus, string> = {
  passed: 'status status--passed',
  bounded: 'status status--bounded',
  failed: 'status status--failed',
  not_run: 'status status--not-run',
};

export interface StatusBadgeProps {
  status: CheckStatus;
  /** Induction/BMC depth. Required (and displayed) for `bounded`. */
  bound?: number;
  /** Why a check did not run (missing tool etc.). */
  skippedReason?: string;
}

export function StatusBadge({ status, bound, skippedReason }: StatusBadgeProps) {
  const title = skippedReason && status === 'not_run' ? `not run: ${skippedReason}` : status;
  return (
    <span className={CLASSES[status]} data-status={status} data-testid="status-badge" title={title}>
      <span className="status__icon" aria-hidden="true">{ICONS[status]}</span>
      <span className="status__label">{LABELS[status]}</span>
      {status === 'bounded' && bound !== undefined ? (
        <span className="status__bound" data-testid="status-bound">(k = {bound})</span>
      ) : null}
    </span>
  );
}

/** Whether a status string (from a possibly-unknown source) is a known check state. */
export function isCheckStatus(value: string): value is CheckStatus {
  return value === 'passed' || value === 'bounded' || value === 'failed' || value === 'not_run';
}
