# Probe: what `reset_polarity_flip` actually does to `sequence_detector`

Measured in the main tree at `5e23a49`, before either reset package landed, so
it is an independent "before" rather than a restatement of a delegated result.

## The baseline verdicts

```
$ gatepack verify examples/sequence_detector/design.yaml --library .../parts.csv
  mutation nand_to_and:      caught by equivalence only
  mutation flop_d_invert:    detected
  mutation reset_polarity_flip: caught by equivalence only

$ gatepack verify examples/pelican/design.yaml --library .../parts.csv
  mutation nand_to_and:      detected
  mutation flop_d_invert:    detected
  mutation reset_polarity_flip: detected
```

`reset_polarity_flip` is **already detected on pelican**. Measured across all
six bundled examples:

| example           | nand_to_and    | flop_d_invert  | reset_polarity_flip |
|-------------------|----------------|----------------|---------------------|
| debounce          | detected       | detected       | detected            |
| mux2to1           | detected       | not applicable | not applicable      |
| parity            | not applicable | not applicable | not applicable      |
| pelican           | detected       | detected       | detected            |
| power_sequencer   | not applicable | detected       | detected            |
| sequence_detector | eq only        | detected       | **eq only**         |

`sequence_detector` is the **only** design where the reset fault escapes the
simulation. The coverage gap is design-dependent, not universal, and the same
holds in the other direction: `nand_to_and` is detected on pelican and
unobservable on `sequence_detector`. Any claim that "the simulation cannot catch
reset faults" is too strong; the accurate claim is that it cannot catch them *on
designs where the fault is confined to the reset window*.

This makes the acceptance check precise: exactly one cell of that table may
change (`sequence_detector` / `reset_polarity_flip`, eq only -> detected), and
the other seventeen must be identical afterwards. A change anywhere else is a
regression or an over-strict testbench, not a bonus.

## The behaviour, measured

`probe_tb.v` drives the reset flush exactly as the real testbench does, walks
the 1-0-1 pattern, then asserts reset **without a clock edge**:

```
                     GOLDEN      MUTATED
after flush:         match=0     match=0
din=1 ->             match=0     match=0
din=0 ->             match=0     match=0
din=1 (expect 1):    match=1     match=1
reset asserted:      match=0     match=1     <- the only divergence
```

Clocked operation is **bit-identical**. The fault is visible only while reset is
asserted, and visible there with no clock edge at all.

## Why — and this is the part that matters

From `build/mapped.v`: the four state flops take `.RST_N(rst_n_s2)`, the
*synchronised* reset, while the two synchroniser flops `_21_`/`_22_` take the
raw `.RST_N(rst_n)`. That is the §9.3 async-assert / sync-de-assert chain.

With the mutation (`if (RST_N) Q <= 1'b0; else Q <= D;`):

- Synchroniser flop `_21_` has `D = 1'h1` and `RST_N = rst_n`. In normal
  operation `rst_n` is high, so `if (RST_N)` is **true** and it drives its own
  output to 0. `rst_n_s1` and then `rst_n_s2` sit at 0.
- The state flops therefore see `RST_N = rst_n_s2 = 0`, so `if (RST_N)` is
  **false** and they take `else Q <= D` — they are ordinary flops with no reset.
- Asserting raw `rst_n` changes nothing without a clock edge, so the state flops
  simply hold. `match` stays wherever it was.

So the mutation does not "invert the reset". It **disables the entire reset
network**, and it does so in a way that leaves clocked behaviour untouched. The
mutated design is a machine that never resets.

I had predicted the opposite before measuring — that the mutated flops would
clear on every clock edge and wreck normal operation. They do not, because the
fault lands on the synchroniser flops first and neutralises the chain feeding
the state flops. The measurement is narrower than the prediction and makes the
case for a reset-assertion check stronger, not weaker.

## Consequence for the `resetmut` package

Its brief proposes a "**the reset never asserts**" mutation (drop the clear, so
the flop is a plain `DFF`), listed as distinct from flipping polarity. On this
topology that may be **the same fault**: the polarity flip already ends in "no
reset at all". If both mutations produce the same observable behaviour, the
suite grows without gaining discrimination.

Review point, not a verdict — the two could still differ on a design whose
synchroniser flops are reset differently, or on the binary-encoded path. Whoever
merges that package should require the difference be demonstrated on a real
design, not argued.

## Consequence for the `resetsim` package

The expected value the brief gave it is confirmed: during reset assertion the
golden design reads `match=0`, because every one-hot state bit clears and
`state == S3` is false. Checking outputs while reset is asserted, before the
next clock edge, catches this fault. Nothing else in the simulation can.
