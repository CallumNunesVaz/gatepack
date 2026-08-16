# BUILD NOTES — application shell (layout, palette, shortcuts, motion, theme)

## Scope

This work package owns `app/renderer/App.tsx`, `app/renderer/styles.css`,
`app/renderer/ui/**`, `app/renderer/keys/**`, and new files under
`app/renderer/shell/`. It builds the workspace shell — the grid layout, the
command palette, the global keyboard handler, the theme toggle and the motion
primitives — on top of the shared foundation (`tokens.css`, `Icon.tsx`,
`Tooltip.tsx`, `keys/registry.ts`, `selection/**`).

## What was implemented

- **Shell layout** (`shell/Shell.tsx`, `styles.css`): a CSS grid of
  `rail | main | inspector` with a status bar spanning the bottom. The rail is
  an icon rail for the six views plus theme + shortcuts buttons. The main
  region holds a slim top bar (brand + "Search commands" trigger) and the
  active view; the right inspector (`shell/Inspector.tsx`) shows the current
  §15.2 selection and its resolved highlights. The page body never scrolls —
  the main region and the inspector scroll internally — and below 1080px the
  inspector is shed via a media query rather than crushing the main region.
  The old single-pane-at-a-time nav (`.app`, `.app__nav`, …) is gone.

- **Command palette** (`shell/CommandPalette.tsx`, `shell/filter.ts`): opens on
  `Mod+K`, fuzzy-filters `COMMANDS` (substring + subsequence scoring), groups
  by `group`, shows icon/title/hint/chord. Enter runs, arrows navigate, Escape
  closes, focus returns to where it was. Generated entirely from the registry.

- **Dispatch seam** (`shell/commands.tsx`): the shell owns a single
  `dispatch(id, payload?)`. Built-ins (view switching, theme, palette,
  shortcuts) are registered by the shell; **panels register their own ids via
  `useCommandBus().register(id, handler)`**. An id with no handler is reported
  through `onUnhandled`, which the shell turns into a visible "not yet wired"
  toast — never a silent drop.

- **Global shortcuts** (`shell/keyboard.ts`): one `keydown` listener driven by
  `COMMANDS` + `matchesChord`. It never fires while focus is in an input,
  textarea, select, contentEditable or Monaco, and only intercepts chords that
  are actually registered (reserved/host chords pass through). Tested against
  the real event path.

- **Shortcut help sheet** (`shell/ShortcutsSheet.tsx`): `Mod+/`, generated from
  `COMMANDS` so it cannot drift from what is bound.

- **Theme** (`shell/theme.ts`): `app.theme` in localStorage, OS default via
  `prefers-color-scheme`, `data-theme` on `<html>`. Explicit choice pins the
  attribute; no choice leaves it unset so the CSS media query stays live.

- **Status bar** (`shell/StatusBar.tsx`): project path, design name,
  diagnostics count, toolchain state (`doctor()`), and a pulsing running-command
  indicator fed by the bridge's `onProgress` events.

- **Motion**: palette scales in from 96%, overlays fade, the running command
  pulses; all durations come from the motion tokens, which collapse to 1ms
  under `prefers-reduced-motion`. No state is communicated by animation alone.

- **Primitives** (`ui/Button.tsx`, `IconButton.tsx`, `Panel.tsx`,
  `EmptyState.tsx`, `Spinner.tsx`, `Toast.tsx`), exported from `ui/index.ts`.
  Views may import these (API kept small).

## Guesses and placeholders

- **`data-density`** (`shell/density.ts`): the shell sets `data-density` on
  `<html>` (`spacious`/`cozy`/`compact`, matching the 1500px/1200px token
  breakpoints) because `tokens.css` promises views can read it. No view
  consumes it yet; the value names are my choice and may need renaming when the
  views agent actually reads them.

- **Inspector contents**: I render every field of the resolved `HighlightSet`
  (nets/cells/packages/states/minterms/transitions + provenance pointers).
  That is honest but may be more verbose than a designer would want; the shape
  is easy to trim.

- **`run.cancel` is unwired**: bare `Escape` outside an overlay reaches the
  dispatcher and reports "not yet wired" (a toast). The run panel agent owns
  cancel; until then Escape with no modal open is noisy. Consider routing
  Escape to the "cancel running command" panel once it exists.

- **Status-bar progress decay**: the pulsing indicator stays lit for ~1.6s
  after the last `onProgress` event (the bridge has no "done" event), so a
  very fast command may pulse briefly with no visible progress line. Honest,
  but imperfect.

## What could not be verified

- The **light theme** end-to-end: no view has migrated to the tokens yet, so
  several view styles still hardcode dark status colours (e.g. `#5eea94`,
  `#ff858a` in `styles.css`). I aliased the legacy `--bg/--panel/--text/...`
  variables onto the tokens so un-migrated views follow the theme, but the
  remaining literal hexes in view rules will look wrong under light until the
  views agent finishes. I did not touch those rules (views are off-limits).
- **Monaco typing guard** against the real editor: the `.monaco-editor` closest
  check is tested against a synthetic node; I could not run Monaco in jsdom to
  confirm the actual class name it uses (`.monaco-editor` is the standard
  container class, and the editor also focuses an inner `textarea`, both
  covered).
- Real `doctor()` output styling (only the fake-core "tools unknown" path was
  exercised in e2e).

## Weakest points

1. `run.cancel` on bare `Escape` (see above) — the most likely thing a user
   notices as wrong.
2. The inspector field list is exhaustive-but-flat; worth a design pass.
3. The 1080px inspector-shed breakpoint is a literal in `styles.css`, chosen to
   sit below the tokens' density stops; it should arguably become a token, but
   CSS custom properties cannot be read by media-query conditions, so a literal
   (with a comment) is the only honest option.

## Test counts

- Python: 557 passed, 5 skipped (unchanged — nothing in `gatepack/` touched).
- Renderer + main vitest: 180 → **205** (+25: filter, keyboard handler, theme,
  palette, shortcuts sheet, dispatch bus, density).
- Playwright e2e: 12 → **14** (+2: palette-by-keyboard + view switch,
  shortcuts sheet open/close).
