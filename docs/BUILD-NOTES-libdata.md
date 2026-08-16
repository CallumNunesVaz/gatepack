# BUILD-NOTES — library data verification (unverified values, M-cell specs)

Scope: make unverified/placeholder electrical data impossible to mistake for
verified data, and make the M-cell specification model mandatory.

## What I implemented

### Problem 1 — structural verified/placeholder distinction

- `gatepack/parts.py` gains `Verification` (enum: `VERIFIED` / `PLACEHOLDER`)
  and every `Part` carries `verification`, defaulting to `PLACEHOLDER` — the
  fail-closed choice. `Part.is_verified` is the one accessor.
- `verification_from_citation(status)` is the *only* place the refs-file status
  words (`"placeholder"`, `"unverified"`) are interpreted; `None` (uncited) is a
  placeholder too.
- `gatepack/refs.py` gains `load_parts_cited()` (loads `parts.csv` and attaches
  each part's verification from the companion `<name>.refs.md`) and
  `placeholder_summary()` (the `{total, unverified, unverifiedCells}` data the
  toolchain agent's `doctor.py` should surface — see below).
- `gatepack/build.py::run_build` now loads parts via `load_parts_cited` so the
  gate and the emitted BOM/report see real citation status.

### Propagation into outputs

- `gatepack/emit/bom.py`: `BomRow.unverified` and a trailing `unverified` BOM CSV
  column (`yes` / empty).
- `gatepack/report/report.py`: the BOM table gains an `electrical data` column
  (`verified` / `unverified`) and, when any row is unverified, a paragraph naming
  the unverified parts and why it matters.
- `gatepack/api.py::bomline` adds `"unverified"` (bool) so the build `--json`
  BOM lines carry the marker. `library_part_payload` already carried
  `"unverified"`; unchanged.

### The gate

`gatepack/build.py` refuses the build when a multi-gate part (`gates_per_pkg >
1`) whose data is unverified is used to place **more than one gate** in a single
package (`len(group.cells) > 1`), unless `run_build(...,
allow_unverified_gates_per_pkg=True)`.

Decision (and the argument for it): the *dangerous* unverified claim is "which
gates share a die" — a wrong value there yields a netlist that physically cannot
be built. I gated on the shared-die case rather than on every unverified
`gates_per_pkg` for two reasons. (1) A single gate placed in a nominally
multi-gate package is a *wrong spare count* failure, not an unbuildable netlist,
and it is already marked in the BOM/report; gating it would make the shipped
(all-placeholder) library refuse every build, including single-gate designs that
do not exercise the dangerous claim. (2) The CLI acknowledgement flag follows
`--allow-single-source` and is owned by the exit-code agent (`gatepack/cli.py`
is off-limits here); the programmatic `allow_unverified_gates_per_pkg` parameter
is the core-side hook they should wire to a `--allow-unverified-gates-per-pkg`
flag. The refusal message names each offending part, its `gates_per_pkg`, the
gate count sharing a die, and the exact consequence.

### Problem 2 — mandatory spec models + second M-cell

- `gatepack/macros/__init__.py`: `known_m_cells()` is now the spec-model
  registry (a cell does not exist as an M-cell until it has a spec). A physical
  binding (`bindings.py`) is optional and separate.
  `validate_m_cell_library()` fails at library load (`load_models()` /
  `load_spec_models()`) when a cell has an implementation model but no
  specification model, or vice-versa.
- `gatepack/frontend/model.py`: the compile-time macro gate now checks
  `known_m_cells()` (specs) and raises `CompileError` with "a macro without a
  specification model cannot be verified (§9.4 M8)" — at compile, not at
  equivalence time.
- `gatepack/macros/specs.py`: `MCellSpec` gains `kind` ("counter" /
  "shift_register"), `serial_in_pin`, and a `flops` property; `spec_model` /
  `_advance_expression` branch on `kind`. `SR4_SPEC` added.
- `gatepack/macros/models/SR4.v`: a 4-bit serial-in parallel-out shift register
  (implementation model). Chosen over a Johnson counter because its failure mode
  (shifts in the wrong bit) differs structurally from a binary counter's.
- `gatepack/frontend/verilog.py`: wires a shift register's `serial_in_pin` to
  `1'b0` (a documented synthetic tie-off — `design.yaml` has no serial-data
  field).
- New toolchain test `test_wrong_sr4_model_is_caught_by_equivalence` mutates the
  SR4 implementation (shift in `1'b0` instead of `SI`) and confirms equivalence
  fails against real Yosys 0.23 (`gatepack-toolchain:m6`), then restores and
  confirms it passes.

## What I guessed / decided

- **SR4 carries no physical binding** (no `bindings.py` entry, no `parts.csv`
  row). I chose this because a physical binding would require inventing a part
  number, package and pinout — exactly the §1.3 defect this work exists to
  prevent. SR4 is verification-only.
- **Gate scope** (shared-die only) as argued above. The alternative — gating on
  every unverified `gates_per_pkg` — is more conservative but makes the shipped
  library unusable by default and, in my view, over-gates the single-gate case
  whose failure is a spare count, not an unbuildable netlist. Recorded here so a
  reviewer can disagree loudly.
- **Verification source is the refs file, not a CSV column.** I deliberately
  did not add a `verification` column to `parts.csv`; the citation is the source
  of truth and duplicating its status into the CSV invites drift. Parts loaded
  without a refs file default to placeholder.

## What is a placeholder

- Every part in `libraries/74aup.csv` is `PLACEHOLDER` (as before). The `verification`
  field merely makes that explicit in the model.
- SR4's `serial_in_pin` tie-off is `1'b0`, a synthetic placeholder, not design data.

## What I could not verify / did not do

- **`gatepack/cli.py` (exit-code agent):** the `--allow-unverified-gates-per-pkg`
  flag is *not* wired. `run_build` exposes `allow_unverified_gates_per_pkg`; the
  CLI agent should map it to a flag following `--allow-single-source`. Until
  then, `gatepack build` on the shipped library refuses by default (correct).
- **`gatepack/doctor.py` (toolchain agent):** the placeholder count is *not*
  surfaced. The data is in `gatepack.refs.placeholder_summary()`; doctor should
  read it (e.g. `placeholder_summary("libraries/74aup.csv")["unverified"]`) and
  add it to the `resources` payload. I put the data in place and left doctor
  untouched.
- **`app/shared/api.ts` (renderer agent):** the build `--json` BOM lines now
  carry `"unverified"` (bool) on the core side. `api.ts`'s `BomLine` should gain
  the matching `unverified: boolean` field; I did not edit `api.ts`.

## Weakest points

- The gate's shared-die boundary (`len(group.cells) > 1`) leans on the packer's
  `PackageGroup.cells`. A single gate resolved into a multi-gate package (the
  `resolve_parts` last-wins behaviour for duplicated cell names) ships a
  multi-gate part number un-gated — it is marked, not refused. If that
  resolution behaviour is ever tightened (fewest-gates representative), the gate
  and the resolution will agree and this edge disappears.
- `unverified_multi_gate_parts()` in `parts.py` is currently exercised only by
  tests; the live gate uses the group-level condition in `build.py`. Kept as the
  library-level predicate for the "multi-gate is the dangerous case" contract.
- The SR4 mutation test covers one mutation (shift-in-wrong-bit); a second,
  orthogonal mutation (e.g. shift direction) would strengthen it but was not
  added.

## Test counts

Baseline: 557 passed, 5 skipped. After: 606 passed, 5 skipped.
