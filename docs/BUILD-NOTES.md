# BUILD NOTES — M1 (parts model, C2 Liberty generator, CLI)

## What was built

The first buildable increment, scoped exactly to M1 (§20): the parts data
model, the C2 Liberty generator, the CLI around them, and the repository
skeleton they need. No front end (C1), synthesis (C3), verification (C4),
packer (C5), emitters (C6), or Electron code was built.

Files added:

- `pyproject.toml` — project `gatepack`, Python >=3.10, dependency
  `pydantic>=2`, console script `gatepack = gatepack.cli:main`, pytest config.
- `gatepack/__init__.py` — version string.
- `gatepack/parts.py` — the §10.1 `parts.csv` model as pydantic models
  (`Part`, `Equivalent`), a loader (`load_parts`) with per-cell error messages,
  and the Liberty selection rules (`select_for_liberty`).
- `gatepack/refs.py` — datasheet-citation checking (§10.1 [R4-21]).
- `gatepack/liberty/boolean.py` — `!`/`&`/`|`/`^` -> Liberty function syntax.
- `gatepack/liberty/generator.py` — C2: `parts.csv` -> Liberty text, with the
  C2 self-check invoked on every emit.
- `gatepack/liberty/validate.py` — the C2 self-check: structural parse
  (balanced braces, library block, cell blocks, `area`, pin directions,
  `function`, `ff` attributes) and cell-count/name verification.
- `gatepack/liberty/__init__.py` — public re-exports.
- `gatepack/cli.py` — `gatepack lib check <csv>` and `gatepack lib gen <csv> -o <lib>`.
- `libraries/74aup.csv` / `libraries/74aup.refs.md` — starter cell library
  (placeholders, see below).
- `Dockerfile` — pinned yosys/abc/sby/espresso/iverilog (see below).
- `tests/` — pytest suite (see below).

## Test command and result

```
.venv/bin/pytest -q
# 52 passed in 0.21s
```

Also smoke-tested by hand:

```
.venv/bin/python -m gatepack.cli lib check libraries/74aup.csv   # exit 0
.venv/bin/python -m gatepack.cli lib gen libraries/74aup.csv -o /tmp/opencode/74aup.lib  # exit 0, 13 cells
```

`lib check` correctly reports the single-sourced `DFF_S` as dropped, and warns
that all 14 rows carry unverified/placeholder electrical data.

The required test coverage is present:

- valid library round-trips to a Liberty file with the expected cell count
  (13 by default: 10 G-cells + DFF/DFF_R/DFF_SR; `DFF_S` excluded);
- the §18 degenerate-library test (`tests/test_validate.py`) — broken `.lib`
  inputs fail the self-check;
- single-sourced exclusion and `--allow-single-source` inclusion;
- a 74HC part at `vcc: 1.8` is excluded with `DropReason.VCC` (§9.4 [R4-8]);
- a cell missing its citation fails `lib check` (exit 1);
- `DFF_SR` emits `clear` and `preset` with `clear_preset_var1:"L"` /
  `clear_preset_var2:"H"` (clear/reset dominates, matching `$_DFFSR_*`).

## Guesses / decisions made

Every place I had to decide without explicit design guidance:

1. **Flop pin naming is hardcoded** (`_FLOP_SPECS` in
   `gatepack/liberty/generator.py`): `D`, `CK`, `Q`, `RST_N` (active-low
   reset), `SET_N` (active-low set). The §9.2 table gives functions and
   candidate parts but no pin names, and the `function` column is empty for
   F-cells, so the generator cannot derive them from the CSV. This is a
   convention, not a design requirement, and will matter when `dfflibmap`
   matches real `$_DFF_*` cells in M1's downstream smoke test.
2. **Library name sanitization**: `74aup.csv` -> `library (lib_74aup)`
   because Liberty identifiers cannot start with a digit. Cosmetic.
3. **`--vcc` CLI flag** (default 3.3 V per §21.1). The §17 CLI listing shows
   no `--vcc`, but VCC-compatibility filtering (§9.4 [R4-8]) needs a
   project voltage; 3.3 V is the documented default.
4. **`lib check` does not fail on single-sourced cells.** §10.1 says
   single-sourced cells are "excluded ... unless `--allow-single-source`,
   which fails CI by default"; I interpreted the enforcement as *exclusion at
   `lib gen`* plus *reporting at `lib check`*, with a non-zero exit reserved
   for hard validation failure (malformed data, missing citation). If the
   intent was for `lib check` to also exit non-zero on single-sourced cells,
   that is a one-line change.
