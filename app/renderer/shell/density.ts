/**
 * Density signal for views.
 *
 * The shell sets `data-density` on <html> so a view can respond to window size
 * without querying the viewport itself (the tokens' comment promises this). The
 * values line up with the media-query breakpoints in `tokens.css`:
 *
 *  - `spacious` — wider than 1500px (the nominal 1920x1080 window);
 *  - `cozy`     — 1500px and below (inspector/sidebar shrink);
 *  - `compact`  — 1200px and below.
 */

import { useEffect } from 'react';

export type Density = 'spacious' | 'cozy' | 'compact';

export function densityForWidth(width: number): Density {
  if (width <= 1200) return 'compact';
  if (width <= 1500) return 'cozy';
  return 'spacious';
}

export function useDensity(): void {
  useEffect(() => {
    const apply = () => {
      document.documentElement.dataset.density = densityForWidth(window.innerWidth);
    };
    apply();
    window.addEventListener('resize', apply);
    return () => window.removeEventListener('resize', apply);
  }, []);
}
