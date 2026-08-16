/**
 * The icon set — inline SVG paths, no icon font, no network request.
 *
 * A strict CSP forbids any external fetch (§5.2), and an icon font would drag
 * a binary asset into the bundle for glyphs we can draw in a few hundred bytes.
 * Every icon is a single 24x24 path drawn on the same grid so they optically
 * match at 16px.
 *
 * `title` is what makes an icon accessible. An IconButton with no accessible
 * name is a button that a screen reader announces as "button" — so `title` is
 * required whenever the icon is not accompanied by visible text, and
 * `decorative` is the explicit opt-out for the case where a label sits beside
 * it and the icon would only repeat the label.
 */

export type IconName =
  | 'spec'
  | 'truthTable'
  | 'schematic'
  | 'packing'
  | 'analysis'
  | 'verify'
  | 'doctor'
  | 'build'
  | 'estimate'
  | 'compile'
  | 'simulate'
  | 'provenance'
  | 'open'
  | 'save'
  | 'export'
  | 'search'
  | 'settings'
  | 'help'
  | 'keyboard'
  | 'close'
  | 'chevronRight'
  | 'chevronDown'
  | 'check'
  | 'warning'
  | 'error'
  | 'info'
  | 'pending'
  | 'cancel'
  | 'copy'
  | 'refresh'
  | 'theme'
  | 'zoomIn'
  | 'zoomOut'
  | 'fit'
  | 'link'
  | 'chip'
  | 'terminal';

/**
 * 24x24 path data. Stroke-based, `fill="none"`, so a single set works on any
 * background and at any size without a second solid variant.
 */
const PATHS: Record<IconName, string> = {
  spec: 'M6 3h8l4 4v14H6z M14 3v4h4',
  truthTable: 'M3 5h18v14H3z M3 10h18 M9 5v14 M15 5v14',
  schematic: 'M3 8h4 M17 12h4 M7 4h6l4 4v8l-4 4H7z M3 16h4',
  packing: 'M4 7l8-4 8 4-8 4z M4 7v10l8 4 8-4V7 M12 11v10',
  analysis: 'M4 20V10 M10 20V4 M16 20v-8 M22 20H2',
  verify: 'M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z M9 12l2 2 4-4',
  doctor: 'M12 4v16 M4 12h16 M7 7l10 10 M17 7L7 17',
  build: 'M14 3l7 7-4 4-7-7z M10 10L3 17v4h4l7-7 M13 6l5 5',
  estimate: 'M12 3a9 9 0 109 9h-9z M12 3v9',
  compile: 'M8 6l-5 6 5 6 M16 6l5 6-5 6 M13 4l-2 16',
  simulate: 'M3 12h4l3-7 4 14 3-7h4',
  provenance: 'M6 4v6a4 4 0 004 4h4 M18 10l-4 4 4 4 M4 4h4 M4 20h4',
  open: 'M3 7a2 2 0 012-2h4l2 3h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z',
  save: 'M5 3h11l3 3v15H5z M8 3v6h7V3 M8 14h8v7H8z',
  export: 'M12 3v12 M8 11l4 4 4-4 M4 19h16',
  search: 'M11 4a7 7 0 100 14 7 7 0 000-14z M16 16l5 5',
  settings: 'M12 9a3 3 0 100 6 3 3 0 000-6z M19 12l2-1-2-4-2 1-3-2V3H10v3L7 8 5 7 3 11l2 1-2 1 2 4 2-1 3 2v3h4v-3l3-2 2 1 2-4z',
  help: 'M12 3a9 9 0 100 18 9 9 0 000-18z M9.5 9.5a2.5 2.5 0 015 0c0 1.7-2.5 2-2.5 4 M12 17.5v.5',
  keyboard: 'M3 6h18v12H3z M7 10h.5 M11 10h.5 M15 10h.5 M8 14h8',
  close: 'M5 5l14 14 M19 5L5 19',
  chevronRight: 'M9 5l7 7-7 7',
  chevronDown: 'M5 9l7 7 7-7',
  check: 'M4 12l5 6L20 5',
  warning: 'M12 3l10 18H2z M12 10v5 M12 18v.5',
  error: 'M12 3a9 9 0 100 18 9 9 0 000-18z M12 7v6 M12 16v.5',
  info: 'M12 3a9 9 0 100 18 9 9 0 000-18z M12 11v6 M12 7.5v.5',
  pending: 'M12 3a9 9 0 100 18 9 9 0 000-18z M12 7v5l3 3',
  cancel: 'M12 3a9 9 0 100 18 9 9 0 000-18z M6 6l12 12',
  copy: 'M9 9h11v11H9z M5 15H4V4h11v1',
  refresh: 'M20 12a8 8 0 11-2.3-5.6 M20 3v4h-4',
  theme: 'M12 3a9 9 0 100 18z M12 3a9 9 0 010 18',
  zoomIn: 'M11 4a7 7 0 100 14 7 7 0 000-14z M16 16l5 5 M11 8v6 M8 11h6',
  zoomOut: 'M11 4a7 7 0 100 14 7 7 0 000-14z M16 16l5 5 M8 11h6',
  fit: 'M4 9V4h5 M20 9V4h-5 M4 15v5h5 M20 15v5h-5',
  link: 'M10 14a4 4 0 006 0l3-3a4 4 0 10-6-6l-1 1 M14 10a4 4 0 00-6 0l-3 3a4 4 0 106 6l1-1',
  chip: 'M8 8h8v8H8z M4 10h4 M4 14h4 M16 10h4 M16 14h4 M10 4v4 M14 4v4 M10 16v4 M14 16v4',
  terminal: 'M3 4h18v16H3z M7 9l3 3-3 3 M13 15h4',
};

export interface IconProps {
  name: IconName;
  /** Rendered size in px; the grid is designed for 16, 20 and 24. */
  size?: number;
  /**
   * The accessible name. Required unless `decorative` — an icon-only control
   * without one is announced as an unlabelled button.
   */
  title?: string;
  /** Set when adjacent visible text already names the control. */
  decorative?: boolean;
  className?: string;
  strokeWidth?: number;
}

export function Icon({
  name,
  size = 16,
  title,
  decorative,
  className,
  strokeWidth = 1.75,
}: IconProps) {
  const path = PATHS[name];
  const labelled = Boolean(title) && !decorative;
  return (
    <svg
      className={className ? `gp-icon ${className}` : 'gp-icon'}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={labelled ? 'img' : undefined}
      aria-label={labelled ? title : undefined}
      aria-hidden={labelled ? undefined : true}
      focusable="false"
      data-icon={name}
    >
      {title && !decorative ? <title>{title}</title> : null}
      {path.split(' M').map((segment, i) => (
        <path key={i} d={i === 0 ? segment : `M${segment}`} />
      ))}
    </svg>
  );
}

/** Every icon name, for the icon-coverage test and the shortcut help sheet. */
export const ICON_NAMES = Object.keys(PATHS) as IconName[];
