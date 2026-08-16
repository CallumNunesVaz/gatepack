# media

Brand assets for gatepack.

## The mark

A **NAND gate inside a five-pin logic package** — the product stated literally:
gatepack compiles a specification into logic gates in physical packages.

Three deliberate choices:

- **NAND**, because it is the universal gate — any logic can be built from it,
  which is the premise the whole tool rests on.
- **The IEEE distinctive shape** (flat back, semicircular front, inversion
  bubble), not a rounded box. Same reason §C12 renders schematics with
  netlistsvg rather than React Flow: engineers read the real symbol and reject
  the substitute.
- **Five pins, three left and two right** — the SOT-353 pinout the 74AUP
  single-gate parts actually ship in.

Colours are ENIG gold on solder-mask green: a real board, not a generic tech
gradient.

## Files

| file | use |
|---|---|
| `gatepack-mark.svg` | the icon, full detail — use at 48 px and above |
| `gatepack-mark-small.svg` | simplified for 16–32 px: no pins, no pin-1 dot, heavier strokes |
| `gatepack-logo.svg` | horizontal lockup: mark, wordmark, tagline |
| `gatepack.ico` | Windows/browser icon, 16–256 px, each size from the right source |
| `png/gatepack-<n>.png` | 16–1024 px raster |
| `png/gatepack-logo{,@2x}.png` | lockup raster, 1× and 2× |

**Below 48 px, use the small variant.** Detail that cannot be resolved is not
neutral — it is noise that blurs the silhouette, and the one thing that has to
survive at favicon size is that this is a NAND gate. The `.ico` already picks
the right source per size.

## Regenerating

```bash
.venv/bin/pip install pillow cairosvg     # not runtime dependencies of gatepack
.venv/bin/python scripts/make_media.py
```

The SVGs are the source; everything else is generated. Two traps are worth
knowing before editing them, because both fail silently rather than loudly:

- **Gradients on the gate leads must be `gradientUnits="userSpaceOnUse"`.** The
  default (`objectBoundingBox`) collapses on a horizontal line, whose bounding
  box has zero height — the leads vanished entirely and the glyph read as a
  plain letter `D`.
- **`--` is illegal inside an XML comment.** A decorative `---- rule ----` in a
  comment makes the file unparseable.

## Where these are used

| copy | consumer |
|---|---|
| `app/build/icon.png`, `app/build/icon.ico` | electron-builder, by its `buildResources` convention |
| `app/renderer/public/favicon.{png,ico}` | the renderer window, via `index.html` |

They are copies, not symlinks, because electron-builder and vite both expect
real files in those locations. **If you change the mark, re-run
`scripts/make_media.py` and copy the four files again.** Nothing checks that
they are in sync, which is a gap worth closing if the mark changes often.
