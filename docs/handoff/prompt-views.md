# Package: the six views — from functional to professional

You are a senior front-end engineer with a background in EDA and instrumentation
UIs. You know that engineers reject a tool that looks like a toy, and that the
fastest way to look like a toy is decoration without information density.

## The project

`gatepack` compiles a truth table or FSM specification into a bill of materials
and a schematic netlist built from discrete 74AUP logic packages, formally
verifying the result on every build. The Electron app is strictly a view over
artefacts the CLI produces — it never recomputes a number the core reported.

## Your scope: the six existing views

```
app/renderer/views/SpecEditor.tsx          56 lines   Monaco + YAML
app/renderer/views/TruthTable.tsx         146 lines   §C11, divergence highlighting
app/renderer/views/Schematic.tsx          281 lines   §C12, netlistsvg + layers
app/renderer/views/BomView.tsx            204 lines   §C13, packing + BOM
app/renderer/views/AnalysisView.tsx       162 lines   §C14, metrics dashboard
app/renderer/views/VerificationPanel.tsx  173 lines   §C15, tri-state badges
app/renderer/views/spec/FsmGraph.tsx                  the FSM graph
```

They work. They are plain: unstyled tables, text buttons, no icons, no tooltips,
no empty states, no loading states, no responsiveness. Bring all of them up to a
professional standard for a nominal **1920x1080** window.

## What already exists — build on it, do not duplicate it

- `app/renderer/ui/tokens.css` — every colour, space, radius, duration, plus
  status colours and the selection highlight. **Never hardcode a colour or a
  pixel spacing.** If a token is missing, note it; do not add a literal.
- `app/renderer/ui/Icon.tsx` — 38 inline SVG icons.
- `app/renderer/ui/Tooltip.tsx` — accessible, shows on focus as well as hover.
- The shell agent is adding `Button`, `IconButton`, `Panel`, `EmptyState`,
  `Spinner` to `ui/` in parallel. **`ui/` is theirs — do not edit it.** If a
  primitive you need is not there yet, build the view with plain elements and
  tokens, and note what you wanted.

## What to do, per view

Apply throughout: icons in place of or beside text where the meaning is
unambiguous; a tooltip on every icon-only control and every column header whose
meaning is not obvious; real empty, loading and error states; and keyboard
navigability of every grid and list.

- **TruthTable** — this is a data grid, so treat it as one: sticky headers,
  zebra rows, monospace for values, and the divergence highlight made
  unmistakable (colour *and* an icon — a red/green distinction alone is
  invisible to a large minority of users). Virtualise if the row count warrants
  it; a 2^n truth table gets big fast.
- **Schematic** — zoom, pan, fit-to-window, and a legend for the layers.
  Selection highlight must use the selection tokens. Wide content scrolls inside
  its own container, never the page body.
- **BomView** — sortable columns, part numbers monospace, the spare-gate story
  visible at a glance, and the single-source warning prominent. Note:
  `BomLine.gatesPerPackage` carries whether packing can save anything —
  **derive that claim, never hardcode it**; a hardcoded "grouping is inert" note
  became a false statement about the user's own design once already.
- **AnalysisView** — a real dashboard: metric cards with the value, its limit
  and its band. `Metric.violated` comes from the core; never recompute the
  verdict in the renderer.
- **VerificationPanel** — the four-state badge (§C15) is the most important
  visual in the app: passed / failed / bounded / not-run must be
  distinguishable at a glance and never by colour alone. `bounded` is not
  `passed` and must never look like it. Counterexample steps should be
  navigable.
- **SpecEditor** — Monaco is already there. Diagnostics inline, a clear
  dirty-state indicator, and the three-way sync must keep working.
- **FsmGraph** — readable node/edge styling, selected state highlighted through
  the selection spine.

## Rules that are not negotiable

- **Do not change behaviour.** This is a restyle plus interaction polish. Every
  existing test in `app/renderer/views/*.test.tsx` must still pass, and where
  you change markup, update the test rather than deleting the assertion.
- **Never recompute a core number.** If a value can come from the envelope, it
  comes from the envelope.
- **The selection spine** (`app/renderer/selection/`) is read-only for you — the
  §15.2 cross-highlights work now and must keep working.
- Every test you add must be able to fail. Build the input that breaks it and
  keep that as the test. This project has shipped **nine** pieces of machinery
  that reported a status while measuring nothing, four with tests that could not
  have failed.

## Files you own

`app/renderer/views/**` (including the tests), and new files under
`app/renderer/views/`.

## Off-limits

`app/renderer/ui/**`, `app/renderer/keys/**`, `App.tsx`, `styles.css` (the shell
agent); `app/shared/api.ts`, `app/main/**`, `app/preload/**`, `gatepack/**`,
`app/renderer/panels/**` (the parity agent); `app/renderer/selection/**`
(read-only); `scripts/**`, `.github/**` (the audit agent).
