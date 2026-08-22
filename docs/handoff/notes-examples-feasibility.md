# Finding — the existing library realises these circuits with no new parts

Measured while `deepseek/examples2` was running, so it is an independent check on
what that package claims it needs. Two candidate circuits, written here and run
through the real toolchain in `gatepack-toolchain:m6`.

## Wide multi-output combinational — a BCD to seven-segment decoder

4 inputs, **7 outputs**, 16 minterms, seven independent sum-of-products
expressions in `output_logic`.

```
verification: passed
  equivalence:               passed
  exhaustive simulation:     passed
  mutation:                  passed
  flop reset connectivity:   passed
  supervisor parameters:     passed
  mutation nand_to_and:      detected
  (the flop and reset mutations: not applicable — no state)
```

## Non-trivial sequential — a coin-operated vending controller

Five states, eleven transitions, two `sync: true` inputs (so the §9.3
synchronisers are exercised), two state-dependent outputs.

```
verification: passed
  equivalence:               passed
  exhaustive simulation:     passed
  mutation:                  passed
  mutation nand_to_and:              detected
  mutation flop_d_invert:            detected
  mutation reset_polarity_flip:      detected
  mutation reset_never_asserts:      detected
  mutation reset_becomes_synchronous: detected
  mutation reset_value_flips:        detected
```

All six mutations detected — it is a better mutation-suite exercise than any
bundled example except `pelican`.

## What this settles for the review

Both ran against `libraries/74aup.csv` **unmodified**. Neither needed a new
cell, a new part number, or a single new electrical figure. The existing set —
`INV BUF AND2 AND3 NAND2 NAND3 NOR2 NOR3 OR2 XOR2 MUX2`, the `DFF` family,
`CNT4`, `SUPERVISOR`, `OSC` — covers wide combinational logic and multi-state
sequential logic alike, because synthesis maps arbitrary boolean expressions
onto whatever gates exist.

So a claim that a new example *requires* a new part is a claim to check, not to
accept. Ask what the design does that a seven-output decoder and a five-state
machine do not. Legitimate answers exist — a design needing a genuine macro
block, or a part whose absence forces an absurd gate count — but "I added a
NAND4 because the expression had four terms" is not one: `abc` factors that onto
the gates available.

Reject any new row whose electrical figures are not marked placeholder exactly
as the existing rows are, and any packaging claim (`gates_per_pkg`, `package`)
without a cited datasheet revision and table. `74aup.refs.md` is explicit that
packaging is gated on its own citation because a wrong `gates_per_pkg` produces
a netlist that physically cannot be built.

## Not a rejection of new parts in principle

If the package makes a *cited* addition — real document, real revision, real
table — that is a genuine improvement and should be accepted on its evidence.
The point is only that the bar is the citation, and that convenience is not a
reason to cross it.
