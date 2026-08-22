# Reset mutation family — handoff notes

Extends `gatepack/verify/mutation.py`'s reset mutation family from one fault
(`reset_polarity_flip`) to four, and pins the whole `MUTATIONS` tuple with a
stronger test that catches a silently no-op `str.replace`. No verdict logic
changed; `base.py` / `synchronous.py` / `simulation.py` are untouched.

## Files changed

- `gatepack/verify/mutation.py` — three new `Mutation` entries
  (`reset_never_asserts`, `reset_becomes_synchronous`, `reset_value_flips`),
  all pure text transforms on `cells.lib` + `cells_sim.v`, all targeting
  `DFF_R` (the async-clear flop the one-hot state machines actually
  instantiate).
- `tests/unit/test_verify.py` — strengthened
  `test_mutations_all_change_both_artefacts` (now asserts *both* artefacts
  change, not one-or-the-other) and added five tests for the new mutations.

## Mutations added, and the real implementation error each stands for

| mutation | what it changes | the implementation error it models |
| --- | --- | --- |
| `reset_never_asserts` | drops the async clear entirely; `DFF_R` becomes a plain `DFF` | **the reset was never wired** — the reset pin is in the netlist but does nothing. Distinct from `reset_polarity_flip`, which keeps a reset but inverts it. |
| `reset_becomes_synchronous` | moves the clear inside `posedge CK`; async-assert becomes sync reset | **async vs sync reset mix-up** — §9.3 promises async-assert / sync-de-assert, and a sync reset is a real, common implementation error. A suite that cannot tell the two apart is not verifying the promise. |
| `reset_value_flips` | the clear asserts `1'b1` instead of `1'b0` (Liberty `clear` → `preset`) | **wrong reset value** (a clear/preset confusion, or an inverted reset constant). On the one-hot path every state bit clears to 0, so resetting to 1 leaves a physically impossible all-1 encoding. |

Each is a single `str.replace` on each artefact. The `DFF_R` ff block and
`always` block are captured once as module constants (`_DFF_R_FF`,
`_DFF_R_ALWAYS`) and each mutation supplies its own "after" text, so the three
share the anchor but cannot silently drift. The anchors are chosen so they do
**not** collide with `DFF_SR` (which has a `preset` and an `else if` line).

## Candidates considered and rejected

- **Set/preset path on `DFF_SR`/`DFF_S`** (candidate 4) — rejected. `DFF_S` is
  single-sourced and excluded from the shipped Liberty file, and no bundled
  example instantiates `DFF_SR` (grep over every `mapped.v` finds zero
  `DFF_SR`/`DFF_S` instances: the one-hot state flops are reset-to-0 `DFF_R`
  via set-via-feedback, and `CNT4`/`SR4` are M-cells, not F-cells). A
  set-path mutation would therefore report `not_applicable` on every design
  and never run a check — it would be a check that measures nothing, which is
  precisely the defect this package exists to prevent. Worth revisiting the
  moment a design instantiates `DFF_SR`.
- **A combined "reset polarity + value + sync" mega-fault** — rejected; three
  separate, physically-motivated faults are more diagnostic than one blob, and
  a blob would make the verdict table unreadable.

## Measured verdict tables (real toolchain output)

Command (run with the pinned docker image; `-u` to keep file ownership sane):

```
docker run --rm -u "$(id -u):$(id -g)" -v "$PWD:/repo" -w /repo \
  gatepack-toolchain:m6 python3 -m gatepack verify \
  examples/<name>/design.yaml --library examples/<name>/parts.csv
```

### `sequence_detector` (sequential, one-hot, `DFF_R`, no sync inputs)

```
verification: passed
  equivalence:               passed
  exhaustive simulation:     passed
  mutation:                  passed
      all applicable mutations detected or caught by equivalence alone
  mutation nand_to_and:      caught by equivalence only
  mutation flop_d_invert:    detected
  mutation reset_polarity_flip: caught by equivalence only
  mutation reset_never_asserts: caught by equivalence only
  mutation reset_becomes_synchronous: caught by equivalence only
  mutation reset_value_flips: caught by equivalence only
```

### `pelican` (five-state showcase, sync inputs `request`/`hold`)

```
verification: passed
  equivalence:               passed
  exhaustive simulation:     passed
  mutation:                  passed
      all applicable mutations detected or caught by equivalence alone
  mutation nand_to_and:      detected
  mutation flop_d_invert:    detected
  mutation reset_polarity_flip: detected
  mutation reset_never_asserts: detected
  mutation reset_becomes_synchronous: detected
  mutation reset_value_flips: detected
```

### `parity` (combinational, no flops, no `NAND2`)

```
  mutation nand_to_and:      not applicable
  mutation flop_d_invert:    not applicable
  mutation reset_polarity_flip: not applicable
  mutation reset_never_asserts: not applicable
  mutation reset_becomes_synchronous: not applicable
  mutation reset_value_flips: not applicable
```

### `mux2to1` (combinational, uses `NAND2`)

```
  mutation nand_to_and:      detected
  mutation flop_d_invert:    not applicable
  mutation reset_polarity_flip: not applicable
  mutation reset_never_asserts: not applicable
  mutation reset_becomes_synchronous: not applicable
  mutation reset_value_flips: not applicable
```

