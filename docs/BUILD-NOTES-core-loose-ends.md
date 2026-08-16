# BUILD NOTES — core loose ends (analyse, M-cell coverage, estimate vs build)

Three previously-unfinished pieces of the core, closed and measured against the
real toolchain (`gatepack-toolchain:m6`: Yosys 0.23, Icarus, sby, z3, pydantic).

Test counts: **504 passed / 4 skipped → 522 passed / 4 skipped** (18 new tests).
`app`: `tsc` clean (both configs), `npx vitest run` 147 passed — untouched, the
contract change is additive (the new `analyse` command emits an envelope the
bridge already routed).

---

## 1. `gatepack analyse <dir>` — added (§17, task 1)

`gatepack/analysis/summary.py` + a parser/entry in `gatepack/cli.py`.

- `analyse <dir>` reads `mapped.json` and `cells.lib` from an existing
  `gatepack build` output directory and emits the `AnalysisSummary` payload
  (`app/shared/api.ts`) — SCOAP delta (§13.1), four-way stuck-at classification
  (§13.2), CPLD blockers (§24.1), plus the two metrics that the directory can
  honestly support (mapped flop count, combinational depth).
- `--design <yaml>` + `--library <csv>` together select a **full** path that
  re-runs `build.assemble` against the existing `mapped.json`, so its payload is
  field-for-field the `analysis` block of `build --json` (all five metrics:
  package count, flop count, static current, depth, pack cost). Pinned by
  `test_full_analysis_matches_build_analysis`.
