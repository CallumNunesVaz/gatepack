/**
 * Panel — a titled surface. The smallest container that still reads as a unit,
 * with an optional header and trailing actions, so views and the inspector
 * share one visual grammar instead of each inventing a heading row.
 */

import type { ReactNode } from 'react';

export interface PanelProps {
  title?: ReactNode;
  /** Trailing controls in the header row. */
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function Panel({ title, actions, children, className }: PanelProps) {
  const cls = className ? `gp-panel ${className}` : 'gp-panel';
  return (
    <section className={cls}>
      {title || actions ? (
        <header className="gp-panel__header">
          {title ? <h2 className="gp-panel__title">{title}</h2> : null}
          {actions ? <div className="gp-panel__actions">{actions}</div> : null}
        </header>
      ) : null}
      <div className="gp-panel__body">{children}</div>
    </section>
  );
}
