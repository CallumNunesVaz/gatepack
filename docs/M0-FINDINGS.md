# M0 spike — measured findings

**Date:** 2026-08-15
**Toolchain:** Yosys 0.23 (git sha1 7ce5011c24b), Icarus Verilog 11.0, in a
Debian bookworm-slim container.
**Status:** These are *measurements from real runs*, not inferences. Where a
result is version-dependent it is marked. They supersede any conflicting claim
in `gatepack-design.md` or `docs/reviews/`.

§22 defined M0 as answering two questions before code was written on assumption.
The code was written first, so these answers arrive as corrections rather than
as inputs. That is the cost of skipping the spike.

---

## 1. Attributes before a continuous `assign` are a syntax error

```verilog
(* src = "x.yaml:1:out" *)
assign y = ~a;          // ERROR: syntax error, unexpected TOK_ASSIGN
```

The same attribute before a `wire` declaration parses cleanly. IEEE 1800 permits
`attribute_instance` before `continuous_assign`; Yosys 0.23's grammar does not.
**Version-dependent — re-check when the container pins a newer Yosys.**

**Impact:** C1 currently emits an attribute before every `assign`, so
`gatepack compile` produces Verilog that Yosys cannot read. The traffic-light
golden fails at `generated.v:88`. This was invisible because no test has ever
run Yosys.

**Fix:** attach provenance to the `wire`/`reg` declaration, never to the
`assign`.

## 2. `src` is Yosys's own attribute and will be overwritten

Emitting `(* src = "design.yaml:20:states[0]" *)` yields a cell carrying
`src=d.v:12.3-14.39` — Yosys populates `src` itself with the Verilog file/line
that created the cell, and that value wins.

**Fix:** use a distinct namespace, e.g. `gp_src`. Never reuse `src`.

## 3. What survives mapping — measured

Design: two combinational expressions plus two reset flops, run through
`proc; flatten; opt; techmap; opt; setundef; dfflegalize; dfflibmap; abc; clean`.

| Carrier | Pass | Survives? |
|---|---|---|
| Cell attribute | `dfflibmap` | **Yes** — both flops kept `src` into `DFF_R` |
| Cell attribute | `abc` | **No** — `$_AND_`/`$_OR_` → `AND2`/`OR2` came out bare |
| Attribute on a `wire` declaration | — | Attaches to the **net**, never to the derived cell |
| **Net attribute** (`netnames`) | `abc` | **Yes — survives mapping intact** |

Cell-level provenance: 4/4 before mapping, 2/4 after (50%).

## 4. Corrections to `gatepack-design.md`

**[R4-14] is wrong in two respects.** It states `src` "does not survive the
passes that matter: `dfflibmap` and `abc`", and the review it came from called
the loss "*total*, not partial".

- `dfflibmap` **preserves** cell attributes. Sequential provenance is intact.
- Only `abc` destroys them, and only for cells.
- Measured loss was 50%, not total.

**The architectural consequence is larger than the correction.** §15.1 plans to
carry provenance on *cells*. For combinational logic that cannot work — ABC
rebuilds the cell set. But **net attributes survive ABC**, so the workable spine
is:

1. Attach `gp_src` to named nets in C1 (on declarations).
2. After mapping, associate each cell with source by the provenance of the nets
   it connects to.
3. Keep the pre-map capture and structural matching as a second signal for
   cells whose nets were themselves optimised away.

This is more tractable than Draft 4 assumed: linked selection (§15.2) does not
require the lossy cell-matching to carry the whole load.

## 4a. Sequential provenance: measured on a real design, and the earlier framing was wrong

Measured on the traffic-light golden through the production script, dumping
`write_json` after `dfflibmap`, after `abc`, and after `opt_clean`:

| Point | Cells | Cells with `gp_src` | Flops | Flops with `gp_src` | Nets with `gp_src` |
|---|---|---|---|---|---|
| after `dfflibmap` | 25 | 0 | 9 | **0** | 22 |
| after `abc` | 20 | 0 | 9 | **0** | 22 |
| after `opt_clean` | 20 | 0 | 9 | 0 | **16** |

Two corrections to what §3/§4 above imply.

**The flops carry no `gp_src` before `abc` ever runs.** §4 asks why the 9 mapped
`DFF_R` cells are bare and assumes `abc` is responsible. It is not: they are
already bare immediately after `dfflibmap`. The reason is that these cells did
not exist in the source — they are named `$auto$ff.cc:266:slice$130`, i.e.
Yosys *created* them from the `always` block. `gp_src` was attached to the `reg`
declaration, which is a **net**, so there was never a cell attribute to survive.
§3's "cell attribute survives `dfflibmap`" is still true; it is simply
irrelevant to flops that C1 never instantiates as cells.

The practical answer to §4's open question: **sequential provenance is exact,
and it is exact via the net, not the cell.** All three `state_*` nets survive to
the final netlist.

**`opt_clean`, not `abc`, is where net provenance is lost.** 22 net attributes
survive `abc` intact and 6 are dropped by `opt_clean`:

```
lost:      next_RED, set_feedback, state_active   (states)
           t_0, t_1, t_3                          (transitions[0], [1], [3])
survivors: 16, including all state_*, all *_int outputs, all synchronisers
```

