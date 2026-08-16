# BUILD NOTES — M11b provenance coverage (reported + measured)

Branch `deepseek/prov`. Scope: `gatepack/provenance/`, `gatepack/report/report.py`,
`tests/`, and this file.

## Test status

```
.venv/bin/python -m pytest tests -q   # 496 passed, 4 skipped  (baseline 467/2)
npx tsc --noEmit -p tsconfig.json     # clean (untouched)
npx tsc --noEmit -p tsconfig.main.json# clean
npx vitest run                        # 125 passed (untouched)
```

The two new skips are `test_at_least_one_exact_transition[xor2]` and
`[decoder_3to8]`: their single self-loop transition is constant-folded by Yosys
`opt` *before* the premap capture, so there is no transition construct in the
netlist to measure — the skip is the honest state, not a faked pass.

The toolchain test (`tests/toolchain/test_provenance_real_run.py`) runs against
the real container here (docker + `gatepack-toolchain:m6` present), so it is
green locally. In an environment without the image it skips with the explicit
reason, matching the other `tests/toolchain` tests.

## What landed

New files:

- `gatepack/provenance/coverage.py` — the measurement + payload layer.
  `measure_coverage(premap, mapped, post_abc=None)` produces a `CoverageReport`
  broken down **by carrier** (net / cell) and **by construct kind** (states,
  transitions, output logic, inputs, reset), plus the `entries`/`coverage`
  payload. `provenance_map_payload()` emits the `ProvenanceMap` shape
  field-for-field with `app/shared/api.ts` (read, not edited).
  `measure_coverage_from_dir(build_dir)` reads `premap.json` / `mapped.json` /
  `post_abc.json` and returns `None` when the netlists are absent — the entry
  point a `gatepack provenance` command or the report generator calls.
- `gatepack/provenance/__init__.py` — re-exports the new API.
- `gatepack/report/report.py` — a "## Provenance (§15.1, M11b)" section (carrier
  table, construct-kind table, exact/inferred/absent split, the constructs with
  no link **named**, assumption inline) and the worst-path rendering fix (see
  §4 below). Two new `ReportInputs` fields: `provenance` and `cell_refdes`.

Tests:

- `tests/unit/test_provenance_coverage.py` — the confidence model pinned against
  synthetic netlists (exact vs inferred vs absent; no present-but-empty entry;
  payload shape; carrier split; driver resolution).
- `tests/golden/test_provenance_coverage.py` — coverage measured for every
  passing golden against committed real fixtures, with a documented floor.
- `tests/toolchain/test_provenance_real_run.py` — a real `gatepack build` in the
  container, a regenerated post-`abc` capture, and an assertion that the live
  numbers equal the committed fixtures (no drift).

Fixtures (committed, real `write_json` from Yosys 0.23 in the pinned container):
`tests/fixtures/provenance/{traffic_light,xor2,decoder_3to8,pelican}/
{premap,mapped,post_abc}.json`.

## The numbers, measured on the real toolchain

| design | premap nets | final nets (exact) | dropped by `opt_clean` (inferred via post-`abc`) |
|---|---|---|---|
| traffic_light | 22 | 16 | 6 (`next_RED`, `set_feedback`, `state_active`, `t_0`, `t_1`, `t_3`) |
| pelican | 29 | 24 | 5 (`next_STOP`, `set_feedback`, `state_active`, `t_1`, `t_4`) |
| xor2 | 2 | 2 | 0 |
| decoder_3to8 | 9 | 9 | 0 |

Construct-kind (traffic_light, without the post-`abc` capture — the shipped
build's reality): states 1/1 exact, **transitions 2/5 exact (3 absent, named
`transitions[0]`, `transitions[1]`, `transitions[3]`)**, output logic 3/3,
inputs 2/2, reset 1/1. This is the M0 §4a finding, now measured by a test that
fails if it drifts.

## The floor and why this number

`NET_EXACT_FLOOR = 0.50` on the net carrier, plus: output logic fully exact, at
least one exact transition on any multi-transition design, and the traffic-light
transition figure pinned exactly (2/5, names included).

The floor is **not** a quality bar. It is chosen to catch the regression that
matters — a change to C1 or to the synthesis passes that stops net `gp_src`
surviving `abc` — while staying well below the weakest real value (73%). A floor
at, say, 95% would encode "the current toolchain is good" and would turn any
future legitimate optimisation into a spurious failure. The pinned traffic-light
assertion is the part that certifies the *finding* (transitions at 2/5), not the
quality.

## The confidence model (and two temptations refused)

`confidence` is exactly the two `api.ts` values:

- `exact` — the `gp_src` attribute survives into the final netlist.
- `inferred` — the attribute survived `abc` but not `opt_clean`; it is present in
  the post-`abc` capture and absent from the final netlist. The dropped net is
  named in the entry (`nets`) and the entry carries no cells, because the six
  dropped nets are genuinely orphaned — measured, not assumed: after `abc` they
  have **no driver and no consumer**, `opt_clean` removes exactly the wires that
  no longer exist, and M0 §4a is right that "there is no bit".