5. **Refs file location/format**: `<stem>.refs.md` beside the CSV (matching
   §17's `74aup.csv` / `74aup.refs.md`), parsed as a markdown table whose first
   column is the cell name. §10.1's text says `parts.refs.md` (a generic
   name); I followed the concrete §17 example.
6. **Citation check is presence-only.** A row is "cited" if its cell name
   appears in the refs table; an entry marked "placeholder — unverified" still
   satisfies it (and produces a warning, not a failure). This is deliberate:
   the whole starter library is placeholder, and the design (§10.1 R4-21)
   pins the *revision/table/page* content to a datasheet later — that content
   cannot be supplied now without fabricating it.
7. **Boolean emission is fully parenthesised** (e.g. `!(A&B)` -> `(!(A & B))`,
   `A&B&C` -> `((A & B) & C)`). Liberty accepts `!`/`&`/`|`/`^`, so translation
   is parse-then-re-emit; the parens remove any precedence ambiguity.
8. **Timing arcs are not emitted.** `tpd_ns` and `iq_ua` are carried in the
   model but unused by M1's generator, following [R4-11] (arcs are primarily
   for the C7 delay report, not mapping). The M1 timing-arc A/B golden (§18)
   is a C3/M1-smoke-test concern, not this generator.
9. **Starter cell set**: the §9.1 gates are a representative subset (INV, BUF,
   NAND2/3, NOR2/3, AND2/3, OR2, XOR2). XNOR2, 2:1 MUX, AND-OR-invert and the
   configurable gates (1G57/58/97/98/99) are deferred because their candidate
   part numbers are less certain; nothing in M1 requires them.
10. **`DFF_S` has no candidate part** (§9.2 shows "—"), so it is shipped with
    an empty `part_suffix` and empty `mfrs`, making it single-sourced and
    therefore excluded by default. It is included only under
    `--allow-single-source`. This is honest but leaves the design's
    "one-hot initial state needs exactly one set flop" unsatisfied; see below.

## Placeholder values in `libraries/74aup.csv`

**Every electrical value in the file is a placeholder** and is marked as such
in `74aup.refs.md`. Nothing has been verified against a datasheet, and none of
it should be used as design data. Specifically:

- `vcc_min`/`vcc_max` = 0.8 / 3.6 V (the AUP family range) — plausible, unverified.
- `tpd_ns` = 4.6–7.5 ns — plausible round numbers in the AUP ballpark, unverified.
- `iq_ua` = 0.9 µA — plausible, unverified.
- `area` = 1.0 for all cells (the §10.1 default per gate).
- `package` = SOT-353, `gates_per_pkg` = 1 for all single-gate parts.
- Part numbers (`1G04`, `1G00`, `1G10`, `1G02`, `1G27`, `1G08`, `1G11`,
  `1G32`, `1G34`, `1G86`, `1G79`, `1G175`, `1G74`) are real-looking candidates
  but are **candidates requiring confirmation**, per §9's header note.
- Manufacturer lists (`TI`, `Nexperia`, `Diodes`) are unconfirmed and must not
  be read as a second-source claim; `74aup.refs.md` says so explicitly.
- `DFF_S`: `part_suffix` and `mfrs` are empty (no candidate part).

## Dockerfile

