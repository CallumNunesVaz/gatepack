# BUILD-NOTES — KiCad import check (Package I, M10-1)

What I built, what KiCad actually said, what I changed, and what I could not verify.

## The question this package set out to answer

The v0.1.0 exit criterion "KiCad import clean, including power symbols and
no-connects" was descoped on 2026-08-16 on the premise that *no automated check
can close it* — it needs a human with KiCad. The counter-argument was that KiCad
ships its own netlist reader as a Python module (`pcbnew`), so driving it
headlessly would let an automated check close the criterion with KiCad's own
code, not a hand-written parser.

## What KiCad actually said (measured, not assumed)

I pinned and ran real KiCad — `kicad/kicad:9.0.9` (cross-checked `10.0.5`) — and
probed `pcbnew` for a headless netlist reader. The result is unambiguous:

```
pcbnew 9.0.9: no headless netlist reader is exposed.
  pcbnew.NETLIST_READER: absent
  pcbnew.PCB_NETLIST: absent
  pcbnew.KICAD_NETLIST_READER: absent
  pcbnew.LEGACY_NETLIST_READER: absent
  pcbnew.COMPONENT: absent
  pcbnew.LoadFootprintsFromNetlist: absent
  NETLIST mentions in pcbnew.py: 0
```

Every line is a real probe result:

* `dir(pcbnew)` contains no `NETLIST` symbol at all; `grep -c NETLIST
  pcbnew.py` is `0`.
* `strings _pcbnew.so` shows none of `LoadFootprintsFromNetlist`,
  `NETLIST_READER`, `PCB_NETLIST`, `KICAD_NETLIST_READER`,
  `LEGACY_NETLIST_READER` — the reader is not even compiled into the SWIG
  module.
* `kicad-cli` has no netlist-import command: `kicad-cli pcb import` is only for
  non-KiCad board formats (`auto, pads, altium, eagle, cadstar, fabmaster,
  pcad, solidworks`), and `kicad-cli sch export netlist` *exports* a netlist
  from a schematic, it does not read one.
* The only netlist-ish Python file shipped is
  `/usr/share/kicad/plugins/kicad_netlist_reader.py`, which parses the **XML**
  intermediate netlist used by BOM plugins (`import xml.sax`) — not the
  s-expression `.net` this project emits.

**Conclusion: the criterion still cannot be closed automatically.** The premise
in the brief — "KiCad's `pcbnew` Python module exposes the netlist reader and
the board updater" — is false for KiCad 9.0.9 and 10.0.5. "Update PCB from
Schematic" is a GUI-only code path; its netlist reader is not scriptable.

Per the rule that outranks the task, I did **not** substitute a hand-written
parser and call it an import check. That would close the criterion falsely —
worse than leaving it descoped.

## What I shipped instead

1. **`Dockerfile.kicad`** — pinned `kicad/kicad:9.0.9` by digest (recorded
   below), documenting the finding so the next person does not re-derive it. It
   is the CI build target for the probe test.

2. **`scripts/kicad_import_check.py`** — runs inside the KiCad image, probes
   `pcbnew` for a headless reader, and reports. Exit codes: `0` import ran+passed
   (never reached), `1` import ran+failed (never reached), `2` **blocked — no
   headless reader** (what it returns today), `3` precondition error. The
   "would-do" import section is clearly marked unimplemented until a KiCad
   release exposes the reader.

3. **`tests/toolchain/test_kicad_import.py`** — feeds a real emitter-produced
   `netlist.net` to the probe inside the pinned image and asserts the honest
   "blocked" (exit 2) state. This test has teeth: if a future KiCad exposes the
   reader, the probe stops reporting "blocked" and the test fails with a message
   saying to implement the real import. It skips only when the image is not
   built (never faked).

4. **`tests/unit/test_kicad_selfconsistency.py`** — the *additional* check the
   brief permits, explicitly named not-KiCad. A hand-written s-expression parser
   reads the emitted `.net` and checks it against itself and against
   `refdes.json`:
   * refdes set matches `refdes.json` values in **both** directions, and every
     component has a footprint;
   * `VCC`/`GND` rails exist and every component's power pin is on its rail;
   * every `no_connect` names a real pin and is attached to **no** net — with
     the rail case called out, since a no-connect quietly turned into a rail
     connection is a short ([R4-20]).
   Each criterion has a corruption input that violates exactly that criterion
   (drop a footprint, drop a GND node, move a no-connect onto the VCC rail, …),
   so a validator that silently stops detecting would fail the test.

