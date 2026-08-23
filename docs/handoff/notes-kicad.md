# Handoff notes — KiCad import check (Package I, M10-1)

Short form for the next reader: **KiCad does not expose its netlist reader to
any headless interface, so the descoped criterion still cannot be closed
automatically — and that is now a *measured* fact, not the 2026-08-16 premise.**

## One-line answer to the brief

The brief said "KiCad's `pcbnew` Python module exposes the netlist reader". It
doesn't. I ran real KiCad 9.0.9 (and 10.0.5): `pcbnew` has zero netlist symbols,
`kicad-cli` has no netlist-import command, and the reader is not even compiled
into `_pcbnew.so`. So I produced the *blocked* outcome the "rule that outranks
the task" describes, with the exact error, and did not fake an import.

## What shipped

- `Dockerfile.kicad` — pinned `kicad/kicad:9.0.9` by digest; documents the
  finding and is the CI build target.
- `scripts/kicad_import_check.py` — probes `pcbnew` for a headless reader;
  exits `2` ("blocked") today, `0`/`1` would be the future import. The real
  import (three criteria) is the marked "would-do" section, unimplemented.
- `tests/toolchain/test_kicad_import.py` — runs the probe in the pinned image;
  fails the day a reader appears (message tells you to implement the import).
- `tests/unit/test_kicad_selfconsistency.py` — **not-KiCad** structural check:
  refdes ⇄ `refdes.json` both directions, power rails intact, no-connects never
  silently on a rail. Each criterion has a corrupt-input test that fails it.
- `tests/toolchain/docker_runner.py` — one backward-compatible `image=` override.
- `.github/workflows/ci.yml` — `kicad-import` job (fail-on-skip), header updated
  "Four jobs" → "Five jobs".

## What I deliberately did NOT do

- **Did not touch `gatepack/emit/kicad.py`.** I have no KiCad reader to justify
  a correction against, and "fixing" the format against my own knowledge is
  exactly the fitting-output-to-a-checker the brief forbids. Pin numbering left
  alone for the pin-map package.
- **Did not present a hand-written parser as an import check.** The
  self-consistency test is named `..._selfconsistency`, lives under the plain
  `test` job, and says in its docstring that it proves nothing about KiCad.

## A finding for whoever un-descopes the criterion

The emitted `.net` is almost certainly invalid KiCad, and here is why an EDA
engineer can say so *without* running KiCad (flag: unverified by KiCad, since I
could not run the reader):

1. `(export "version" "gatepack-0.1.0")` — KiCad wants `(export (version D))` /
   `(export (version "E"))`; `version` is a keyword, the value a format letter.
2. Quoted key/atom pairs (`"ref" "U1"`, `"code" 1`, `"name" "GND"`) throughout,
   where KiCad uses bare keywords in sub-lists — `(comp (ref U1) ...)`,
   `(net (code 1) (name "GND") ...)`.
3. `(no_connects …)` / `(no_connect …)` is not a KiCad section or node form; a
   KiCad no-connect is a pin absent from every net.
4. `design`/`libparts`/`libraries` carry the quoted-key shape and omit fields
   KiCad expects (`date`, `tool`, a proper `sheet`, `description`).

The emitter will need to emit KiCad's real legacy (or modern) netlist shape
before any import can succeed — this note is the evidence, not the fix.

## Test counts

Baseline `778 pass / 5 skip`. After this package: **`789 pass / 5 skip`**
(10 self-consistency + 1 KiCad-import probe). `scripts/repro_check.py` and
`scripts/lint_workflows.py` both still pass.

## The three things I am least confident about

1. Reader absence being permanent (two releases checked, not nightlies — re-run
   the probe against `kicad/kicad:nightly` to settle it).
2. Whether the `kicad-import` CI job should be *red* until the criterion closes
   (I chose a guard test + loud comments; a reviewer may want a hard red).
3. That my four format divergences are the *complete* list of what KiCad would
   reject; only the real reader can rank them.

## Proofs that matter

- `.venv/bin/python -m pytest -q` → `789 passed, 5 skipped`.
- `scripts/kicad_import_check.py` against `kicad/kicad:9.0.9` prints the six
  absent symbols and exits `2` (transcript in `docs/BUILD-NOTES-kicad.md`).
- `tests/unit/test_kicad_selfconsistency.py` corrupts the netlist six ways and
  each corruption fails exactly its criterion.
