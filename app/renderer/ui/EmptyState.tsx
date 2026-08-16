/**
 * EmptyState — the honest "there is nothing here (yet)" message.
 *
 * Every view that can legitimately hold nothing renders this rather than a
 * blank surface: a blank region reads as a rendering bug, an EmptyState reads
 * as a state.
 */

import type { ReactNode } from 'react';
import { Icon, type IconName } from './Icon';

export interface EmptyStateProps {
  icon?: IconName;
  title: string;
  description?: ReactNode;
}

export function EmptyState({ icon, title, description }: EmptyStateProps) {
  return (
    <div className="gp-empty">
      {icon ? <Icon name={icon} size={22} decorative className="gp-empty__icon" /> : null}
      <p className="gp-empty__title">{title}</p>
      {description ? <p className="gp-empty__desc">{description}</p> : null}
    </div>
  );
}