Refused explicitly, because both make the number better and the tool worse:

1. **No `keep` on `gp_src` nets.** Preserving the six names would buy
   provenance with real gates by inhibiting `opt_clean`. Not done.
2. **Inferred is never promoted to exact.** The `inferred` count sits in its own
   column; the exact count does not move when the post-`abc` capture is present
   (16 stays 16). The toolchain test asserts this.

**Absent vs present-but-empty.** A construct with no link at all produces no
entry, so the renderer's `linkConfidence` "none" is distinguishable from an
entry whose `nets` and `cells` are both empty. `measure_coverage` never emits an
empty entry; the unit and golden tests assert that invariant.

## What is NOT wired (the seams, deliberately left for the file owners)

I was constrained to `gatepack/provenance/`, `gatepack/report/report.py`,
`tests/` and these notes. Three one- or two-line integration points remain, each
in a file owned by another agent. Each is listed with exactly what to do.

1. **`gatepack/build.py` — populate the report.** `assemble()` builds
   `ReportInputs(...)`; add two kwargs so the generated `report.md` actually
   carries the new section and the readable worst path:

   ```python
   from gatepack.provenance.coverage import measure_coverage_from_dir
   # (assemble does not know the out dir today; pass it in, or compute from
   #  the netlists it already has)
   ...
   ReportInputs(
       ...,
       provenance=measure_coverage_from_dir(out_dir),
       cell_refdes={raw: refdes for raw, stable in names.items()
                    if stable in current for refdes in [current[stable]]},
   )
   ```

   Until then the report renders "provenance not computed (no provenance map
   passed...)" and the raw `$abc$...` worst path — both honest degradations,
   matching the existing "SCOAP not computed" pattern.

2. **`gatepack/cli.py` + `gatepack/api.py` — the `provenance` command.** The
   GUI already calls `gatepack provenance <outDir> --json` (in `app/main/
   session.cts`). The subcommand does not exist. The payload builder exists and
   is one call:

   ```python
   # _cmd_provenance(args):
   report = measure_coverage_from_dir(args.out)
   if report is None:
       _json_ok("provenance", {"entries": [], "coverage": 0.0})
   else:
       _json_ok("provenance", provenance_map_payload(report))
   ```

   `provenance_map_payload` matches `ProvenanceMapSchema` (zod) field-for-field.

3. **`gatepack/synth/synchronous.py` — the post-`abc` capture point.** Add one
   line between `abc` and `clean`:

   ```
   abc -liberty <lib>
   write_json <out>/post_abc.json    # M11b: post-abc, pre-opt_clean capture
   clean
   ```

   Without it, the shipped build reports the six dropped constructs as **absent**
   (the lower honest number). With it, `measure_coverage_from_dir` finds
   `post_abc.json` and reports them as **inferred**. The toolchain test already
   proves the mechanism by patching the generated script and re-running Yosys.

## What I guessed / am least confident about

1. **Scope judgement.** I treated "write only in `gatepack/provenance/`,
   `gatepack/report/report.py`, `tests/` and your notes" as binding and left the
   three seams above for the file owners rather than touching `build.py`,
   `cli.py` or `synth/`. If the milestone is judged end-to-end ("run
   `gatepack build` and the report has the section"), those seams are the
   remaining work; everything behind them is implemented and tested.
2. **Construct inventory from premap, not from the spec.** A construct that
   produced no logic (xor2/decoder_3to8's constant-folded state and self-loop
   transition) is absent from the inventory, so it is *not* reported as "lost".
   The alternative — derive the inventory from the spec and call those
   constructs "absent" — would report a benign constant as a provenance gap. I
   chose the honest-netlist reading, but a reviewer may prefer the spec reading.
3. **`states` is one construct, not N.** C1 emits every state net with the
   single token `states` (not `states[i]`), so the kind table shows
   `states: total=1`, and the transition weakness is the axis that matters.
   Relatedly — and worth the attention of whoever owns the GUI — `app/renderer/
   selection/map.ts` resolves a state selection to path `states[${i}]`, which
   the core never emits: state selections will therefore read as "no link"
   (confidence `none`) even though states have exact provenance under `states`.
   That is a real contract mismatch I could not fix (both files are out of my
   scope).

## What I could not verify

- The cell carrier is `0/0/0` on every golden: C1 attaches `gp_src` to nets, and
  the flops Yosys creates (`$auto$ff...`) carry no cell attribute (M0 §4a), so
  the net carrier is the entire spine for these designs. I did not exercise a
  design whose sequential provenance genuinely rides a *cell* attribute — the
  unit test `test_cell_carrier_is_distinct_from_net_carrier` covers the path,
  but not against a real netlist.
- The `coverage` field of the payload is the construct-level fraction
  (9/12 = 0.75 for traffic_light without the post-`abc` capture), not the 73%
  net figure. The two are different metrics; both are reported in the report
  section, but only one number fits `api.ts`'s single `coverage` field.
