# BUILD NOTES — §13.1 SCOAP + §13.2 stuck-at fault analysis

Milestone M10 was merged without these two exit criteria; this branch (`deepseek/
analysis`) makes the `scoap` and `faults` fields of `AnalysisSummary` real,
completing C7.

## Test status

```
.venv/bin/python -m pytest tests -q
# 420 passed, 2 skipped   (baseline was 403 passed, 2 skipped)
npx tsc --noEmit -p tsconfig.json        # 3 pre-existing errors (see below)
npx vitest run                            # 98 passed
```

The two skips are pre-existing (property-discharge and latch-inferring goldens,
gated on sby/Yosys). The `tsc` errors are **pre-existing and not mine**: another
agent added `simulate` to `GatepackApi` in `app/shared/api.ts` without updating
`FakeGatepack` in `app/renderer/bridge/fake.ts`. I touched no `app/` file.

## What landed

New files:

- `gatepack/analysis/scoap.py` — SCOAP over the resolved mapped netlist.
  Combinational `CC0`/`CC1` by the standard controlling-value recurrences, `CO`
  by backward boolean-difference propagation (exact for these gates), sequential
  `SC0`/`SC1` for flops (single pass, `SO(D) = CO(Q) + clock + async-deassert`).
  Emits a per-net table, an **unobservable** list (nets with no path to any
  primary output) and a **delta table** of the worst nets.
- `gatepack/analysis/faults.py` — single stuck-at enumeration + collapsing +
  classification over the resolved mapped netlist. Reports uncollapsed and
  collapsed counts and the four-way detected/undetected/redundant/untestable
  split.

Wired into `build.assemble` (computes both, stores on `BuildResult`), `report.md`
(two new sections), and `api.analysis_summary` (the only function changed in
`api.py`).

`gatepack/liberty/boolean.py` gained `parse_function`/`eval_function` so the
fault simulator can parse a gate function once and evaluate it in the hot loop
instead of re-parsing per vector. This is the only change outside my stated
scope, and it is additive.

## Definitions — the four fault classifications

These are routinely conflated, so the module docstring pins them:

- **detected** — some applied vector changes a primary output or a flop `D`.
- **undetected** — not detected, but the vector space was *not* exhausted, so a
  test may exist outside the applied set. Unknown, not proven absent.
- **redundant** — proven (exhaustive space) that no test exists: the net sits in
  redundant/unobservable logic. A *design* finding.
- **untestable** — no test exists for a reason other than redundancy: a
  stuck-at on a clock / async set / async reset net, which the single-time-frame
  vector model cannot exercise. A *test-access* finding.

## The two counts — what "collapsed" means

`uncollapsed` = 2 × (nets + G/F-cell pins), the literal "nets and cell pins"
enumeration. This deliberately over-counts relative to the textbook `2 × lines`
figure (a pin fault and the net fault it attaches to are counted separately); it
is what was asked for. `collapsed` applies (a) node-level equivalence and (b)
gate-level equivalence + dominance, **with fanout handled correctly**: a net
fans out to ≥2 combinational gates is a *stem* plus one *branch* per sink, and
gate collapsing is applied to branch lines, never to a fanout stem (the
checkpoint rule). I verified the collapsed counts reproduce the textbook figures
for the library gates (AND2=3, XOR2=6, NOT=2, NAND2=3, NOR2=3).

## Sequential handling — the honest approximation

Sequential fault simulation needs multi-cycle time-frame expansion plus
reachable-state knowledge. Neither is derivable from the mapped netlist alone
without a real simulator, so I implemented the standard **combinational-cut
model**: flop `Q` is a pseudo-input, flop `D` a pseudo-output, and the vector
space is `(data inputs) × (2**k flop states)`. This enumerates *illegal* states
(e.g. two one-hot bits set), so the `detected` count is an **upper bound**, not
exact sequential coverage — stated in the note and the report. SCOAP uses the
same cut (flop `Q` as a leaf, `SC(Q)` derived one step from `D`), so a
one-hot set-via-feedback path cannot recurse: the feedback goes *through* the
flop and is cut at `Q`.

## Combinational loops

The design bans latches, so the combinational part is acyclic once flop `Q` is
cut. As defence in depth, SCOAP's Kahn order marks any residual (cycle) cell's
output `None` rather than recursing, and observability is a bounded min-
relaxation fixed point with positive edge weights (so it converges; the 1024-pass
cap is a safety net). A two-inverter ring is a unit test and terminates.

## Honest empty vs zeros

When synthesis did not run there is no netlist, `analysis_summary` emits
`scoap: []` and the zeroed `faults` record, and `report.md` states "not computed
(no mapped netlist)" — never zeros presented as a measurement. The `faults`
record is a closed `api.ts` shape (four numbers, no reason field), so the reason
lives in the report, which is where the task's "state the assumption inline"
requirement points.

## The unobservable wire sentinel

`api.ts` types `observability: number`; JSON has no infinity. An unobservable net
is emitted with `observability = UNOBSERVABLE` (`2**30`), documented in the
module and the report, so C12 can key on `observability >= 2**30` for its
unobservable-overlay. This is a judgment call I want reviewed.

## What I could NOT verify

Yosys is not on PATH (a container has it, but I did not drive it here), so the
SCOAP/fault code has never run on a *real* mapped netlist. The parser is the
existing `gatepack.netlist.parse_mapped_json`; my modules are unit-tested against
hand-written fixtures **labelled as such** (they build on `tests/unit/cells.py`,
the established synthetic-netlist helper). The sequential numbers in particular
are only as good as the cut-model assumption. A real-netlist smoke test is the
first thing to do in the toolchain container.

## What I guessed / least confident about

1. **The sequential fault model is an approximation.** The combinational cut
   over-enumerates flop states, so `detected` is an upper bound and `redundant`
   can be under-counted (a fault only visible in an illegal state is "detected").
   Exact sequential coverage would need time-frame expansion + reachable states,
   which I did not attempt. This is the weakest part of the deliverable.
2. **The single-pass sequential SCOAP.** I compute `SC(Q)` in one step from a
   `D`-cone that treated `Q` as a leaf; I do not iterate to the SCOAP sequential
   fixed point (which can diverge on the one-hot feedback). The `SC0`/`SC1` for
   flops are therefore a first-order estimate, and downstream combinational CC
   is computed against `Q = (1,1)`.
3. **`UNOBSERVABLE` as a wire sentinel.** It keeps the `api.ts` `number` type
   but is an in-band "infinity" the renderer must special-case; a `null`
   (precedented by `packageCount` when Yosys is absent) would be more honest
   but violates the `number` type. I chose the sentinel; the renderer author
   should confirm.
