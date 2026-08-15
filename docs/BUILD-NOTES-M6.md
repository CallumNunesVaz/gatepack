# BUILD NOTES — M6 (properties via SymbiYosys) + `--json` output + §24.1 CPLD lint

Three deliverables landed together on branch `deepseek/m6-properties`, in the
order the brief required: (1) `--json` machine output, (2) M6 properties, (3)
the §24.1 CPLD-hostile construct lint.

## Test status

```
.venv/bin/python -m pytest tests -q
# 386 passed, 2 skipped   (baseline was 347 passed, 2 skipped)
```

The two skips are pre-existing (property-discharge and latch-inferring goldens,
both gated on tools that are not installed). No existing test was changed or
moved.

---

## 1. `--json` machine output

Added a `--json` flag to `compile`, `estimate`, `verify` and `build`. With the
flag, each command prints **exactly one JSON object to stdout** (no trailing
noise; single line) and every human diagnostic goes to stderr. Without it,
behaviour is byte-for-byte unchanged.

New files:

- `gatepack/diagnostic.py` — the `Diagnostic` shape (`severity`, `code`,
  `message`, optional `path`/`line`/`column`/`pointer`) and a documented
  GP-code scheme (`GP1000`..`GP1010`). `pointer` is populated wherever the code
  already has a §15.1 token.
- `gatepack/api.py` — the envelope builders (`envelope_ok`/`envelope_err`,
  `schema: 1`) and the per-command payload builders, matched field-for-field to
  `app/shared/api.ts`.

The envelope is emitted exactly as `api.ts` specifies; the contract is pinned in
`tests/contract/test_json_contract.py` (parse the JSON, assert the envelope and
payload shapes for all four commands, plus a failing `ok: false` case and the
"exactly one object on stdout" property).

### Honest gaps and deviations (recorded, not hidden)

These are fields the analysis modules do not compute yet, or places where the
`api.ts` type does not match what the tool can honestly say today:

- **`EstimateResult.packageCount` is `null` when Yosys is absent.** `api.ts`
  types it `number`; with no `mapped.json` there is no honest number, so the
  tool emits `null` and `cellCounts: {}`. Never a fabricated 0.
- **`AnalysisSummary.scoap` is always `[]`** and **`faults` is always all-zero**
  (§13.1 SCOAP and §13.2 stuck-at are explicitly out of scope of the current
  `gatepack/analysis` module — see its `__init__.py`).
- **`Check.durationMs` is always 0.** The `ToolchainRunner` does not time
  subprocesses; wiring a real clock into it is a small, separate change.
- **Structural checks mapped to `kind: "property"`.** `api.ts`'s `Check.kind`
  is a closed enum (`equivalence|simulation|mutation|property|hazard`); the two
  §9.5 S-cell checks ("flop reset connectivity", "supervisor parameters") are
  neither of the five but must have *some* kind. I mapped them to `property`
  (they are spec-sensibility invariants) and documented the judgment call here.
- **`BomLine.singleSourced` counts manufacturers only** (`len(manufacturers) <
  2`), exactly as `api.ts` defines it — equivalents are *not* counted, even
  though the C2 second-source rule (`§10.1 [R4-9]`) does count them. This is a
  real (small) semantic divergence between the CSV rule and the JSON marker.
- **`EstimateResult.reasons` is my invention** — `api.ts` gives it only as
  `string[]`. I emit one string per red/amber metric plus nothing for green.

## 2. M6 — properties discharged by SymbiYosys

**`docs/M6-FINDINGS.md` landed mid-build (measured against real sby in
`gatepack-toolchain:m6`) and I treated it as authoritative, same standing as
`M0-FINDINGS.md`.** It overrides §11 in three places that change the work, and I
followed it rather than the brief's assumptions:

1. **C1's property emission changed** (`gatepack/frontend/verilog.py`). The
   brief said "the front-end already emits assertions"; M6-FINDINGS §1 measured
   that `assert property (@(posedge clk) ...)` **does not parse** in Yosys 0.23
   (no open-source SVA). Emission now uses immediate assertions inside a clocked
   `always`, with `disable iff` folded into an `if (f_past_valid && <not-reset>)`
   guard. §2 additionally requires a reset wrapper (`f_past_valid` + `assume`)
   or true invariants fail spuriously at step 1 — emitted too. This **moved** the
   existing `test_properties_file_emits_assertions` (M6-FINDINGS §1 says the old
   assertion is invalid); the test now pins the immediate-assertion form.
2. **Cover tasks use `mode cover`, not `mode bmc`** (M6-FINDINGS §4: `mode cover`
   reports the step a cover statement is reached).
3. **The parser follows the measured output format** (M6-FINDINGS §3–§3.1):
   `returned pass for basecase`/`returned pass for induction`, `Assert failed in
   <mod>: <label>`, `Reached cover statement at <label> in step N`,
   `DONE (PASS|FAIL, rc=...)`. The §3.1 parsing trap — both modes emit `returned
   pass`, so status is keyed on the *mode the driver chose*, never a summary
   line — is honoured, as is the §2 rule that induction-pass + basecase-fail is
   a missing-reset signature (failed), **not** a bounded pass.

New files:

- `gatepack/verify/properties.py` — task enumeration, `.sby` generation, output
  parsing (measured format), VCD extraction, check assembly, `run_properties`.
