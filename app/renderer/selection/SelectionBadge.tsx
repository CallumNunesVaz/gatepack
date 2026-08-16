/**
 * A provenance-confidence badge. The single most important thing about a link
 * is whether it is *known*: `exact` (a surviving attribute), `inferred`
 * (structural match) and `none` ("no exact link") are rendered as three
 * distinct, greppable states — a transition that highlights nothing must say
 * so, not silently highlight nothing (§15.2).
 */

import type { LinkConfidence } from './types';

export function SelectionBadge({ confidence }: { confidence: LinkConfidence }) {
  if (confidence === 'exact') {
    return <span className="link-badge link-badge--exact" data-confidence="exact">exact</span>;
  }
  if (confidence === 'inferred') {
    return <span className="link-badge link-badge--inferred" data-confidence="inferred">inferred</span>;
  }
  return <span className="link-badge link-badge--none" data-confidence="none">no exact link</span>;
}
