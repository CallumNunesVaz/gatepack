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
