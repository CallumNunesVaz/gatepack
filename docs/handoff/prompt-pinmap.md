# Package F — a footprint pin map, and the two things blocked on it

Read `docs/handoff/delegation-rules.md` first. Every rule there applies.

## The task

`parts.csv` carries `package` but no pin map. Two deferred features are blocked
on that one missing data structure, and neither is blocked on code:

* **KiCad pin numbers.** `gatepack/emit/kicad.py` numbers pins positionally
  (gate-1 signal pins, gate-2 signal pins, …, VCC, GND) and shouts about it in
  `PIN_NUMBER_NOTICE`. A netlist with invented pin numbers cannot be built.
* **Package pinout rendering on the C13 cards** (§24.2), deferred to v0.2
  explicitly "blocked on *data*: `parts.csv` carries `package` but no pin map,
  and adding one increases the transcription burden R8 warns about. The renderer
  is the easy half."

You are building the data model and the emitter half. The renderer half is a
separate package and is **not** in your scope.

## The rule that outranks the task

**Never invent an electrical or packaging value.** §1.3/[R4-21]: every value in a
parts table carries a datasheet citation with document revision and table/page,
or it is *explicitly marked a placeholder*. A plausible number with a fabricated
citation is the worst thing you can do to this project — it can reach a physical
board, and a wrong pin number is the most direct route from this repository to a
dead board there is.

Read `libraries/74aup.refs.md` before you write a line. The honest current state:
every electrical figure is a marked placeholder; `gates_per_pkg` and `package`
are individually cited because a wrong `gates_per_pkg` yields a netlist that
physically cannot be built.

**You do not have datasheets.** So every pin-map row you add is a
**placeholder**, marked exactly the way the existing placeholder rows are, and
your refs file says so in those words. Do not derive a pinout from a package
name. Do not copy one part's pinout to another "because they're both SOT-353".
Do not recall a pinout from memory and present it as data — a remembered pinout
is a fabrication with extra steps.

That sounds like it makes the package pointless. It does not, and the reason is
the next section.

## The thing that makes a placeholder pin map worth having

**A pin map is cross-checkable against data the library already holds.** That is
what this package is really delivering: a structure in which a wrong pinout —
placeholder or cited — is *caught* rather than trusted.

Every one of these is a hard check, and each must have a test that fails when
you break it:

* the number of pins in the map equals the pin count implied by `package`
  (SOT-353 = 5, SOT-363 = 6, VSSOP-8 = 8, SO-16 = 16, SOT-23 = 3);
* exactly one `VCC` pin and exactly one `GND` pin;
* the map covers exactly `gates_per_pkg` gates;
* each gate has exactly `inputs` input pins and exactly one output pin;
* every pin number appears exactly once, and the numbers are contiguous from 1;
* no two rows for the same `(part_suffix, package)` disagree.

A placeholder pinout that satisfies all six is a *consistent* placeholder: it
cannot silently misdescribe how many gates or pins a part has, which is the
class of error that actually reaches a board. An inconsistent one is rejected
before it ships. That is the deliverable.

## The data model

New file `libraries/74aup.pins.csv`, and its citations in
`libraries/74aup.pins.refs.md` mirroring the structure of `74aup.refs.md`.

Key the map on the **ordered part**, not the cell — a pinout is a property of
the part number and its package, and one cell (`INV`) has several parts
(`1G04`, `2G04`, `3G04`) with different pinouts:

```
part_suffix,package,pin,signal,gate
1G00,SOT-353,1,A,1
1G00,SOT-353,2,B,1
...
1G00,SOT-353,5,VCC,
```

`signal` uses the pin names the cell's `function` already uses (`A`, `B`, `C`,
`Y`) plus `VCC`/`GND`; `gate` is the 1-based gate index within the package, empty
for power pins. Follow `gatepack/pins.py`, which already owns the per-cell pin
table — do not invent a second naming convention beside it.