5. **`tests/toolchain/docker_runner.py`** — one small extension: `run` /
   `run_repo` / `run_work` take an optional `image=` override (default the
   toolchain image), so the KiCad probe reuses the same `-u uid:gid` mount
   discipline instead of hand-rolling `docker run`. Backward compatible; no
   existing call site changed.

6. **`.github/workflows/ci.yml`** — a `kicad-import` job that builds the pinned
   image and runs the probe with the same fail-on-skip guard the `toolchain` job
   uses.

## What I changed in the emitter: nothing

The brief allows correcting `gatepack/emit/kicad.py` **where KiCad's own reader
shows it is wrong**. I could not run KiCad's reader, so I have no KiCad verdict
to correct against, and I did not "fix" the emitter against my own mental model
of the format — that would be fitting output to a checker I never ran. The
emitter and its `PIN_NUMBER_NOTICE` are untouched.

### A suspicion I record but could not prove

The emitted file is almost certainly *not* valid KiCad netlist syntax. An EDA
engineer can see this without running KiCad, but I flag it as **unverified by
KiCad** because the reader is not scriptable:

* `(export "version" "gatepack-0.1.0")` — KiCad writes `(export (version D))`
  (legacy) or `(export (version "E"))` (modern): `version` is a keyword, not a
  quoted atom, and the value is a format letter, not a project string.
* Keys are quoted atoms throughout (`"ref"`, `"value"`, `"code"`, `"name"`) where
  KiCad uses bare keywords in their own sub-lists — `(comp (ref U1) (value ...)
  ...)`, `(net (code 1) (name "GND") ...)`. Quoted key/atom pairs are the
  emitter's own shape, not KiCad's.
* `(no_connects …)` is not a KiCad netlist section at all. In a KiCad netlist an
  unconnected pin is simply absent from every net; there is no
  `no_connect` node form.
* `design` lacks the fields KiCad expects (`source`/`date`/`tool` and a proper
  `sheet`), and `libraries`/`libparts` use the quoted-key shape.

If the criterion is ever un-descoped, the emitter will need to emit KiCad's
actual legacy (or modern) netlist shape. This note is the evidence that it does
not today; it is not a fix.

## What I could not drive headlessly

Everything that would close the criterion: KiCad's netlist reader, its board
updater ("Update PCB from Schematic"), and any report of components/nets/
no-connects as KiCad would parse them. The probe proves the reader is absent
from every headless interface; a source-level SWIG bind of `pcb_netlist.h` would
be a KiCad upstream change, not something this package can do in CI.

## Pinned image tags (all resolved, none floating)

* `kicad/kicad:9.0.9` @ `sha256:e638b79b0321f29395a5b783e94bb9f3c73303e8da15da27b8f5cb4b67a37729` (pinned in `Dockerfile.kicad`)
* `kicad/kicad:10.0.5` @ `sha256:182c8005cb775a2c448a4c18681d489f1ff472a761885eba3e08b07e3c0564de` (cross-checked, same absence)

## The three things I am least confident about

1. **That KiCad 9/10's reader absence is permanent.** I verified two current
   releases; I did not verify older releases or future nightlies. A KiCad
   nightly might already bind the reader. What would settle it: re-run the probe
   against `kicad/kicad:nightly` and read `pcbnew/swig/pcbnew.i` upstream.
2. **The exact list of what a future KiCad would reject.** My four divergences
   above are expert observation, not KiCad output; the first thing to break a
   real import may be something else (pin numbering, the `gatepack` logical
   library name, the missing `libsource` description). Only running the real
   reader can rank them.
3. **Whether the CI job should be red.** Today the `kicad-import` job is *green*
   while the criterion is *open*. I chose a guard test (fails the moment the
   reader appears) plus loud comments over a permanently red job, but a
   reviewer may reasonably prefer the job to fail until the criterion actually
   closes. That is a policy call I could not make unilaterally.
