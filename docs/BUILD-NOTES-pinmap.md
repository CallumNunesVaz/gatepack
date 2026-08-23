# BUILD-NOTES — footprint pin map (Package F)

Scope: build the data model and the emitter half of a footprint pin map — the
``<name>.pins.csv`` file, its citations, the consistency checks that make a
*placeholder* pin map worth having, and the KiCad-emitter consumer.  The C13
renderer half is a separate package and is explicitly out of scope.

## What I implemented

### The data model — `gatepack/pinmap.py`

- ``PinMapRow`` / ``PartPinMap`` (pydantic, mirroring ``gatepack/parts.py``),
  keyed on the **ordered part** ``(part_suffix, package)``, not the cell — one
  cell (``INV``) is several parts (``1G04``/``2G04``/``3G04``) with different
  pinouts.  ``PartPinMap.verification`` reuses ``parts.Verification``, defaults
  to ``PLACEHOLDER`` (fail-closed).
- ``load_pinmaps`` (parse + structural validation, incl. check 6 "no two rows
  for the same key disagree") and ``load_pinmaps_cited`` (attach provenance from
  ``<name>.pins.refs.md``; a missing ``.pins.csv`` yields ``{}``).
- ``check_pinmaps(parts, pinmaps)`` runs the six cross-checks and returns
  violation strings.  Each check is a separate function so a test can prove an
  input violates *exactly* that check and nothing else.
- ``pin_map_summary`` / ``bundled_pin_map_summary`` for the placeholder/cited
  count surfaced by `lib check` and `doctor`.

### The six consistency checks (the actual deliverable)

1. pin count == the count implied by ``package`` (``PACKAGE_PIN_COUNTS`` mirrors
   the cited "Package pin counts" table in ``74aup.refs.md`` and is
   cross-checked against it by a test);
2. exactly one ``VCC`` and exactly one ``GND``;
3. the map covers exactly ``gates_per_pkg`` gates;
4. each gate's signal set equals the cell's pin table exactly (which is what
   makes "``inputs`` input pins and exactly one output pin" true by
   construction);
5. pin numbers appear exactly once, contiguous from 1;
6. no two rows for the same ``(part_suffix, package)`` disagree (load-time).

### The data — `libraries/74aup.pins.csv` + `.refs.md`

20 pin maps, one per G/F part that has a real part number.  Every one is a
placeholder, and ``74aup.pins.refs.md`` opens with a STATUS block saying so in
those words.  Six library rows are deliberately unmapped (see below).

### The consumer — `gatepack/emit/kicad.py`

- ``_package_pin_entries(part, pinmap)`` uses a part's pin map when present and
  the positional fallback when not; the fallback is byte-for-byte the old
  behaviour.
- The pin-number notice is **conditional on provenance, not presence**, and is
  **per-part**: no map → loud positional warning; placeholder map → loud
  warning naming the map as the (placeholder) source; cited map → soft positive
  statement.  A mixed netlist names each part and its status.

### Reporting — `gatepack/cli.py`

`lib check` runs the six checks (rejecting, exit 1, on any violation) and prints
``pin maps: N part(s) mapped, P placeholder, C cited``.  `doctor` (human output)
surfaces the same count for the bundled library when it is discoverable.  The
``--json`` payloads are unchanged, so the pinned IPC contract is untouched.

## What I could not source (and how I marked it)

**Every pin number is a placeholder.**  I have no datasheets.  The pin
*positions* are positional (gate-1 signal pins sorted, gate-2 signal pins, …,
VCC, GND), never derived from a package name, never copied from a "similar"
part, never recalled.  The refs file says this outright.

Two derived quantities need flagging specifically:

- **``NC`` rows** (the single-gate inverter ``1G04`` and buffer ``1G34`` in
  SOT-353 have one lead the pin model does not account for: 5 package pins −
  2 signal − 2 power = 1).  The *count* is arithmetic over already-held data;
  the *label* ``NC`` is a placeholder — I do not know that lead is a
  no-connect, only that it is a lead the model has no signal for.  The emitter
  writes it as a passive pin that attaches to no net.