- `--json` uses the standard envelope; a missing netlist is an explicit
  `ok:false` envelope (`GP1003`, "no mapped netlist … run `gatepack build`
  first"), never an all-zeros summary.

### Decisions / guesses I had to make

- **The GUI routes `['analyse', outDir]`** (`app/main/session.cts`), so the
  dir-only path is the default and must stand alone. I did not touch `app/`.
- **Parts are reconstructed from `cells.lib`.** The directory does not carry
  `parts.csv` (the build does not copy it), so I parse the generated Liberty
  (`load_parts_from_liberty`) to recover each G-cell's boolean function, pin
  count and tier. This is enough for SCOAP and stuck-at, and I verified the
  dir-only SCOAP/faults are byte-identical to the full path on the showcase.
- **`cells.lib` does not carry `gates_per_pkg`, `iq_ua` or `tpd_ns`**, so the
  dir-only path deliberately **omits** package count, pack cost and static
  current rather than fabricate them (a one-gate-per-package assumption would
  be exactly the wrong-number failure mode this project exists to prevent).
  The full path (with `--library`) supplies them. This is the main limitation;
  see "weakest" below.
- **Faults without a compiled design**: `analyze_faults(netlist, compiled=None)`
  treats every primary input as a data input (the module's documented
  approximation for sequential designs). Clock/reset are still classified
  `untestable` (they are control nets in the netlist), so on the showcase the
  classification coincides with the exact one; at the vector cap boundary a
  design with many inputs could differ.

### Weakest part

The dir-only metrics are sparse (2 of 5) and the flop-count metric is the
*mapped* F-cell count, which for a macro design would under-count (M-cell flops
are inside the macro, and the front-end does not instantiate macros — see §2).
If the analysis dashboard needs the full five metrics without `--library`, the
build must persist `parts.csv` (or a richer manifest) into the out directory —
that is a `build.py` change, outside this task's file scope.

---

## 2. M-cell coverage (R25) — findings, loud ones (§9.4, task 2)

Added `tests/golden/designs/cnt4_macro.yaml` (a CNT4 macro declared in the
design) and `tests/toolchain/test_mcell_coverage.py`. Three facts, all measured
in the container:

1. **The model IS shared (R25, the trivial half).** One `CNT4.v` under
   `gatepack/macros/models/`, appended by `load_m_cell_models()` onto
   `cells_sim.v`, which both the equivalence script and the Icarus compile read.
   Pinned structurally by `test_mcell_model_is_shared_between_equivalence_and_simulation`.

2. **The macro is never instantiated, and a macro-bearing design does not even
   synthesise.** The front-end (`gatepack/frontend/verilog.py`, outside my file
   scope) emits the macro as a dangling `(* gp_src = "…macros[0]" *)` attribute
   immediately followed by a comment and then `endmodule` — no `CNT4 dwell(…)`
   instantiation. Yosys rejects that attribute with `syntax error, unexpected
   TOK_ENDMODULE`. So `gatepack verify` on the macro golden **fails at C3, before
   C4 ever runs**, and the shared model is dead code in every real build.
   Pinned by `test_verify_on_macro_design_fails_before_reaching_the_model` and
   `test_cnt4_macro_is_declared_but_not_instantiated`.

3. **A deliberately wrong CNT4 model is NOT caught.** With a hand-built netlist
   that actually instantiates `CNT4` (because the front-end can't), the
   equivalence script reads `cells_sim.v` on *both* the golden and the mapped
   side. Mutating the counter so it counts by two instead of one
   (`Q <= Q + 4'd2` instead of `Q <= Q + 4'd1`) changes both sides identically,
   and `equiv_induct` still reports **"Equivalence successfully proven!"** for
   both. This is the R25 risk materialised: "mutation testing compares an M-cell
   model against itself". Pinned by
   `test_wrong_mcell_model_is_not_caught_by_equivalence`.

**Net finding: the M-cell path is unverified.** R25's "one shared model file"
control satisfies only the no-drift half of the requirement. A wrong M-cell
model cannot be caught by the current C4 strategy, because the equivalence check
compares the model against itself and the exhaustive simulation's spec model
(`_ReferenceDesign`) knows nothing about the counter. Catching it needs an
*independent* hand-written reference model on the golden side — which means
changing how the front-end emits macros (an instantiation plus a reference), a
change outside `gatepack/analysis|macros|verify|cli|api|tests`.

---

## 3. `estimate` verdict is never checked against `build` — two defects found (§6, task 3)

Added `tests/unit/test_estimate_build_consistency.py` and
`tests/toolchain/test_estimate_build_consistency.py`.

Measured on the pelican showcase with `libraries/74aup.csv`:

- **`estimate` counts mapped *cells*, not packed *packages*.** `_count_mapped_cells`
  in `estimate.py` returns the number of non-`$` cells (23 for the showcase);
  `build` packs the same netlist to **20 packages / 3 spare gates**. The §6
  verdict's "package count" metric is therefore computed against 23, not 20.
  Both fall in the green band (≤ 25) here, so no verdict flips — but a design
  near the boundary gets a verdict over the wrong number, which is exactly the
  "green, ~18 packages for a board that builds to 30" failure the task names.
  The unit test proves the general divergence (3 NOR2 cells → estimate 3 vs
  `pack()` 2 with a 2-gate part); the toolchain test pins the showcase 23 vs 20.

- **`estimate` runs Yosys with `cwd=build_dir.parent`, silently breaking nested
  `--build` paths.** `build` and `verify` both fixed this (run from the
  invocation directory, paths relative); `estimate` still has the old form, so
  `--build .gpout/est` makes Yosys resolve `mapped.json` one level too deep,
  fail, and `packageCount` becomes `None` with exit 0 and no error. Pinned by
  `test_estimate_nested_build_dir_silently_reports_none`.

Both defects are in `gatepack/estimate.py`, which is **not** in this task's
write scope, so they are reported rather than fixed. The fix is small (run Yosys
from `.`; fold the packed package count in) but should be made by whoever owns
`estimate.py`, with these tests then flipped from "diverges" to "agrees".

---

## Three things I am least confident about

1. **The dir-only `analyse` metrics being limited to 2 of 5.** It is honest, but
   a user who only ever calls the GUI path (no `--library`) sees a sparser
   dashboard than `build --json` produces. I chose "omit, never fabricate" over
   "reconstruct a wrong package count"; if the reviewer wants the full five
   metrics from the directory alone, `build.py` must persist `parts.csv` (or a
   richer manifest) into the out dir — which is outside my file scope.

2. **That reporting the M-cell defects as tests rather than fixes is what's
   wanted.** I could not fix the front-end (`gatepack/frontend/verilog.py` and
   `estimate.py` are both outside my write scope), so the two loudest findings
   (macro never instantiated + wrong model not caught; estimate counts cells not
   packages) are delivered as pinned tests plus these notes. A reviewer who
   wanted the actual fixes will need to re-scope those two files.

3. **Whether `analyse` should have accepted `--design`/`--library` at all.** The
   §17 contract and the GUI routing are dir-only, so I made those flags optional
   and additive; the full path re-runs `build.assemble` (which also re-generates
   and re-validates the Liberty). That is correct but heavier than a pure
   "re-read the artefacts" command, and it re-derives data the directory already
   contains (in `report.md`/`bom.csv`, as prose I deliberately did not parse).
