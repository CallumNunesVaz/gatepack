# Review notes — the examples and Windows packages

Both delivered against `81dfac9`. Everything below was measured here.

## examples2 — accepted as delivered

Five new examples: `full_adder`, `seven_segment`, `gray_counter`,
`combination_lock`, `edge_detector`.

**The dangerous half of the task was avoided correctly.** `libraries/74aup.csv`
and `74aup.refs.md` are byte-identical — the diff is empty. No new part, no new
part number, no new electrical figure, so nothing had to be cited and nothing
was fabricated. That matches the independent finding in
`notes-examples-feasibility.md`: a seven-output decoder and a five-state machine
both verify on the existing cell set, because synthesis maps arbitrary boolean
expressions onto whatever gates exist.

All eleven examples verify green, run here with a harness that walks **every**
directory under `examples/` rather than a hand-listed set, preferring each
example's own `parts.csv`:

```
combination_lock passed   debounce passed        edge_detector passed
full_adder passed         gray_counter passed    mux2to1 passed
parity passed             pelican passed         power_sequencer passed
sequence_detector passed  seven_segment passed
--- 11 examples; failures: 0
```

That harness matters because `list_examples()` discovers any directory with a
`design.yaml` and gates nothing on it verifying — a broken example would ship
listed, as someone's first impression.

### Its top-flagged uncertainty, resolved

> "The seven-segment glyph table is standard to me but has no datasheet
> authority in scope (the new unit test catches *transcription* errors, not a
> wrong table)."

That was the right thing to worry about and the right thing to flag. Settled by
evaluating all seven segment expressions with the project's own parser across
all sixteen inputs and comparing against the hex seven-segment font written out
independently: **16 of 16 match**. Kept as
`test_seven_segment_glyphs_match_the_hex_font`, which fails when a single
minterm is removed from `seg_a`.

(My first attempt at this check produced a table of nonsense because I passed
`str` where `evaluate` takes `bool` and compared a `bool` to `'1'`. The design
was never at fault; the harness was.)

### Its second concern, unfounded — and what it uncovered

> "`gray_counter` … a non-zero initial gray code would mis-reset."

`gray_counter`'s initial state `G00` has code **0**, so every state bit resets
to 0 and `DFF_R` suffices. The general case is fine too: a probe with
`initial: G11` (code 3, both bits set) verifies green, and the mapped netlist
shows Yosys reaching for **`DFF_SR`** — which *is* in the shipped library
(`74AUP1G74`, second-sourced). Only `DFF_S` is excluded, for being
single-sourced. So the encoded path loads a non-zero initial code correctly.

**This bears on an earlier decision.** The `resetmut` package declined a
`DFF_SR` set-path mutation because no bundled example instantiates that cell,
which would have made the mutation `not_applicable` everywhere — a check
measuring nothing. Re-checked across all eleven examples: still `DFF_SR = 0`
everywhere, so that decision stands.

But the probe above shows the cheap way to change it: **an example using
`binary` or `gray` encoding with a non-zero initial state instantiates
`DFF_SR`**, which would make the set-path mutation applicable and worth adding.
That is a concrete route to closing a known gap, not a vague suggestion.

## windows — accepted, with its most valuable finding fixed here

In scope, and honest about its limits. Cross-compile *refusals* rather than fake
cross-builds, a `windows-core` CI job on `windows-latest`, Windows guidance in
`doctor`, `start.ps1`/`start.cmd`, `docs/WINDOWS.md`.

Verified here:

* `bundle_core.build_core(platform='win32')` on this Linux host raises rather
  than producing something — *"PyInstaller does not cross-compile … Build the
  win32 core on a win32 machine instead"*. Actionable, not a silent no-op.
* `run_doctor(platform='win32')` appends real guidance to each tool's purpose
  (OSS CAD Suite for yosys/sby, Icarus for Windows) and leaves the Linux output
  untouched. Testable on this host by injection, which was the requirement.
* `scripts/lint_workflows.py` passes on the changed workflow.
* `pwsh` is genuinely absent here, so its "launchers written blind" label is
  accurate. It stays **unverified** — I could not upgrade it either.

### Its out-of-scope finding was the important one

> "`gatepack/toolchain.py`'s `resolve_tool` doesn't check `.exe`, so a frozen
> Windows core wouldn't find a bundled `yosys.exe`."

Correct, and confirmed: both the bundled and `GATEPACK_TOOLS` branches used a
bare `d / name`. `shutil.which` applies `PATHEXT`, so a *system* install on
Windows always worked — which is why it hid. The case it broke is exactly the
one a self-contained installer exists to serve. Fixed in `f12c1da`, falsified,
with the suffix rule kept platform-specific so a missing tool on POSIX is still
reported missing.

## What remains unverified

* **No Windows machine has run any of this.** The NSIS installer, the
  `windows-core` CI job, `start.ps1` and `start.cmd` are all unexercised. The
  bundled `app/resources/bin/*` remain Linux ELF from the Debian bookworm
  archive (checked: all six are `\177ELF`), so a Windows install still depends
  on either the CI-built core or a user-installed toolchain.
* The seven-segment font is the *conventional* one, asserted against a table
  written independently rather than against a datasheet. Two independent
  derivations agreeing is not the same as a citation, and the example claims no
  more than that.