- **``DFF_SR`` (``74AUP1G74``) is deliberately unmapped.**  ``74aup.refs.md``
  already records it as "complementary Q/Q̄", but ``gatepack/pins.py``
  ``F_PIN_DIRECTIONS`` has only ``Q``.  Writing the 8th lead as ``NC`` would be
  a fabrication (it is an output, not a no-connect).  Extending
  ``F_PIN_DIRECTIONS`` to add ``Q̄`` would ripple into Liberty/netlist generation
  that other agents own, so I left ``DFF_SR`` to the positional fallback instead
  of lying about it.

Also unmapped: ``DFF_S``/``NAND3``/``NOR3`` (no candidate part — empty
``part_suffix``), ``CNT4`` (M-cell; pin table lives in ``gatepack/macros``),
``SUPERVISOR`` (S-cell; pin table in ``gatepack/pins.py`` S seam, and check 4's
"``inputs`` input pins" does not apply to it).

## What I guessed / decided

- **Pin-map provenance is attached in ``load_parts_cited``** (via a ``pinmap``
  field on ``Part``), so `gatepack build` picks the map up with no change to
  ``build.py`` (out of my scope).  ``Part.pinmap`` is typed ``Any`` to avoid a
  parts↔pinmap import cycle; the concrete type is ``PartPinMap``.
- **Check 4 iterates the gates present in the map**, not ``1..gates_per_pkg``,
  so check 3 (coverage) and check 4 (per-gate I/O) cannot both fire on the same
  input — which is what makes the "violates exactly this check" tests possible.
- **The pin-map placeholder count is a finding, not a gate.**  An *inconsistent*
  map is rejected (exit 1); a *consistent placeholder* map ships with the count
  reported.  That mirrors how the electrical data works (uncited is marked, not
  refused) while still making a wrong pinout unshippable.
- **Identical duplicate rows collapse silently; disagreeing rows raise.**
  Check 6 is about disagreement, not duplication, so an exact duplicate is not
  an error.

## What is weakest / least certain

- **The ``NC`` label.**  It is the honest placeholder for "a lead the model has
  no signal for", but it is not a fact about that lead.  If a reviewer would
  rather see these two parts left to the fallback (like ``DFF_SR``), the map
  and one test shrink; I chose to keep ``1G04``/``1G34`` mapped because INV is
  the most-used cell and leaving it unmapped would hide the pin-map machinery
  from the common case.
- **Doctor's bundled-library lookup.**  ``bundled_pin_map_summary`` locates
  ``libraries/74aup.csv`` relative to the ``gatepack`` package (a source
  checkout); in a PyInstaller bundle that file is deliberately absent, so the
  line is omitted.  `lib check` is the canonical surface; doctor's line is
  best-effort and I could not test the frozen-bundle path.
- **Check 4's phrase vs implementation.**  The brief says "exactly ``inputs``
  input pins and exactly one output pin"; I implemented it as "the gate's
  signal set equals the cell's pin table", which is strictly stronger (it also
  catches a wrong pin *name*) and implies the brief's phrasing for G/F cells.
  If a reviewer wants a direction-count check that tolerates alternate signal
  names, that is a small change to ``_check_gate_io``.

## What I could not verify

- **Real KiCad import.**  The ``.net`` s-expression was not import-tested (no
  KiCad here), including the ``passive`` direction I chose for ``NC`` pins and
  the per-part ``comment`` fields.  The format mirrors the existing emitter and
  the notice/comment mechanism it already used, but "KiCad accepts it" is
  unverified.
- **The full two-build reproducibility against Yosys.**  ``scripts/repro_check.py``
  compares front-end artefacts here (no Yosys); the build/netlist half is only
  provable in the ``gatepack-toolchain:m6`` container, which I could not run
  inside this environment.  Determinism of the netlist path is pinned by
  ``test_kicad_netlist_deterministic`` and the unit tests instead.

## Files

- new: `gatepack/pinmap.py`, `libraries/74aup.pins.csv`,
  `libraries/74aup.pins.refs.md`, `tests/unit/test_pinmap.py`,
  `tests/unit/test_kicad_pinmap.py`.
- changed: `gatepack/parts.py` (one field), `gatepack/refs.py` (attach pin maps),
  `gatepack/emit/kicad.py` (map + conditional per-part notice),
  `gatepack/cli.py` (`lib check`/`doctor` reporting).

## Test counts

Baseline: 749 passed, 5 skipped.  After: 772 passed, 5 skipped (+23).
