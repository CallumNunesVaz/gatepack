# Review notes — the two reset packages, and what measurement changed

Both delegated packages (`resetsim`, `resetmut`) were reviewed against the
acceptance criteria recorded in `3fe18b2` and `4a15c41`. Everything below is
measured in `gatepack-toolchain:m6`, not read off either agent's report.

## resetsim — accepted, both conditions met

The acceptance check was deliberately narrow: **exactly one cell of the
eighteen-cell mutation table may move.**

`before` (integration, `gatepack/verify/simulation.py` untouched) reproduced the
table in `notes-resetprobe.md` cell for cell. `after` differed in exactly one:

```
sequence_detector  reset_polarity_flip:  caught by equivalence only -> detected
```

Seventeen cells unchanged, `nand_to_and` on `sequence_detector` still
equivalence-only — the brief's canary for an over-eager testbench held.

The second condition was that the verdict move *because the simulation started
failing*, not via verdict logic. `mutation.py`, `base.py` and `synchronous.py`
are byte-identical between the two trees (checked, not assumed), so
`is_detected` is unchanged; it returns true only when `simulation is FAILED`,
and `is_equivalence_only` only when `simulation is PASSED`. A move between those
two verdicts is therefore a change in the simulation result and nothing else.

The two claims the package derives from the emitter were checked against
`gatepack/frontend/verilog.py` directly: `_emit_one_hot_state` clears every
state bit (so no `state == S` predicate holds during reset — `None` is right),
`_emit_encoded_state` loads `STATE_<initial>` (so binary/gray reset *is* a real
state), and the input synchronisers clear to 0. All three match.

## resetmut — accepted, but the distinctness claim was false as delivered

`4a15c41` required the difference between `reset_never_asserts` and
`reset_polarity_flip` to be **demonstrated on a real design, not argued**. The
package argued it in a docstring. Measured, the picture was worse than
suspected — and worse for all four reset mutations, not just that pair.

Running each mutation against one design and diffing the actual Icarus traces:

| topology | distinct traces |
|---|---|
| `sync_deassert: true` — **every bundled example** | **1 of 4** |
| `sync_deassert: false` — state flops on the raw pin | 3 of 4 |

On the §9.3 default the four reset mutations are byte-identical faults. The
two-flop synchroniser is the reason: `reset_polarity_flip` makes the
synchroniser's own flop drive itself to 0, pinning the synchronised reset low,
so the state flops become plain flops — the same end state every other reset
mutation produces. The bundled example suite is *structurally* unable to tell
the reset family apart, and no amount of adding mutations to it would help.

Even off the synchroniser, `reset_never_asserts` and `reset_becomes_synchronous`
still coincided. The cause was in the *stimulus*, not the mutations: **nothing
in the testbench ever clocked an edge while reset was asserted**, so "reset is
synchronous" and "reset is absent" had no observable difference.

## What I added

One clock edge, taken with reset still held, and a second comparison after it —
`FAIL: <output> held in reset`. §9.3 asserts asynchronously, so any number of
edges under reset leaves the reset outputs unchanged; that is a real property
and nothing else was checking it.

With it, on a design that moves into its output-true state on the next edge:

```
reset_polarity_flip        -> {o at step 0, o held in reset}
reset_never_asserts        -> {o at step x, o during reset, o held in reset}
reset_becomes_synchronous  -> {o at step x, o during reset}
reset_value_flips          -> {o at step 1, o during reset, o held in reset}
                                            distinct traces: 4 of 4
```

`reset_becomes_synchronous` is the only one with no `held in reset` failure — a
synchronous reset clears *on* the held edge and matches the golden design from
there, while an absent reset takes `D` and does not. That one line is the whole
distinction. Removing the held edge collapses the pair back to 3 of 4, which is
pinned by `test_the_reset_family_are_four_distinct_faults` (verified to fail
without it).

Re-measured afterwards: the eighteen-cell invariant still holds — restricted to
the original three mutations, exactly one cell moved, the intended one.

## The set-path rejection was right

`resetmut` declined the `DFF_SR`/`DFF_S` set-path mutation the brief proposed,
on the grounds that nothing instantiates those cells. Checked by building all
six examples and grepping `mapped.v`:

```
debounce 0   mux2to1 0   parity 0   pelican 0   power_sequencer 0   sequence_detector 0
                    (DFF_R: 8, 0, 0, 11, 6, 6)
```

Zero. A set-path mutation would report `not_applicable` on every design — a
check that measures nothing, which is the defect this whole area exists to
prevent. Worth revisiting the moment a design instantiates `DFF_SR`.

## Limits, stated rather than papered over

- The reset probe drives every input to 0. A design whose reset-phase output
  depends on a *non-sync* input is only probed at that one assignment.
- `binary`/`gray` reset (`_reset_state` returning the initial state) has unit
  coverage but no bundled example: all six are one-hot.
- The four reset mutations remain one indistinguishable fault on every bundled
  example. They separate only off the reset synchroniser, which is why the
  distinctness test carries its own `sync_deassert: false` design.