Pins `yosys`, `abc` (via Yosys's submodule), `sby`, `espresso`, `iverilog`, and
a solver (`z3`) for sby. **Every version tag and the espresso fork URL are
placeholders** to be confirmed at M0, and the image has not been built in this
environment (no network/toolchain available). The comments in the file flag
this; it is deliberately simple and must be exercised as part of M0 before it
is trusted.

## Things in the design I think are wrong or under-specified

1. **`DFF_S` "must be present" vs. the second-source rule is a contradiction.**
   §9.2 lists `DFF_S` as required for one-hot initial state, but gives no
   candidate part and the §10.1 rule mechanically excludes any single-sourced
   cell. The design cannot have both a set-flop in the shipped library *and*
   the second-source rule as stated; I implemented the rule and let `DFF_S`
   drop (honest), but this needs a decision: either find a genuinely
   dual-sourced set-flop, or accept that one-hot initialisation is synthesized
   as set-via-feedback and drop `DFF_S` from the inventory.
2. **Citation filename is inconsistent**: §10.1 says `parts.refs.md`, §17 shows
   `74aup.refs.md`. I followed §17.
3. **"`--allow-single-source`, which fails CI by default"** is ambiguous about
   *which* command fails. I made the override a `lib gen`/`lib check` flag that
   changes exclusion; the "fails CI" consequence materialises downstream when a
   build needs the excluded cell. See guess #4.
4. **§10.2 example still shows `vcc: 1.8`** while §21.1 fixes the default to
   3.3 V and notes "this changes the §10.2 example". The example was not
   updated in the text; M1 does not touch `design.yaml`, so no action here, but
   it is a stale value to fix in Draft 5.

## What is unfinished / not in this increment

- Yosys-level parse validation of the emitted `.lib` (the design's C2 self-check
  says "verify the file parses under Yosys"); the pure-Python structural check
  is a substitute until the M0 container exists. `dfflibmap`/`abc` mapping of
  `DFF`/`DFF_R`/`DFF_S`/`DFF_SR` from the hand-written Liberty is the M1 exit
  criterion and is **not** demonstrated here (no yosys available).
- Timing arcs and `cells_sim.v` behavioural models (the other M1 deliverables in
  the milestone table) are out of this increment's stated scope; the task
  scoped M1 to "parts data model, C2 Liberty generator, and the CLI".
- `gatepack estimate` (correctly moved to M3 per [R4-22]) is not present.

---

# BUILD NOTES — M2 + M3 (C1 front-end, C3 SynchronousBackend, `gatepack estimate`)

## What was built

This increment delivers M2 (the C1 synchronous front-end) and M3 (C3
SynchronousBackend + the §6 viability verdict), plus the test architecture and
the two docs. No C4/C5/C6 or Electron work.

Files added:

- `gatepack/frontend/` — the C1 front-end:
  - `yaml_subset.py` — a hand-rolled YAML-subset parser with per-node line
    provenance (see "Guesses" #1).
  - `expr.py` — the shared boolean expression language (`! & | ^`, `0`/`1`,
    `state == NAME`) with parse / expand / evaluate / Verilog-emit.
  - `schema.py` — the pydantic `design.yaml` schema, field-for-field per §10.2,
    `vcc` defaulting to 3.3 (§21.1; the §10.2 example's 1.8 is the known stale
    value).
  - `model.py` — semantic compilation: reachability (BFS), guard overlap +
    exhaustiveness (SAT-style), expression reference checking, async refusal.
  - `sat.py` — exhaustive guard checking with a documented input cap.
  - `johnson.py` — Johnson-counter topology detection (suggestion only).
  - `verilog.py` — behavioural Verilog + `properties.sv` emission with
    `(* src = "design.yaml:LINE:PATH" *)` on every construct.
  - `frontend.py` / `errors.py` — orchestration and `CompileError` /
    `AsyncRefused`.
- `gatepack/synth/` — `base.py` (interface), `synchronous.py` (C3 script),
  `asynchronous.py` (refuses).
- `gatepack/yosys/common_frontend.ys` — the shared common front end, loaded once
  and referenced by C3 (and, at M5, C4's `golden_prep`) via
  `gatepack.yosys.common_frontend()`.
- `gatepack/estimate.py` — the §6 verdict (`assess` is a pure function) plus
  `run_estimate` orchestration (front-end → C2 Liberty → C3 script → optional
  Yosys → manifest.json).
- CLI additions: `gatepack compile <design.yaml> -o <dir>` and
  `gatepack estimate <design.yaml> --library <csv> [--build <dir>]`.
- `tests/unit/` (moved 52 existing + ~100 new), `tests/golden/`,
  `tests/contract/`, `scripts/tests/{harness.sh,run.sh,test_cli_e2e.sh}`.
- `AGENTS.md` and `docs/TESTING.md`.

## Test command and result

```
.venv/bin/pytest -q
# 163 passed, 2 skipped in 0.41s
```

The two skips are explicit (§7.3/§21.4 — never fake a Yosys result):

- `tests/golden/test_golden_designs.py::test_property_violating_fsm_skipped_without_sby`
  — property discharging needs sby (M6).
- `tests/golden/test_golden_designs.py::test_latch_inferring_design_skipped_without_yosys`
  — the latch ban is a C3 Yosys-level assertion.

Shell harness (also passing):

```
scripts/tests/run.sh    # 1/1 test scripts passed (12 assertions)
```

## Guesses / decisions made

1. **No PyYAML — hand-rolled YAML subset.** The environment has no network and
   cannot `pip install`, and PyYAML is not present. `design.yaml` uses a small,
   fixed subset (block/flow mappings and sequences, quoted/plain scalars, no
   block scalars/anchors), so I wrote `yaml_subset.py` to cover exactly that,
   with line provenance for the `src` spine. Two deliberate divergences from
   YAML: `on`/`off`/`yes`/`no` remain strings (avoids the YAML 1.1 footgun where
   a state named `ON` becomes a boolean), and only `true`/`false`/`null` are
   special. Switching to PyYAML later is a drop-in at the `parse` boundary.
2. **"Non-exhaustive transition sets" = no implicit self-loops.** This is the
   one place the design was genuinely ambiguous, and I picked the reading that
   makes the check *meaningful*. The front-end requires each state's outgoing
   guards to be pairwise disjoint (overlap → reject) and collectively a
   tautology (gap → reject, with the witness assignment and a hint to add an
   explicit `{from: S, to: S, when: "1"}` self-loop). Under an implicit-hold
   convention, "reject non-exhaustive" would be vacuous. **Consequence:** the
   §10.2 example as written is non-exhaustive (IDLE has only `arm & !fault`); my
   golden designs add the explicit self-loops. If implicit hold was intended,
   the exhaustiveness check should be deleted and this documented differently.
3. **Guard overlap is checked by exhaustive evaluation, not a BDD/SAT solver.**
   For each state, enumerate all `2**n` input assignments once and count true
   guards per assignment (0 → gap, ≥2 → overlap), giving witnesses for free.
   Cap `n ≤ 22` (≈4.2 M assignments); above that the front-end errors rather
   than sampling. This is the "small pure-Python SAT approach" §12 C1 permits,
   and it is exactly correct for the input sizes FSMs use here.
4. **`dfflegalize` flavour strings are unverified.** Yosys is not installed, so
   the `-cell $_DFF_P_ 01 -cell $_DFF_PN0_ 01 ...` list in
   `gatepack/synth/synchronous.py` (`FLOP_TYPE_MAP`) follows the §12 C3 example
   literally but is a best-effort mapping that **must be confirmed against the
   pinned Yosys at M0**. It is isolated in one constant precisely so that
   correction is a one-line change.
5. **Macros are noted, not instantiated, in generated Verilog.** M-cell
   behavioural models are an M8 deliverable; emitting a module instance with no
   model would produce broken Verilog. C1 records each macro (with its `src`
   line) as a comment and in the compile result, and `estimate` counts its
   internal flops (`M_CELL_FLOP_COUNTS`) and clock load.
6. **`properties.sv` is compiled at M2, discharged at M6.** The file is a real
   SystemVerilog module (DUT instantiated, clock, reset, `assert property` /
   `cover property` for invariant/mutex, a `cover` target for reachability, and
   a documented bound placeholder for liveness). It is emitted but never run
   here — no sby.
7. **Package count is a mapped-cell count upper bound; depth is unknown.** The
   verdict's `package count` comes from counting non-`$_` cells in
   `mapped.json` when Yosys runs (one gate per single-gate package — the C5
   packer will refine this); `combinational depth` needs a depth pass I did not
   write (no Yosys to validate it against), so it is reported `unknown`. Static
   current is likewise not computed (it is a C7 concern and project-defined).
8. **Clock fanout = flop count + clocked macros.** Flop count = state flops +
   2×(sync inputs) + 2×(reset de-assert synchroniser) + macro internal flops.
   Each macro adds one clock input pin on top. Documented in `model.py`.
9. **Exit-code contract:** `0` success / `1` error / `2` usage / `3`
   async-refused, as named constants in `gatepack/cli.py` and pinned in
   `tests/contract/`. `3` distinguishes "unsupported" from "invalid" so
   downstream tooling can tell them apart.
10. **`safe_state` int values are coerced to strings** in the schema (YAML
    parses `0`/`1` as ints; the model stores `"0"`/`"1"`/`"any"`).

## Design issues I believe are wrong or under-specified

- **§10.2 example transitions are non-exhaustive under any reading that makes
  "reject non-exhaustive" real.** The text lists "non-exhaustive transition
  sets" as a reject condition but its own example relies on implicit hold
  (IDLE → ARMED only when `arm & !fault`). The doc flags only the stale `vcc`
  value, not the transitions, so I treated the example as schema-shaped but
  added explicit self-loops to my goldens. This contradiction is worth a Draft 5
  note.
- **`truth_table.csv` has no schema anywhere in the document.** §1, §5, §10.3,
  §12 C1, and §17 reference it, but no section defines its columns or format,
  so I could not implement it and scoped M2 to `design.yaml` (FSM) only. The
  combinational goldens (2-input XOR, 3-to-8 decoder) are expressed as
  single-state FSMs with combinational `output_logic` instead.
- **§10.1 still says "`parts.refs.md`"** while §17 shows `74aup.refs.md`; M1
  already noted this (§BUILD-NOTES M1 #2), unchanged.
- **`DFF_S` contradiction** from M1 is unchanged (§9.2 "must be present" vs the
  §10.1 second-source rule excluding any single-sourced cell).

## Unfinished / not in this increment

- M0 toolchain spike: Yosys-level parse of `cells.lib`, `dfflibmap` mapping
  DFF/DFF_R/DFF_SR from the hand-written Liberty, `src`-survival measurement
  through `dfflibmap`/`abc`, and the timing-arc A/B are all still unverified —
  there is no Yosys here, and nothing fakes a result.
- `truth_table.csv` front-end (no schema; see above).
- M-cell behavioural models (M8) — macros are noted, not synthesised.
- Property *discharging* (M6) — the file is emitted, not run.
- The §6 `combinational depth` and static-current metrics (need synthesis + C7).
- C5 packer, C6 emitters, and the §10.3 `out/manifest.json` from a full `build`
  (M9/M10). The `estimate` manifest is a §6-verdict manifest, not the M10
  build manifest.

---

# BUILD NOTES — three defects + cells_sim.v + M8 + M5 (C4 verification)

## What was built

This increment closes three known defects, the M1 `cells_sim.v` gap, the M8
M-/S-cell libraries, and the M5 C4 verification component, and wires it into the
CLI.

### 1. Three defects

1. **Duplicate YAML keys** (`gatepack/frontend/yaml_subset.py`). Block and flow
   mappings now reject a repeated key with a line-numbered `ParseError`
   ("duplicate mapping key 'name' …"), instead of silently last-wins. A golden
   (`tests/golden/designs/duplicate_key.yaml`) and three unit tests pin it,
   including the quoted/plain collision (`name` vs `"name"`).
2. **Spec-driven C2 self-check** (`gatepack/liberty/{generator,validate}.py`).
   `flop_ff_requirements()` derives the required `ff` attributes per F-cell from
   `_FLOP_SPECS`, and `validate_library(text, expected, flop_requirements=…)`
   now checks them exactly (missing *and* unexpected). Regression tests assert
   a `DFF_R` without `clear` is rejected, and a `DFF` with a spurious `clear`
   is rejected. The self-check no longer shares the generator's blind spots
   (§19 R1).
3. **Dockerfile reproducibly pinned** (`Dockerfile`). Base image is now
   `debian:bookworm-slim@${BASE_DIGEST}` and the three tool checkouts are by
   commit SHA (`YOSYS_COMMIT`/`SBY_COMMIT`/`ESPRESSO_COMMIT`). **Every value is
   a `TODO(M0)` placeholder that is deliberately invalid, so the build fails
   loudly until M0 records the real values.** No digest/SHA was invented and
   presented as real.

### 2. `cells_sim.v` (M1 gap, [R4-17])

`gatepack/liberty/sim.py` emits behavioural Verilog models of every G- and
F-cell from the *same* `parts.csv` functions and `_FLOP_SPECS` the Liberty file
uses (`gatepack.liberty.boolean.translate_verilog` was added for `!`→`~`). Both
`gatepack estimate` and `gatepack verify` now write `build/cells_sim.v`.

### 3. M8 — M-/S-cells + tie-off

- `gatepack/macros/` — `CNT4` hand-written behavioural model
  (`models/CNT4.v`) + physical binding (`bindings.py` → 74LVC161/SO-16, pinout
  **candidate/unverified**). `load_models()` concatenates the models onto
  `cells_sim.v` — the *same files* C4 uses (§19 R25).
- `gatepack/infra/` — `supervisor.py` (the `SUPERVISOR` S-cell + its parameter
  checks: VCC range, asserted reset width vs. worst-case flop reset recovery,
  with the "cannot be checked" case surfaced as a finding, never a green pass);
  `reset.py` (the "every flop is reset-connected" check, implemented by scanning
  the *emitted* Verilog, so it is independent of C1's internal model); and
  `tieoff.py` (identity-value computation for spare/unused gate inputs).
- `libraries/74aup.csv` + `.refs.md` gained `CNT4` (M) and `SUPERVISOR` (S)
  rows; both are excluded from Liberty (tier), so the 13-cell G/F set is
  unchanged and no existing test broke.

### 4. M5 — C4 verification (`gatepack/verify/`)

- `base.py` — `VerificationStrategy` ABC, `VerifyConfig`, `CheckStatus`
  (including the distinct `bounded pass` and `not run` / `not applicable`
  states), `CheckResult`, `VerificationReport`, and a `ToolRunner` protocol
  (`SubprocessRunner` default) so everything is testable without tools.
- `equivalence.py` — the shared-front-end `golden_prep` (literally
  `yosys.common_frontend`, never copied), the `equiv_make -seq` →
  `equiv_induct` → `equiv_status -assert` script, the `equiv_simple` →
  `equiv_induct -seq N` (N raised) → sby miter fallback ladder, and parsers for
  `equiv_status` and sby BMC (BMC "PASS" → `bounded pass` carrying its bound).
- `simulation.py` — exhaustive-sim command construction, the runtime-cap
  decision (`not applicable` above the cap, never random vectors/coverage), a
  self-checking testbench generator (combinational `2**n` truth-table, and
  sequential BFS-driven (state × input) traversal), and result parsing.
- `mutation.py` — three faults (NAND→AND, flop D invert, reset-polarity flip) as
  pure text transforms on `cells.lib`/`cells_sim.v`, plus the assertion logic: a
  mutation is *detected* only when **both** checks fail.
- `synchronous.py` / `asynchronous.py` — the strategies; async refuses (§7.3).
- `run.py` — `run_verify` orchestration (C1→C2→C3→C4 + §9.5 checks) and the
  deterministic manifest.

### 5. CLI + tests

`gatepack verify <design.yaml> --library <csv> [--build dir]` was added (exit
0 = nothing failed and nothing unrun; exit 1 = failed or not-run; exit 3 =
async-refused). Tests: `tests/unit/{test_sim,test_macros,test_infra,test_verify}.py`
(new), a contract addition for the `verify` CLI surface, a golden addition
(`verify` reaches xor2/traffic-light), and `scripts/tests/test_verify.sh`.

## Test command and result

```
.venv/bin/pytest -q
# 219 passed, 2 skipped in 0.59s
bash scripts/tests/run.sh
# 2/2 test scripts passed (test_cli_e2e.sh: 12, test_verify.sh: 10)
```

The two skips are unchanged (property-discharge needs sby; latch-ban needs a
real Yosys run). The `verify` checks deliberately exit non-zero here because
Yosys/Icarus are absent — a verification that could not run is never a pass
(§14).

## What has NEVER been executed against a real tool

This is the single most important thing in these notes. **None of the following
has been run against a real binary; nothing was faked to make it look otherwise:**

- The **equivalence script** (`equiv_make -seq` / `design -stash` /
  `equiv_induct` / `equiv_status -assert`) is generated and its *construction*
  is unit-tested, but the exact `equiv_make`/`design -stash` invocation is a
  best-effort form and **must be confirmed against the pinned Yosys at M0** —
  exactly like the M2/M3 `dfflegalize` flavour strings.
- The **exhaustive testbench** is generated (and its shape is asserted) but has
  **never been compiled or run by Icarus**. The reset-flush count (4 clocks) and
  the clock-toggling convention are guesses until a real `iverilog`/`vvp` run.
- The **mutation suite's tool path** (re-map with the mutated library, re-run
  equivalence + sim) is written but **untested** — only its pure transform +
  detection logic is exercised (with synthetic results).
- The **sby BMC miter** is generated but never run.
- `cells_sim.v` models have never been simulated; the CNT4 model has never been
  compared against hardware or a real part.

## Guesses / decisions made

1. **The `equiv_make`/`design -stash` equivalence idiom is unverified** (above).
2. **Reset-recovery data is a placeholder.** `worst_flop_reset_recovery_ns`
   returns `max(tpd_ns)` over F-cells (reset recovery ≈ tPD order-of-magnitude).
   `parts.csv` has no recovery column (§10.1), so this is a documented proxy.
3. **`SUPERVISOR.reset_assert_min_ns = 200 ms`** is a candidate placeholder
   (typical supervisor delay); unverified.
4. **CNT4 → 74LVC161 pinout is candidate-only**, and the behavioural model
   exposes only CLK/RST_N/EN/Q; the parallel-load/ripple-carry pins (LOAD_N,
   ENT) are recorded as tie-offs, not modelled. `verified=False` throughout.
5. **M-cell models are appended to `cells_sim.v` unconditionally** (all known
   M-cells, not just the ones a design uses). Unused module definitions are
   harmless to Icarus and keep the "same files for sim and equivalence" rule
   trivial.
6. **`verify` takes `design.yaml` + `--library` + `--build`** (mirroring
   `estimate`), not the §17 `gatepack verify out/` form, because there is no
   M9/M10 `build` command producing `out/` yet.

## A real bug the new check found (and I fixed)

The §9.5 "every flop is reset-connected" check, implemented against the emitted
Verilog, immediately flagged the **input synchroniser flops** — C1 emitted them
as `always @(posedge clk)` with no reset, so they come up undefined after
power-on. I fixed `gatepack/frontend/verilog.py` to reset them (async-assert on
the raw reset, active polarity aware). This changes the generated Verilog for
every `sync` input but no flop count; all goldens still pass. This is precisely
the class of "undefined after power-on" bug the check exists to catch.

## Design issues I think are wrong or under-specified

- **`gatepack verify out/` (§17) needs the M9/M10 `build` command** that
  produces `out/` with `mapped.json`/`mapped.v`. Until then `verify` re-runs the
  front-end + C2 + C3 from `design.yaml`; the §17 signature is not yet
  implementable.
- **The exhaustive testbench must compare against the spec (truth table), not
  the behavioural Verilog**, because the mapped top module shares the golden's
  module name and cannot be co-instantiated. I compare against expected values
  computed from the compiled design. The design text says "compared against the
  truth table" (§C4.3) and this is consistent with it, but the module-name
  clash that forces it is not called out anywhere.
- **`equiv_status -assert` exit code vs. parsed text**: the parser keys on
  "Equivalence successfully proven" / "failed", which must be re-validated
  against the real Yosys output wording at M0.
- **Flop reset recovery has no schema field**; the proxy (tPD) is my invention
  and should become a real `parts.csv` column when datasheets are transcribed.

## Unfinished / not in this increment

- M0 toolchain spike: everything under "never executed against a real tool"
  above, plus the `src`-survival and timing-arc A/B measurements.
- M6 property *discharging* (sby) — `properties.sv` is still only emitted.
- C5 packer, C6 emitters (which will *apply* the tie-off values `infra/tieoff.py`
  computes), C7 analysis, C8 report (M9/M10).
- The C5 "M- and S-cells are never written to Liberty" invariant is still
  enforced by `select_for_liberty`; a regression test exists via
  `test_m_and_s_tier_excluded`.

---

# BUILD NOTES — M0 measured-defect pass (toolchain-corrections)

## What was changed

This pass applies the six measured defects from `docs/M0-FINDINGS.md` to the
existing source. Every change is a correction against a real Yosys 0.23 / Icarus
11.0 measurement, not a design-document assumption.

1. **Generated Verilog no longer emits an attribute before an `assign`.**
   `gatepack/frontend/verilog.py` now attaches provenance to `wire`/`reg`
   *declarations* only. Output logic (which has no declaration of its own) is
   emitted as an explicitly declared intermediate net (`wire {name}_int = ...`)
   followed by a bare `assign {name} = {name}_int;`. A golden regression test
   (`test_no_attribute_immediately_precedes_assign`) walks every line and asserts
   no attribute immediately precedes an `assign`.
2. **`src` renamed to `gp_src` everywhere.** Yosys populates `src` itself, so the
   emitted attribute is `gp_src` in C1, the new `gatepack/provenance.py`, and
   every test/script that asserts on it.
3. **Provenance rides on named nets.** C1 already put attributes on named nets for
   states/transitions/expressions; the output-logic fix above completes the
   picture so every carrier is a named net. A new pure helper
   `gatepack.provenance.net_provenance(verilog)` extracts which nets carry
   `gp_src`, so a coverage statement is about real net names. The mapped-cell
   association (net -> cell -> source, plus structural matching fallback) is
   **not** implemented — it is the M11b deliverable and needs a real
   `mapped.json`; nothing here fabricates one.
4. **Equivalence flow matches the measured M0 recipe.** `build_equivalence_script`
   now: writes `gold.v` from the shared front end, `design -reset`, re-`proc`s
   after each round-trip (`proc; opt; async2sync; opt` golden / `proc; flatten;
   opt; async2sync; opt` gate), reads `cells_sim.v` alongside the mapped netlist,
   and runs `equiv_make golden mapped equiv ; prep -top equiv ; equiv_simple ;
   equiv_induct ; equiv_status -assert`.
5. **One-hot initial state is set-via-feedback.** Every one-hot state flop now
   resets to 0; an all-zero detector (`set_feedback = ~(state_A | ...)`) is OR'd
   into the initial state's next term. No set-capable part (`DFF_S`) is needed.
   The cost is counted explicitly: `gatepack.estimate.one_hot_init_cost()` and a
   `one_hot_initial_state` block in the estimate manifest + a CLI line. The
   default encoding is unchanged.
6. **Single injectable runner module.** New `gatepack/toolchain.py` centralises
   `yosys_command` / `iverilog_command` / `vvp_command` (pure command-line
   functions, assertable without the binary) and `ToolchainRunner` (the only
   thing that shells out). `verify/base.py` re-exports `SubprocessRunner` as an
   alias so existing imports keep working; `estimate`, `verify/run`, and
   `verify/synchronous` now route every Yosys/Icarus call through it.

## Exact commands run and their real output

```
$ .venv/bin/pytest -q
234 passed, 2 skipped in 0.49s

$ bash scripts/tests/run.sh
== test_cli_e2e.sh ==
test_cli_e2e.sh: 12 passed, 0 failed
PASS test_cli_e2e.sh
== test_verify.sh ==
test_verify.sh: 10 passed, 0 failed
PASS test_verify.sh
==== summary: 2/2 test scripts passed ====
```

The two skips are unchanged and name their missing tool: property-discharge
needs sby (M6); the latch ban needs a real Yosys run (C3). No result is faked.

## What I could not fix, and why

- **The mapped-cell provenance association (M11b) is not built.** Defect 3's
  "associate each mapped cell with source via net provenance + structural
  matching" needs a real `mapped.json` from the pinned Yosys to develop and test
  against. I implemented the testable half (net-carried `gp_src` + the
  `net_provenance` extractor) and documented the rest as unbuilt, so coverage is
  reported honestly rather than implied.
- **No real tool run was possible.** The `gatepack-toolchain:probe` image exists
  but Docker cannot be run from this sandbox, and Yosys/Icarus/sby are not
  installed. All tool-dependent checks report `not run` with an explicit reason.
- **`equiv_status -assert` / `equiv_induct` wording** is still best-effort: the
  parser keys on "Equivalence successfully proven"/"failed", which must be
  re-validated against real Yosys output at M0.

## Claims still unverified against a real toolchain

Everything below is generated and its *construction* is unit-tested, but none of
it has been executed against a real binary:

- The corrected equivalence script (gold.v round-trip, `async2sync`,
  `cells_sim.v`, re-`proc`) has never been run — only its exact text is asserted.
- The one-hot set-via-feedback RTL has never been through `dfflibmap`/`abc`; the
  claim that it verifies end-to-end with the shipped library is inferred from
  M0's "all four flop variants map" and "both sides through the same front end"
  measurements, not from a fresh run.
- `dfflegalize` flavour strings (`FLOP_TYPE_MAP`) remain unconfirmed.
- The exhaustive testbench (reset-flush count 4, clock toggling) has never been
  compiled by Icarus.
- `gatepack.provenance.net_provenance` parses our own emitted Verilog; it has
  never been cross-checked against `premap.json`/`mapped.json` from a real run.