- `gatepack/toolchain.py` gained `sby_command` (`sby -f <file>`).
- `gatepack/frontend/verilog.py` labels every property `gp_assert_N`/
  `gp_cover_N` and emits a `cover` for **liveness** (previously a comment) as a
  bounded reachability target.

Wired into `gatepack verify` as an additional set of checks, plus a
`--properties-only` flag that runs only the §11 checks (no synthesis, no
equivalence/simulation/mutation, no §9.5 checks).

### The one behaviour that matters: vacuity

Every `invariant`/`mutex` property produces **two** sby tasks — a `prove`
(assertion) task and a `cover` (antecedent) task. A property whose assertion
passes but whose antecedent cover is unreached is reported as a **failure**
(vacuous), never as a pass. The four-way status is honoured exactly:
`prove` (basecase+induction pass) → `passed`; `prove` basecase-pass +
induction-fail → `bounded` with `bound`; `cover` reached → `bounded` with the
reached step; FAIL → `failed`; missing tool → `not_run`.

### What is honestly NOT verified

`sby` is **not installed on this machine**, so the end-to-end discharge has
never run. The parser is tested against *hand-written* fixtures in the measured
format; the discharge is not. Specifically:

- The `.sby` task syntax in `build_sby_file` (per-task `[label]` sections with
  `:options`/`assert`/`cover` selection) is **still best-effort** —
  M6-FINDINGS gives the sby *output* format, not the input file grammar, so the
  `.sby` file may need correction against a real run.
- **The properties-module clock is still a self-toggling `reg`**
  (`always #1 clk = ~clk`) inherited from C1's simulation-style wrapper. sby's
  smtbmc drives a clock input; a `#1`-delay oscillator is a simulation construct
  and very likely incompatible. M6-FINDINGS' working example has `clk` as a free
  input. I did **not** convert the wrapper to a clock-input form because I
  cannot verify either choice without sby — this is the #1 item to resolve when
  the tool exists. I expect it to mean "make `clk`/`rst_n` inputs to the
  `*_properties` module".
- `parse_vcd` is a minimal VCD parser tested against a hand-written fixture. For
  **multi-bit** signals (binary/gray state vectors) it stores the raw bit string
  rather than a `'0'|'1'|'x'` scalar — a deviation from the `api.ts` doc, which
  reads as written for the one-hot default (single-bit state signals).
- `Counterexample.pointers` is best-effort: it names the `properties` and
  `states` provenance tokens but does **not** recover the exact transition(s)
  implicated from the VCD signal values.
- The `.sby`'s sby pin: M6-FINDINGS §5 measures that no tagged sby release works
  with Yosys 0.23 and pins a bare commit (`beb8b3c6…`). I did not touch the
  Dockerfile; the pin is a toolchain action item, not a code change.

A missing `sby` reports every property check as `not_run` with
`skippedReason: "sby not found on PATH"` — visible, never a silent pass. The
`--properties-only` flag still requires `--library` even though it does not use
it (the flag reuses the shared `verify` parser); noted as a small UX wart.

## 3. §24.1 — CPLD-hostile construct lint

New file `gatepack/analysis/cpld.py`: `lint_verilog` (memory declarations,
latch-inferring combinational `always` blocks) and `lint_netlist` (surviving
`$_` cells, `$_DLATCH_*`/`$_SR_*` latches, `$mem*` memories), combined in
`lint_cpld`. Every diagnostic carries `code=GP1009`, `severity=warning`, and a
`path`/`line` where the detector has one.

Surfaced in three places, as required:

- `AnalysisSummary.cpldBlockers` in the `build --json` payload;
- a "CPLD fallback (§24.1)" section in `report.md`, naming the alternative flow
  that consumes `generated.v`;
- a golden test (`tests/golden/test_golden_designs.py`) that fails if any golden
  design's output trips the lint — the correct result is an empty list.

The negative tests in `tests/unit/test_cpld.py` (memory decl, latch-inferring
`always`, `$_DLATCH_`/`$mem`/`$and` cells) prove the lint can actually fire; a
lint that cannot fail is worthless (§24.1).

**Heuristic honesty:** the Verilog-side detectors are coarse text scans, not a
parser. The latch detector flags "a combinational `always` with an `if` and no
`else`/default" — it cannot see through `case`-based incomplete assignment or
`always_comb` (not emitted by C1, but possible in hand-fed input). C1 never emits
either construct, so the goldens are clean; the detector exists to catch a
hostile or hand-written input, not to be a complete latch checker.

---

## Least-confident items

1. **The properties-module clock.** C1 still emits a self-toggling
   `always #1 clk = ~clk`, which is a simulation construct and almost certainly
   wrong for sby (whose engine drives a clock input). M6-FINDINGS' working
   example has `clk` as a free input. I left it because I cannot verify either
   form here, but I expect the fix to be "make `clk`/`rst_n` inputs".
2. **The `.sby` file grammar.** M6-FINDINGS gives the *output* format (which my
   parser now matches), not the input `.sby` syntax; `build_sby_file`'s
   per-task `[label]` sections are still best-effort.
3. **The `EstimateResult.packageCount = null` deviation.** It is the honest value
   without Yosys, but it violates the `api.ts` `number` type and the renderer
   (or the main-process validator) may need to accept `null` for a not-run
   synthesis — which contradicts the "never fake a result" rule if it is
   rejected. (Also: `durationMs` is always 0; no clock in `ToolchainRunner`.)