These are **not recoverable**. The dropped bits appear in no cell connection in
the final netlist — `abc` folded those intermediates into the combinational
cone, and `opt_clean` then removed wires that genuinely no longer exist. Bit
identity does not rescue them, because there is no bit.

**Coverage, measured: 16/22 = 73% overall, but transitions are the weak axis at
2/5.** That matters more than the headline number, because §15.2's most valuable
interaction is selecting a transition edge in the FSM graph and highlighting the
gates it produced — and 3 of 5 transitions have no exact link on this design.

The architecture is not in trouble; §20 M11b already requires that partial links
be explicit rather than papered over. But two things follow:

1. **Capture the provenance map from the post-`abc`, pre-`opt_clean` netlist.**
   Six links are available there for free and are thrown away afterwards. They
   refer to nets absent from the final netlist, so they must be recorded as
   `inferred`, resolved onto the cells that consumed them.
2. **Do not "fix" this by marking `gp_src` nets with `keep`.** It would preserve
   the names by inhibiting the optimisation, changing the emitted netlist to
   improve a diagnostic — buying provenance with real gates.

## 5. Still unmeasured

- Whether Liberty timing arcs change ABC's mapping (§C2 [R4-11] A/B test).
  **Attempted, inconclusive.** The no-arc baseline maps cleanly (13 cells:
  4×NAND2, 2×NAND3, 2×INV, 2×OR2, 2×XOR2, 1×AND3). Adding hand-written
  `timing()` groups made ABC abort with `Can't open ABC output file` — my
  arc-bearing Liberty is malformed, not proof of anything about arcs. Needs a
  correctly-formed `lu_table_template` before the question can be answered.
  Incidental: a malformed Liberty makes ABC fail *loudly* here, which is a
  different and friendlier failure than R1's "parses but is degenerate" case.
- ~~Whether `equiv_make`/`equiv_induct` close~~ — **measured, see §6 below.**
- ~~`dfflibmap` mapping of `DFF_S`/`DFF_SR`~~ — **measured, all four variants
  map.** With `--allow-single-source` to admit `DFF_S`, a design needing a
  set-only flop and a set+reset flop mapped to `DFF_S` ×1 and `DFF_SR` ×1. The
  §9.2 [R4-3] `ff` group table is therefore correct as implemented, including
  `clear_preset_var1`/`var2` dominance — real `dfflibmap` accepts it.

  **This narrows the `DFF_S` problem from technical to commercial.** The
  mechanism works; what is missing is a dual-sourced set-capable *part*. Option 1
  in §6 below (find one and add it) is viable if such a part exists, and no code
  change is needed to support it.

---

## 6. Equivalence: a working recipe, and one blocking failure

Measured on a two-state one-hot FSM against the generated 74AUP Liberty.

### The recipe that closes

```
# both sides through the SAME front end, then:
write_verilog -noattr gold.v      # golden: stop before dfflegalize/dfflibmap/abc
write_verilog -noattr gate.v      # mapped: after abc; clean
# then, in a fresh design:
read_verilog gold.v ; proc; opt; async2sync; opt      -> stash as gold
read_verilog gate.v cells_sim.v ; proc; flatten; opt; async2sync; opt -> stash as gate
equiv_make gold gate equiv ; prep -top equiv
equiv_simple ; equiv_induct ; equiv_status -assert
```

Three requirements Draft 4 does not state, each of which is a hard failure:

1. **`cells_sim.v` is mandatory, not a convenience.** Without behavioural models
   the mapped netlist's cells are undefined modules and `equiv_make` dies with
   `Module '\INV' ... is not part of the design`. This confirms [R4-17] as a
   blocking M5 dependency rather than a nice-to-have.
2. **`async2sync` is mandatory on both sides.** Async-reset flops are `$adff`
   cells with no SAT model; without it every flop warns
   `No SAT model available for async FF cell` and induction cannot close. §9.3
   *mandates* async-assert reset, so **every** gatepack design hits this.
3. **Re-`proc` after any Verilog round-trip**, or the golden module "contains
   memories or processes".

### The blocking failure: one-hot cannot be verified without `DFF_S`

| Flop reset values | `equiv_status -assert` |
|---|---|
| `s_idle<=0, s_run<=0` | **passes** — equivalence closes |
| `s_idle<=1, s_run<=0` (one-hot initial state) | **fails** — 1 unproven cell |

The only variable is the set-flop. `DFF_S` has no candidate part in §9.2 and is
excluded by §10.1's second-source rule, so the library cannot express a flop
that resets high.

This is the `DFF_S` contradiction raised in `docs/BUILD-NOTES.md`, now
demonstrated rather than argued, and the consequence is worse than a missing BOM
line: **§6.2's default one-hot encoding produces designs that cannot be formally
verified with the shipped library.** Three ways out, and one must be chosen
before M5 is called done:

- Find a genuinely dual-sourced set-capable flop and add it.
- Emit one-hot initial state as set-via-feedback logic on a reset-to-0 flop, and
  count that cost in the §6 gate budget.
- Change the default encoding for designs whose library has no set flop, and say
  so loudly in the report rather than silently.
