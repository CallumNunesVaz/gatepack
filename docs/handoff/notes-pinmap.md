# Handoff notes — pin map (Package F)

Short form for the next reader: the pin map exists now, every number in it is a
placeholder, and the machine that matters is the six consistency checks, not the
numbers.

## What shipped

- `libraries/74aup.pins.csv` — 20 pin maps, keyed `(part_suffix, package)`.
  Every pin number is positional/placeholder; `74aup.pins.refs.md` says so in a
  STATUS block at the top.
- `gatepack/pinmap.py` — typed model, loader, provenance (reuses
  `parts.Verification`), and `check_pinmaps` running the six checks.
- `gatepack/emit/kicad.py` — uses the map when a part has one, positional
  fallback otherwise; the pin-number notice is now per-part and conditional on
  provenance (no map / placeholder / cited), never one global claim.
- `gatepack/cli.py` — `lib check` runs the checks (exit 1 on any violation) and
  prints the placeholder count; `doctor` surfaces the same count (best-effort).

## The three things I am least confident about

1. **The `NC` lead on the single inverter/buffer (`1G04`, `1G34`).**  It is the
   honest placeholder for "a lead the model has no signal for", but I cannot say
   it is a no-connect.  The alternative — leave those two parts unmapped like
   `DFF_SR` — is defensible and smaller; I kept them mapped because INV is the
   common case.  If a reviewer objects, it is a ~6-line deletion plus one test.
2. **`DFF_SR` being left unmapped.**  It is the only G/F part with a real part
   number and no pin map, because the pin model has ``Q`` but not ``Q̄`` (the
   refs record says "complementary Q/Q̄").  Fixing it properly means adding
   ``Q̄`` to ``F_PIN_DIRECTIONS``, which ripples into Liberty/netlist generation
   owned by other agents — I refused to touch that.  The positional fallback
   still covers it, loudly.
3. **Doctor's bundled-library count is best-effort.**  `doctor` finds the
   library relative to the `gatepack` package (source checkout only); in a
   frozen PyInstaller bundle the library is deliberately absent, so the line is
   omitted and `lib check <csv>` is the only surface.  I could not test the
   frozen path here.

## What I could not verify

- **No KiCad import test.**  The `.net` s-expression (including the `passive`
  direction for NC pins and the per-part `comment` fields) has not been opened
  in real KiCad.
- **No full two-build Yosys reproducibility.**  `scripts/repro_check.py` ran
  front-end artefacts only (no Yosys in this environment); the netlist half is
  only provable in `gatepack-toolchain:m6`.

## One known stale note I could not touch

`gatepack/build.py::_build_notes` still says "real footprint pin numbers need
footprint data (parts.csv has none)".  That is literally still true (the pin
map is a *separate* file, and it is placeholder anyway), but a follow-up should
soften it to mention the pin map; `build.py` was out of scope here.

## Proofs that matter

- `check_pinmaps(load_parts(...), load_pinmaps_cited(...))` == ``[]`` on the
  shipped library.
- Each of the six checks has a test with an input that violates exactly that
  check (the other five assert empty on the same input).
- `lib check` prints `pin maps: 20 part(s) mapped, 20 placeholder, 0 cited` and
  the count is pinned by a test so it cannot drift to zero.
- An inconsistent pin map (6 pins in a 5-pin package) makes `lib check` exit 1.
- No-pin-map fallback is byte-for-byte the old positional behaviour (pinned in
  `test_kicad_pinmap.py::test_no_pin_map_falls_back_to_positional_and_loud_notice`).