Load it through a typed model in the style of `gatepack/parts.py`, with the same
`Provenance` distinction between verified and placeholder. Fail closed: a part
with no refs entry is a placeholder, never assumed verified.

**A pin map is optional.** A library with no `.pins.csv` must keep working
exactly as it does today — that is the 749-test regression suite, and it is not
allowed to move.

## Consumer: the KiCad emitter

`gatepack/emit/kicad.py` uses the map when one is present for the part, and its
positional fallback when one is not. Three requirements:

1. **The notice is conditional on provenance, not on presence.** A placeholder
   map is still not a manufacturer pinout, so `PIN_NUMBER_NOTICE` — or a version
   of it that names the map as the source — must still appear, just as loudly.
   The notice may only soften for a part whose pin map is *cited*. Test all
   three states: no map, placeholder map, cited map.
2. Per-part, not per-file: a netlist mixing cited and placeholder parts says
   which parts are which. A single global claim over a mixed netlist is exactly
   the kind of unmarked assumption this project exists to prevent.
3. The emitted file stays deterministic and timestamp-free (§C6, §5.5).

## `gatepack lib check`

Extend it to run every consistency check above, and to report the placeholder
count for pin maps the way it already does for electrical data. `gatepack
doctor` should surface the same count. A user must be able to ask "is any of
this pinout real?" and get a straight answer.

## Your file scope — nothing outside it

* `libraries/74aup.pins.csv`, `libraries/74aup.pins.refs.md` (new)
* `gatepack/pinmap.py` (new), `gatepack/pins.py` (additive only)
* `gatepack/emit/kicad.py`
* `gatepack/cli.py` (`lib check` / `doctor` reporting only)
* `gatepack/refs.py`, `gatepack/parts.py` (only if the provenance model genuinely
  needs extending — prefer reusing it as-is)
* `tests/unit/test_pinmap.py` (new), `tests/unit/test_kicad*.py`,
  `tests/unit/test_refs*.py`
* `docs/BUILD-NOTES-pinmap.md`, `docs/handoff/notes-pinmap.md`

**Off-limits** (other agents are in them right now): `app/**`, `examples/**`,
`gatepack/synth/**`, `gatepack/verify/**`, `libraries/74aup.csv` and
`libraries/74aup.refs.md` — the electrical library is not yours to touch; you are
adding a *new* file beside it. Also always off-limits: `gatepack-design.md`,
`docs/*-FINDINGS.md`, `docs/MILESTONE-AUDIT.md`, `docs/GUI-AUDIT.md`,
`app/shared/api.ts`.

## Acceptance

1. `.venv/bin/python -m pytest -q` — **749 pass, 5 skip** at baseline, all still
   passing plus yours.
2. A test for **each** of the six consistency checks, each proven by an input
   that violates exactly that check and nothing else.
3. A test that a library with no pin map behaves identically to today —
   byte-identical KiCad output for a golden design.
4. A test that a placeholder pin map still produces the loud notice, and that
   removing the notice fails the test.
5. `gatepack lib check` reports the pin-map placeholder count; a test pins the
   number so it cannot silently drift to zero.
6. Two clean builds of a golden design still produce byte-identical output
   (§5.5, `scripts/repro_check.py`).

## The failure mode to avoid

This project has shipped nine pieces of machinery that reported a status while
measuring nothing. The version of that here is a `74aup.pins.csv` full of
confident pin numbers that nobody sourced, in a file whose header implies the
values are real, feeding a KiCad netlist someone fabricates a board from.
**If you cannot source a pin number, mark it placeholder and say so.** The
project already runs on placeholders; it is not a failure to add another. It is
a failure to add one that does not look like one.

## Output

`docs/BUILD-NOTES-pinmap.md` and `docs/handoff/notes-pinmap.md`: the data model,
every value you could not source and how you marked it, which consistency checks
you think are weakest, and the three things you are least confident about.
