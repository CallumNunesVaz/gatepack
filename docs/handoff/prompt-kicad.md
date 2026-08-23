# Package I — make KiCad itself read the netlist (M10-1)

Read `docs/handoff/delegation-rules.md` first. Every rule there applies.

## What was descoped, and why

"KiCad import clean, including power symbols and no-connects" was an M10 exit
criterion. It was **descoped from v0.1.0 on 2026-08-16** with this reasoning:

> It cannot be tested here: it needs a human with KiCad installed, opening the
> emitted netlist and confirming that power symbols and no-connects survive.
> Rather than carry a milestone open indefinitely on a criterion no automated
> check can close, the criterion is removed from the v0.1.0 exit set.

The descope was honest and the README says plainly that the netlist is
unverified output. But the premise — *no automated check can close it* — is
worth attacking, because KiCad ships its own netlist reader as a Python module.

## The architecture

**Drive KiCad's own code, headlessly, in a container.**

KiCad's `pcbnew` Python module exposes the netlist reader and the board updater
that "Update PCB from Schematic" uses — the same code path a human triggers from
the GUI. If it can be driven from a script, then the check is not "a
hand-written parser agrees with our own emitter" (which proves nothing) but
"KiCad parsed this file and told us what it found".

Roughly:

1. `Dockerfile.kicad` — a pinned KiCad image (the `kicad/kicad` images on Docker
   Hub carry `pcbnew` and `kicad-cli`). Pin a specific tag and record it, the
   way `Dockerfile.probe` pins Yosys 0.23 and an sby commit. A floating `latest`
   makes every future result unreproducible.
2. A script that, inside that container, reads `out/netlist.net` from a real
   gatepack build with KiCad's own reader, applies it to an empty board, and
   reports: components found, footprints resolved, nets formed, power nets,
   no-connects, and every error or warning KiCad emitted.
3. `tests/toolchain/test_kicad_import.py` — the criterion as a test. Use
   `tests/toolchain/docker_runner.py` rather than hand-rolling `docker run`, and
   pass `-u "$(id -u):$(id -g)"` or the container leaves root-owned files in the
   checkout and the next local command fails with EACCES.
4. A CI job alongside `toolchain` in `.github/workflows/ci.yml`. It must **fail
   on a skip**, for the reason the existing `toolchain` job gives: a skip is
   indistinguishable from the test not existing.

## The three things that must be checked, not assumed

The descoped criterion named these specifically. Each needs its own assertion:

* **every component lands with its footprint** — and the refdes set matches
  `out/refdes.json` exactly, both directions;
* **power symbols survive** — the `VCC`/`GND` rails come through as nets with
  the members the emitter put on them, including the rail tie-offs
  `gatepack/emit/kicad.py` deliberately routes there;
* **no-connect flags survive** — the pins in the emitter's `no_connects` section
  arrive as no-connects and are *not* silently attached to a rail. That
  distinction is [R4-20] and it is the single most consequential thing in the
  file: a no-connect quietly turned into a rail connection is a short.

## The rule that outranks the task

**Never fake a tool result.** If the KiCad container cannot be obtained, or
`pcbnew`'s reader cannot be driven from a script in the version you pin, then:

* **say so plainly**, with the exact error, and
* **do not substitute a hand-written parser and present it as an import check.**

A parser you write validates that the file matches *your* understanding of the
format, which is the same understanding that produced it. It is circular and it
would close the criterion falsely — a worse outcome than leaving it descoped,
because the descope is at least honest.

A hand-written structural validator is welcome as an **additional** check,
clearly named as not-KiCad (`test_kicad_selfconsistency.py`, not
`test_kicad_import.py`), and it must never be what a CI job's name implies is an
import test.

Likewise: if KiCad reports warnings you do not understand, report them. Do not
tune the emitter until the warnings disappear without knowing what they meant —
that is fitting the output to the checker.

## What you may change in the emitter

`gatepack/emit/kicad.py` may be corrected where KiCad's own reader shows it is
wrong. That is the entire point of running the check. Two constraints:

* **Do not touch pin numbering.** Another agent is adding a footprint pin map in
  the same window; the positional-placeholder numbering and its
  `PIN_NUMBER_NOTICE` are theirs. If KiCad objects to the pin numbers, record it
  as a finding for that package rather than fixing it here.
* The emitted file stays deterministic and timestamp-free (§C6, §5.5).
  `scripts/repro_check.py` must still pass.

## Your file scope — nothing outside it

* `Dockerfile.kicad` (new), `scripts/kicad_import_check.py` (new)
* `gatepack/emit/kicad.py` (corrections shown to be needed by KiCad itself —
  not pin numbering)
* `tests/toolchain/test_kicad_import.py` (new), `tests/unit/test_kicad*.py`
* `.github/workflows/ci.yml`
* `docs/BUILD-NOTES-kicad.md`, `docs/handoff/notes-kicad.md`

**Off-limits**: `libraries/**`, `gatepack/pinmap.py` and anything pin-map
related, `gatepack/synth/**`, `gatepack/verify/**`, `examples/**`, `app/**`.
Also always off-limits: `gatepack-design.md`, `docs/*-FINDINGS.md`,
`docs/MILESTONE-AUDIT.md`, `docs/GUI-AUDIT.md`, `app/shared/api.ts`. The audit
records the descope decision; **you do not get to un-descope it** — you produce
the evidence and someone else updates the audit.

## Acceptance

1. `.venv/bin/python -m pytest -q` — **749 pass, 5 skip** at baseline, all still
   passing plus yours.
2. Either: a transcript of KiCad's own reader consuming a real
   `examples/pelican` build's netlist, with the component/net/no-connect counts
   it reported — or a clear statement of exactly what blocked it, with the error.
3. If it works: assertions for all three criteria above, each proven by an input
   that violates exactly that criterion (corrupt the netlist, watch the check
   fail). A check that has never rejected a bad netlist is not a check.
4. `scripts/repro_check.py` still passes; `scripts/lint_workflows.py` passes on
   your workflow change.
5. Every image tag pinned by digest or explicit version, recorded in the notes.

## Output

`docs/BUILD-NOTES-kicad.md` and `docs/handoff/notes-kicad.md`: what KiCad
actually said, what you changed in the emitter and why KiCad made you, what you
could not drive headlessly, and the three things you are least confident about.
If you conclude the criterion still cannot be closed automatically, say so
clearly — that is a legitimate and useful result, and it is better than a check
that closes it falsely.