(`debounce` and `power_sequencer` were also run: all six mutations `detected`,
`verify` passed with the bundled library. `power_sequencer` with its **own**
`parts.csv` fails the *base* equivalence check — a pre-existing condition
unrelated to this package, not investigated here.)

## The verdicts are the expected result, not a target

Nothing came back **undetected** — equivalence caught every applicable
mutation, so the checks are not insensitive to the reset family. The split
between "detected" and "caught by equivalence only" is design-dependent and,
as measured, entirely consistent with the known reset-blindness of the
exhaustive simulation (the other agent is extending it to check the reset
assertion phase):

- **`sequence_detector`** has no synchronised inputs (`din` is `sync: false`),
  so its only flops are the state flops and the reset de-assert synchroniser.
  A reset fault leaves those self-healing: the one-hot set-via-feedback
  (`state_S0 <= next_S0 | ~state_active`) recovers a valid `S0` from the
  all-zero encoding regardless of the fault, and the post-reset outputs the
  simulation checks are unchanged. Equivalence (which compares the full state
  space, including the reset phase) sees the fault; the output-only simulation
  does not look. Hence "caught by equivalence only" — exactly the verdict the
  prompt predicted.
- **`pelican`** has synchronised inputs, so the reference model in the
  simulation assumes the input-synchroniser flops start cleared after reset.
  A reset fault that leaves those flops at `x` (rather than `0`) makes the FSM
  read a different effective input than the reference model predicts, and the
  output mismatch is caught at a transition edge. Hence "detected".

I confirmed the `sequence_detector` "equivalence only" results are genuinely
*caught by equivalence* (not a miss) by running the mutated `cells_sim.v`
through Yosys directly: each of the three new faults yields
`ERROR: Found N unproven $equiv cells` (non-zero exit), while the unmutated
model proves equivalent.

## `cells_sim.v` diffs each mutation produces

All three fire on the `DFF_R` model in the generated `cells_sim.v` (the
`before` is the C2-emitted block, the `after` is what the mutation writes):

```
reset_never_asserts
-  always @(posedge CK or negedge RST_N) begin
-    if (!RST_N) Q <= 1'b0;
-    else Q <= D;
+  always @(posedge CK) begin
+    Q <= D;

reset_becomes_synchronous
-  always @(posedge CK or negedge RST_N) begin
+  always @(posedge CK) begin

reset_value_flips
-    if (!RST_N) Q <= 1'b0;
+    if (!RST_N) Q <= 1'b1;
```

The matching `cells.lib` changes (the Liberty file is never read by either
check, but it must change so the mutation is honest and the no-op test fires):
`reset_never_asserts` deletes the `clear` line; `reset_becomes_synchronous`
deletes `clear` and rewrites `next_state` to `"(RST_N & D)"`; `reset_value_flips`
rewrites `clear : "!RST_N"` to `preset : "!RST_N"`. In every case only the
`DFF_R` entry changes — `DFF_SR`'s `clear`/`preset` are left intact (pinned by
`test_reset_family_mutations_target_only_dff_r`).

## Cost of the flat `MUTATIONS` tuple

The suite runs every mutation against every design, so adding three mutations
roughly doubles the mutation phase. Measured wall-clock for the full `verify`
(which includes synthesis + base equivalence + base simulation + the mutation
phase):

- `sequence_detector` (6 applicable mutations): **~1.0 s**
- `pelican` (6 applicable mutations): **~3.7 s**

That is dominated by Yosys/Icarus startup, not by the number of mutations. The
flat module-level tuple stays: at six entries it is still one readable list,
the order is meaningful (combinational → flop data → reset family), and the
per-mutation cost does not justify restructuring.

## Tests

- Before: `706 passed, 5 skipped`.
- After: **`711 passed, 5 skipped`**.

The strengthened `test_mutations_all_change_both_artefacts` now asserts
`lib2 != lib` **and** `sim2 != sim` for every mutation in `MUTATIONS` (the old
test allowed a mutation to change only the Liberty file, which no check reads,
and still pass). Five new tests pin the three new transforms, that they target
only `DFF_R`, and that they report `not_applicable` on a combinational netlist.

## Three things I am least confident about

1. **Why `reset_value_flips` is "equivalence only" on `sequence_detector`.** I
   measured that it is (equivalence fails, simulation passes), and I believe
   the reason is the one-hot self-healing plus no synchronised inputs. But I
   have not excluded the possibility that the simulation passes because of
   Icarus's `x`-propagation in the combinational next-state cloud rather than
   for the structural reason I wrote down. The equivalence failure is solid
   either way; the *simulation* explanation is my best reconstruction.
2. **The Liberty encoding of "sync reset" as `next_state : "(RST_N & D)"`.** It
   is honest, but nothing in this repo re-reads a mutated Liberty file, so that
   representation is unverified against any Liberty consumer. If it matters, a
   real Liberty parser's treatment of a folded-in reset should be checked.
3. **Rejecting the `DFF_SR` set/preset path.** I argued it is dead weight today
   (zero instantiations), but that means the *first* design to use `DFF_SR`
   will have a set-path mutation gap that nobody will notice until then. The
   rejection is correct under "a check that cannot fire is worth nothing", but
   it trades future coverage for honesty now.
