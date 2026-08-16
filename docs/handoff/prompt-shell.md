# Package: the application shell — layout, command palette, shortcuts, motion

You are a senior front-end engineer who builds professional desktop tools —
the kind engineers keep open all day — and who has strong opinions about
information density, keyboard access and restraint in animation.

## The project

`gatepack` compiles a truth table or FSM specification into a bill of materials
and a schematic netlist built from discrete 74AUP logic packages, and formally
verifies the result on every build. The Electron app in `app/` is strictly a
view over artefacts the CLI produces — it never reimplements logic, it spawns
`gatepack <cmd> --json` and renders what comes back.

The app currently works and is ugly. `app/renderer/App.tsx` is 73 lines: a
title bar, six nav buttons, one pane at a time. There is no keyboard access
beyond tabbing, no icons, no tooltips, no motion, no responsiveness, and no way
to reach a command that is not one of those six buttons. **The user has asked
for a comprehensive overhaul**, designed for a nominal 1920x1080 window.

## What already exists — build on it, do not duplicate it

Read these first. They are the shared foundation and three other agents are
building on them at the same time:

- `app/renderer/ui/tokens.css` — every colour, space, radius, duration, and the
  density breakpoints. **Never hardcode a colour or a pixel spacing**; if a
  token is missing, add it there.
- `app/renderer/ui/Icon.tsx` — 38 inline SVG icons, `<Icon name="build" />`.
- `app/renderer/ui/Tooltip.tsx` — accessible tooltip, shows on focus too.
- `app/renderer/keys/registry.ts` — **the** table of every command in the app,
  with ids, groups, icons, chords and CLI mappings. `registry.test.ts` asserts
  no two commands share a chord and that every CLI subcommand is reachable.

## What to build

### 1. The shell layout (1920x1080 nominal)

Replace the single-pane-at-a-time nav with a real workspace. A left icon rail
for the six views, a main region, and a right inspector panel that shows what is
currently selected (the selection spine already exists in
`app/renderer/selection/`). A status bar along the bottom carrying the project
path, the design name, the diagnostics count, and the toolchain state.

At 1920x1080 there is room to show the schematic and the BOM together; below
`--gp-sidebar-w`'s breakpoints the shell should shed the inspector rather than
crushing everything. Use CSS grid and the tokens' breakpoints. **The one thing
that must never happen is a horizontal scrollbar on the page body** — wide
content (netlists, tables) scrolls inside its own container.

### 2. The command palette

`Mod+K`. Fuzzy-filters `COMMANDS`, grouped by `group`, showing each command's
icon, title, hint and chord. Enter runs, arrows navigate, Escape closes, focus
returns to where it was. This is what makes "everything the CLI does" reachable
without thirty toolbar buttons.

Commands are dispatched by id through a single callback the shell owns —
another agent is implementing the panels behind several of these ids, so define
the dispatch seam clearly and leave unimplemented ids reporting "not yet
wired" rather than failing silently.

### 3. Keyboard shortcuts

A single global handler driven by `COMMANDS` and `matchesChord`. It must:

- **not fire while the user is typing** in an input, textarea or the Monaco
  editor — the commonest way a shortcut handler ruins a text field. Test this.
- show a shortcut help sheet on `Mod+/`, generated from the registry so it
  cannot drift from what is actually bound.
- leave browser/Electron reserved chords alone.

### 4. Motion, and the theme

Animation that shows where something came from: panels slide from the edge they
belong to, the palette scales in from 96%, a selection ripples to the linked
view, a running command pulses in the status bar. All durations from the motion
tokens; **everything must remain fully legible with `prefers-reduced-motion`**,
which the tokens already collapse to 1ms — an animation may never be the only
thing communicating a state change.

Add the light/dark toggle (`app.theme`), persisting to localStorage, defaulting
to the OS preference. `data-theme` on the root element is what the tokens read.

### 5. Tests

Vitest with `@testing-library/react` for the palette, the key handler and the
theme; at least one Playwright e2e that opens the palette by keyboard and
switches views. Make each test fail first — a palette test that passes when the
palette renders nothing has measured nothing, and this project has shipped
**nine** pieces of machinery that reported a status while measuring nothing.

## Files you own

`app/renderer/App.tsx`, `app/renderer/styles.css`, `app/renderer/ui/**` (you may
add primitives — Button, IconButton, Panel, EmptyState, Spinner, Toast — and
other agents will use them, so export them from `ui/index.ts` and keep the API
small), `app/renderer/keys/**`, and new files under `app/renderer/shell/`.

## Off-limits — three other agents are in this repo right now

- `app/renderer/views/**` — the views agent is restyling all six.
- `app/shared/api.ts`, `app/main/**`, `app/preload/**`, `gatepack/**` — the
  parity agent owns the IPC surface and the core.
- `scripts/**`, `.github/**` — the audit agent.
- `app/renderer/selection/**` — read it, do not edit it.

If you need a primitive that a view needs too, put it in `ui/` and say so in
your notes.
