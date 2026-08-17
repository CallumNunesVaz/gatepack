# Package: finish the pin-fit work — the masked-mutation question

Your previous run in this worktree stopped part-way through (the API account ran
out of credit, mid-investigation). **The work already in the tree is good and
has been reviewed — do not redo it.** This brief covers only what is left.

## What is already done and verified (leave it alone)

In `libraries/74aup.csv` and `libraries/74aup.refs.md`:

- `NAND3` and `NOR3` had their part number and `mfrs` cleared — correct, and
  independently confirmed: `74AUP1G10` 404s on both Nexperia's and TI's document
  servers, and `74AUP1G27` returns nothing. There is no AUP single 3-input
  NAND or NOR to buy.
- `AND3` corrected to `SOT-363` (74AUP1G11, 13 July 2023) — independently
  confirmed against the Nexperia product page and datasheet.
- `DFF_R` → `SOT-363` and `DFF_SR` → `VSSOP-8` — the F-tier cases, which you
  found yourself and which the arithmetic agrees with.
- The cited "Package pin counts" table, and
  `tests/unit/test_package_pin_fit.py`, which skips-and-reports an uncited
  package rather than guessing.

599 unit tests pass. All of that stands.

## What is left

### 1. The problem you were looking at when you stopped

Clearing `mfrs` on `NAND3`/`NOR3` makes them unsourced, so they drop out of the
default Liberty file and synthesis maps designs differently. That is the right
consequence — a cell you cannot buy should not be a synthesis target — and it
moves package counts. It also makes one bundled example fail:

```
$ gatepack verify examples/sequence_detector/design.yaml \
    --library examples/sequence_detector/parts.csv
passed   equivalence
passed   exhaustive simulation
failed   mutation   one or more mutations NOT detected: nand_to_and, reset_polarity_flip
passed   flop reset connectivity
passed   supervisor parameters
```

Two planted faults are not observable: equivalence and exhaustive simulation
both pass *with the mutation in place*.

**Work out why, and say which of these it is:**

- **The mutation is genuinely masked** — the mutated gate sits where the fault
  cannot propagate to an output in any reachable state (a redundancy, a
  don't-care region). Then verification is not "insensitive"; the fault is
  unobservable, and reporting it as a failure is the check describing itself
  wrongly. The honest fix is for the mutation check to distinguish *masked*
  from *undetected* — and to say which gate and why.
- **The verification really is insensitive** — the fault does reach an output
  but the checks do not look in the right place. Then the check is right to
  fail and the fix is elsewhere.

Do not guess between these. Determine it from the actual netlist and the actual
mutation: find which cell is mutated, and establish whether its output can
differ at a primary output in a reachable state.

### 2. Then resolve it, honestly

Whatever you conclude, the rule is absolute: **a mutation that was not detected
must never be reported as detected.** If you add a "masked" verdict, it must be
established by evidence (the fault provably cannot propagate), not assumed
because the checks passed — "the checks passed" is precisely what is in
question.

If the right fix is in `gatepack/verify/**`, you may make it — that restriction
is lifted for this run. Keep it minimal and covered by a test that fails without
it. If the right fix is to the example, say why changing the design is better
than fixing the check. If you cannot settle it, say so plainly and leave the
example failing rather than papering over it; an honest red is worth more than
a green that means nothing.

### 3. Re-measure every example and correct its header

Package counts have moved. Measured here after your changes:

```
pelican 19 (was 20)   debounce 13 (was 12)   sequence_detector 12 (was 14)
mux2to1 3             parity 2               power_sequencer 10
```

Every example's header comment states its package count, and several name the
specific parts ("three packages — a 1G04 and two dual-NAND 2G00s"). Those
comments are now wrong. Re-measure each, correct every count and part list to
what the build actually produces, and check the prose too — an example that
describes mapping onto a 3-input gate no longer does.

`tests/golden/test_showcase.py` and
`tests/toolchain/test_estimate_build_consistency.py` pin the showcase count.
Update them to the measured number and say in your notes what changed from what
to what, and why the new number is right.

### 4. Prove it

```
docker run --rm -u "$(id -u):$(id -g)" -v "$PWD:/repo" -w /repo \
  gatepack-toolchain:m6 python3 -m gatepack build ... --json
```

(The `-u` matters: without it the container writes root-owned files into the
checkout and your next local command fails with EACCES. The toolchain tests in
this worktree now route through `tests/toolchain/docker_runner.py`, which does
this for you.)

Required, with real output quoted:

- `gatepack lib check libraries/74aup.csv` passes.
- Every example builds with **no** acknowledgement flag, and verifies.
- `.venv/bin/python -m pytest tests -q` — report the count.
- The falsification of `test_package_pin_fit.py` you were asked for: plant a
  bad row, show the test catches it, quote it.

## Files you own

`libraries/**`, `examples/**`, `tests/**`, and `gatepack/verify/**` if and only
if section 2 leads there.

## Report

Write `docs/handoff/notes-pins.md`: the datasheets, the pin-count table sources,
the falsification, the masked-vs-insensitive determination and the evidence for
it, every package count that moved, and anything you could not settle.
