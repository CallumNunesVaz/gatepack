# gatepack — Design Document and Build Plan

**Status:** Draft 4.1
**Date:** 2026-08-15
**Licence:** GPL-3.0-or-later
**Supersedes:** Draft 3 (async backend scoped for v0.1.0; provenance assumed to
survive synthesis; `dfflibmap`/`dfflegalize` conflated; no v0.1.0 scope cut)

**Prior-art survey (Draft 4.1):** §24 records what was adopted, declined and
kept for interoperation after surveying the logic-simulator field, and
`docs/M0-FINDINGS.md` supersedes this document wherever they conflict — it
contains measurements from a real Yosys, this document contains assumptions.

**External review:** Draft 3 was reviewed by DeepSeek v4-pro
(`docs/reviews/2026-08-15-deepseek-v4-pro.md`). Findings accepted are folded
into the text below and marked **[R4-n]** at the point of change. Two findings
were rejected or amended; see §23.4.

---

## 1. Purpose

`gatepack` compiles a truth table or finite state machine specification into a
bill of materials and schematic netlist built from discrete logic packages, and
provides a desktop application for authoring, visualising, verifying and
analysing those designs.

It exists to make discrete logic a *maintainable* implementation target. The
existing options are hand minimisation (error-prone, unreviewable, effectively
unversionable) or a programmable device (which reintroduces vendor toolchain
lock-in). `gatepack` closes that gap: ASCII source in git, a deterministic
build, and a machine-checkable proof that the gate netlist implements the
specification.

### 1.1 Scope of designs

The tool is general across four axes, not tuned to one design:

| Axis | Range |
|---|---|
| Inputs | 1 to many. No assumed width. |
| Logic | Purely combinational through multi-state sequential |
| Timing model | **Synchronous** and **asynchronous** (§7) |
| Duty cycle | Continuously clocked, intermittently clocked, and event-driven |

This generality changes the role of the viability assessment. Draft 2 treated
gate count as a go/no-go gate on *building the tool*. It is instead a
**per-design verdict the tool produces** (§6): `gatepack estimate` reports
whether discrete implementation is sensible for a given specification, and says
so plainly when it is not. A tool that silently emits a 200-package BOM has
failed at its job.

### 1.2 Non-goals

Named explicitly so no one mistakes the output for a complete design:

- **Placement and routing.** Output is a netlist, not a layout.
- **Timing closure.** `gatepack` reports cumulative propagation delay from
  Liberty data. It does not model PCB parasitics and is not static timing
  analysis. **[R4-16]** "No STA" is not "no timing model": the §6 viability
  verdict and the §9.6 clock report both depend on the coarse cumulative-tPD
  model, which is therefore in scope and must be accurate enough to gate on.
- **Clock tree synthesis.** The tool *reports* the clock distribution problem
  (§9.6); it does not solve it.
- **Power supply design.** S-cells (§9.5) are **selected and
  compatibility-checked against declared parameters, never designed or
  optimised.** The tool does not size regulators, choose crystals, or perform
  power sequencing.
- **Quantitative reliability.** Single stuck-at fault analysis is provided
  (§13.2). FMEDA, failure rates, diagnostic coverage and safe failure fraction
  are not — they require part-level failure data the tool does not have.
- **Analogue anything.**
- **Curated schematic sheet layout.** **[R4-15]** C12 *does* render a schematic
  (netlistsvg), so "no schematic generation" was self-contradictory. The
  non-goal is narrower: no multi-sheet, human-curated, manufacturing-quality
  schematic. Auto-layout is a review aid; the sheet a person signs is drawn by
  a person.

### 1.3 Project context

Personal FOSS project, publishable and deployable in a workplace under GPL-3.0.
Two consequences are binding:

- **All bundled examples must be synthetic.** Invented interlocks and
  sequencers only. Nothing derived from employment work, which keeps the
  repository permanently clear of IP and export-control questions.
- **DO-330 is an architectural posture, not a deliverable.** The output-verified
  structure (§14) is retained because it is good engineering. No qualification
  artefacts are produced.

---

## 2. Name

`gatepack` — from the two stages that constitute the tool's core work: gate
mapping, then package packing.

Availability checked 2026-08-15: PyPI available, npm available, crates.io
available, GitHub repository name search returns zero results, no trademark
conflicts found. Rejected: `tinylogic` (onsemi/Fairchild trademark),
`gatesmith`, `gatewright`, `jellybean` (all taken).

---

## 3. Design principles

1. **Do not reimplement solved problems.** Logic optimisation, technology
   mapping and schematic rendering are handled by Yosys, ABC, Espresso and
   netlistsvg.
2. **Text is canonical; the GUI is a view.** Every design semantic lives in
   YAML or CSV. Delete the application and lose nothing but convenience. This is
   the specific line whose crossing would recreate the vendor lock-in the tool
   exists to avoid.
3. **The tool's output is independently verified.** Formal equivalence runs on
   every build. The tool may be wrong; the check must catch it.
4. **Constraints are enforced mechanically, not by review.** Second-sourcing is
   a property of the cell library, so synthesis *cannot* emit a single-sourced
   design.
5. **Reproducible builds.** Same commit plus same container yields a
   byte-identical netlist. The GUI is not in the reproducible path.
6. **Fail loudly on suspicious success.** An implausibly good gate count is the
   characteristic symptom of a malformed cell library.
7. **Nothing in CI depends on the desktop application.**
8. **Report the consequence; let the engineer decide.** Test point placement,
   packing overrides, M-cell selection and macro suggestions are all surfaced
   with their costs, never applied silently.

---

## 4. Licensing

`gatepack` is GPL-3.0-or-later.

| Component | Licence | Integration |
|---|---|---|
| Yosys | ISC | bundled binary, child process |
| ABC | BSD-style (UC Berkeley) | via Yosys |
| SymbiYosys / sby | ISC | bundled binary, child process |
| Espresso (maintained fork) | BSD-style (UC Berkeley) | bundled binary |
| Icarus Verilog | GPL-2.0+ | child process |
| netlistsvg | MIT | npm dependency |
| elkjs | EPL-2.0 | transitive via netlistsvg |
| React Flow | MIT | npm (core only — verify no Pro features used) |
| Electron | MIT | application shell |
| KiCad | GPL-3.0+ | file interchange only |
| Digital (hneemann) | GPL-3.0 | **no code or data linked** — optional file interchange and cross-check only (§24) |

EPL-2.0 (elkjs) is weak-copyleft at file scope, consumed unmodified as a
library, so it does not constrain the GPL-3.0 choice. Confirm by licence audit
at M11 rather than assuming.

---

## 5. Architecture

```
┌─ Desktop application (Electron) ─────────────────────────────────┐
│  Renderer (React)                      Main process (Node)       │
│  ┌────────────────────────────┐        ┌──────────────────────┐  │
│  │ C10 Spec editor            │        │ C9  Session manager  │  │
│  │ C11 Truth table grid       │◄─IPC──►│     file I/O, watch  │  │
│  │ C12 Schematic view         │        │     git status       │  │
│  │ C13 Packing / BOM view     │        └──────────┬───────────┘  │
│  │ C14 Analysis dashboard     │                   │ child_process│
│  │ C15 Verification panel     │                   ▼              │
│  └────────────┬───────────────┘        ┌──────────────────────┐  │
│               └── linked selection ────┤ gatepack core (CLI)  │  │
│                   bus (§15)            │ + bundled binaries   │  │
│                                        └──────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
                                │
                                ▼
        design.yaml / truth_table.csv / parts.csv     ← canonical, git-tracked

Core pipeline:

  spec ─► [C1] front-end ─► behavioural Verilog + properties
                                  │
                                  ├─► [C3] synthesis ─────► mapped netlist
                                  │     ├ SynchronousBackend
                                  │     └ AsynchronousBackend
                                  │
                                  └─► [C4] verification ◄──┘
                                        ├ equivalence (both)
                                        ├ properties (both)
                                        ├ exhaustive sim (both)
                                        ├ mutation (both)
                                        └ hazard analysis (async only)

  parts.csv ─► [C2] Liberty gen ─► lib ──► C3
  mapped netlist ─► [C5] packer ─► [C6] emitters ─► BOM, KiCad netlist
                                └─► [C7] analysis ─► [C8] report
                                      ├ power / clock
                                      ├ SCOAP testability
                                      └ stuck-at fault
```

### 5.1 Why Electron rather than a browser app

The decisive reason is **verification**. The WebAssembly Yosys distribution
excludes `sby` and `yosys-smtbmc`; only the main `yosys` application is
available in the JavaScript package. A browser-only build could synthesise and
render but could never run the formal checks that justify the architecture.
Electron's main process spawns native `yosys`, `sby` and `espresso`, so the
application runs the *same* verification the CLI does.

Secondary: designs open in place in a git working tree rather than being
uploaded; air-gapped by construction with no server and no network permission;
native Yosys is roughly twice the speed of the WASM build.

Costs, accepted: ~150–250 MB installer, per-platform code signing, an update
mechanism, and a larger security surface (§5.2).

A WASM fallback (`@yowasp/yosys`, ISC) is retained as an optional degraded mode
for a possible browser build — synthesis and rendering only, verification
visibly marked unavailable.

### 5.2 Electron security posture

- `nodeIntegration: false`, `contextIsolation: true`, `sandbox: true`.
- Privileged operations behind a narrow `contextBridge` API. The renderer never
  touches `fs`, `child_process`, or arbitrary paths.
- Every IPC payload schema-validated in the main process. Treat the renderer as
  untrusted.
- Strict CSP; no remote content, ever. No telemetry; no update check unless
  explicitly enabled.
- Bundled binaries hash-pinned and verified at launch; mismatch is a hard
  failure.
- File access scoped to the opened project directory.

---

## 6. Viability assessment

`gatepack estimate` runs the front-end and synthesis only, and emits a verdict
before any BOM is produced. This is a headline feature, not a development gate.

Metrics and default thresholds (all configurable per project):

| Metric | Green | Amber | Red |
|---|---|---|---|
| Package count | ≤ 25 | 25–50 | > 50 |
| Flop count | ≤ 8 | 8–15 | > 15 |
| Clock net fanout | ≤ 8 | 8–15 | > 15 |
| Combinational depth | ≤ 6 | 6–10 | > 10 |
| Static current (Σ IQ at 125 °C) | project-defined | | |

Amber prompts input-space collapse (§6.1) and re-measurement. Red emits an
explicit recommendation against discrete implementation, naming the binding
metric and suggesting alternatives (a flash CPLD such as MAX V with portable
inferred Verilog, or a mixed-signal PLD where the design is supervisory).

The flop count and clock fanout are **independent** of gate count. A design can
pass on gates and fail on clocking: fifteen flops in fifteen packages is a clock
net with fifteen distributed loads and no clock tree, and skew may be the
binding constraint (§9.6).

### 6.1 Input-space collapse

Suggested automatically where detectable, applied never:

- Mutually exclusive or one-hot input groups → encode.
- Inputs live only in specific states → state-gate them.
- Inputs only ever appearing OR'd (faults, interlocks, ready lines) →
  pre-combine into an aggregate condition.

### 6.2 State encoding

**Synchronous designs only.** **[R4-6]** Draft 3 stated a global one-hot default
and then required single-variable-change assignment for async (§7.2). Those are
flatly incompatible: every one-hot transition changes two state bits, which is a
critical race by construction in an asynchronous machine. One-hot is a
*synchronous* default. Async state assignment is a separate mechanism (§7.2) and
never inherits this setting.

Default **one-hot**. Each state flop's D input reduces to a small AND-OR term
and no state decoder is required — the flop output *is* the state signal. This
spends flip-flops to save combinational gates and inter-package routing, the
correct trade when every gate is a separate package.

Counter-pressure: one-hot maximises flop count and therefore clock distribution
difficulty (§9.6). Where the FSM is linear-sequential, a Johnson counter M-cell
(§9.4) delivers one-hot outputs from a single package and sidesteps both
problems at once.

For asynchronous designs, state assignment is a different problem entirely —
see §7.2.

---

## 7. Timing models

`design.yaml` carries a top-level `timing_model: synchronous | asynchronous`.
This selects a **backend strategy pair** — one synthesis strategy and one
verification strategy — and switches the front-end validation rules.

```
SynthesisBackend (interface)
├── SynchronousBackend     dfflibmap → abc -liberty
└── AsynchronousBackend    Espresso hazard-free cover → constrained mapping

VerificationStrategy (interface)
├── SynchronousVerify      equivalence + properties + exhaustive + mutation
└── AsynchronousVerify     the above + hazard analysis + fundamental-mode check
```

Shared across both: C1 front-end, C2 Liberty generator, C5 packer, C6 emitters,
C7 analysis, C8 report, the provenance map, and the entire desktop application.
Divergent: optimisation policy, state assignment, and verification method.

The strategy boundary is designed in from M4, not retrofitted. The reason is
specific and non-negotiable: **ABC's redundancy removal is correct for
synchronous logic and destroys hazard-freedom in asynchronous logic.** It cannot
be a runtime flag on a shared path.

### 7.1 The asynchronous hazard problem

Suppressing a static hazard requires *keeping* redundant consensus terms in the
cover. ABC removes redundant terms, because for synchronous logic that is
exactly right — the glitch settles before the next clock edge.

Consequence: an async netlist optimised by ABC can be **formally equivalent to
its specification and still glitch on real silicon**. Equivalence checking
compares steady-state functions and says nothing about transient behaviour. This
is why the async path needs its own verification strategy, not just its own
mapper.

### 7.2 Asynchronous backend requirements

- **Hazard-free cover.** Minimise with Espresso to a cover satisfying the
  adjacency condition — every pair of adjacent on-set minterms covered by a
  common product term. In practice this means retaining prime implicants a
  minimal cover would drop.
- **Constrained mapping.** Map the AND-OR form structurally (Yosys `techmap`
  with a custom map file) rather than through ABC's optimising scripts. Accept a
  worse gate count as the price of correctness, and report the delta against
  what the synchronous path would have produced.
- **Race-free state assignment.** Single-variable-change assignment, validated
  rather than assumed. Critical races are a distinct failure mode from the
  encoding choice in §6.2.
- **Fundamental-mode assumptions declared and checked.** The entire method
  collapses if two inputs can change simultaneously. `design.yaml` must declare
  which inputs are mutually exclusive in time; C1 rejects designs that do not.
- **Essential hazards.** Cannot be fixed by logic — only by inserted delay in
  feedback paths. C4 detects and reports them; mitigation is a **delay element
  S-cell** (§9.5) the designer places explicitly.

### 7.3 Why asynchronous synthesis is deferred to v0.2

**[R4-1]** Draft 3 treated the async backend as an 8-day milestone carrying
elevated risk. Review identified three problems that are not risks to be managed
but unsolved-in-general research problems:

1. **Factoring destroys hazard-freedom.** A hazard-free cover is hazard-free *as
   a two-level structure*. The G-cell inventory tops out at fan-in 3, so any
   product term with more than three literals must be factored into multiple
   levels — and multi-level decomposition of a hazard-free two-level cover is
   not hazard-preserving in general. "Structural `techmap` with a custom map
   file" therefore cannot just transcribe the AND-OR form; it has to constrain
   decomposition, which is the hard part and was unscoped.
2. **State assignment.** Single-variable-change assignment is not a setting on
   the §6.2 encoder; it needs a distinct transition-diagram/STT method, and
   validating race-freedom is its own algorithm.
3. **Espresso does not emit hazard-free covers by default.** Neither the default
   heuristic nor exact minimisation (`-Dso`) guarantees the adjacency condition.
   The hazard-free cover must be constructed and then independently verified,
   not requested.

**Decision.** v0.1.0 ships the *strategy interface* (M4) and the async
*front-end and verification* path, but `AsynchronousBackend.synthesise()`
**detects and refuses** with a clear verdict rather than emitting a netlist that
may glitch. A netlist that is formally equivalent and hazardous on the bench is
the worst possible output of this tool — worse than no output, because it
survives review. Real async synthesis is a v0.2 research task (§23.3).

If async synthesis is later re-scoped into v0.1.0, it is constrained to
≤3-literal product terms and single-variable-change encodings, with both limits
stated in the report.

**This remains the highest-risk component in the plan** (R15). The constrained
mapper has no off-the-shelf equivalent, and generated code here should be
treated as a first sketch.

---

## 8. Cell library model

Four tiers, distinguished by how they enter the design.

| Tier | Contents | How it enters the netlist |
|---|---|---|
| **G** | Combinational gates | Inferred by ABC via `abc -liberty` |
| **F** | Flip-flops | Inferred by Yosys via `dfflibmap -liberty` |
| **M** | Counters, shift registers, sequencers | **Instantiated explicitly**; never inferred |
| **S** | Reset supervisor, oscillator, clock buffer, delay element, tie-off, test point | **Selected and parameter-checked**; never synthesised |

**[R4-7]** Asynchronous primitives — the Muller C-element above all — are
**M-cells, not a fifth tier**. A C-element is a state-holding majority gate with
no two-level Boolean equivalent, so neither an Espresso cover nor ABC can
produce one; the Draft 3 open question ("do they fall out of the hazard-free
cover?") is answered *no* (§21.7). It is instantiation-only with a hand-reviewed
behavioural model, which is exactly the M-cell contract, so it reuses that
machinery rather than adding a tier.

---

## 9. Cell inventory

All part numbers below are **candidates requiring datasheet confirmation**
before entry into `parts.csv` (risk R8). Availability at the target temperature,
second-source status and IQ must each be verified per part.

### 9.1 G-cells — combinational

Inverter, buffer, NAND2/3, NOR2/3, AND2/3, OR2/3, XOR2, XNOR2, 2:1 MUX,
AND-OR-invert, and the configurable multi-function gates.

Configurable gates (1G57 / 1G58 / 1G97 / 1G98 / 1G99 in AUP numbering)
implement different functions depending on input tie-off. Model each
configuration as a **distinct Liberty cell sharing a `part_suffix`**, then
deduplicate at BOM time. ABC cannot see this equivalence; the C5 post-pass must.

**[R4-10] Consolidation does not happen by itself.** C5's deduplication can only
merge cells ABC *already chose* as the configurable type. It cannot re-map a
`1G00` into a `1G57`, so with uniform `area = 1.0` ABC has no reason to prefer
configurable parts and the part-diversity win never materialises. Two mechanisms,
either of which is real work and neither of which was in Draft 3:

- **Area biasing.** Weight configurable cells below dedicated gates in the
  Liberty `area` field so ABC prefers them. Cheap to implement, blunt, and it
  distorts the area metric that §10.1 also uses as a cost proxy.
- **Post-map cell-merge pass.** After mapping, rewrite dedicated-gate instances
  into configurable-gate instances where the function matches and the tie-off is
  available. Correct, but a new C5 sub-pass with its own equivalence obligation.

v0.1.0 ships area biasing behind a per-library flag and reports part diversity
as a metric, so the trade is at least visible. The merge pass is deferred.

### 9.2 F-cells — flip-flops

**[R4-2] Draft 3 got the mechanism wrong.** It attributed the fallback behaviour
to `dfflibmap`. Corrected:

- `dfflibmap` maps `$_DFF_*` cells to Liberty cells. If no library cell matches a
  given flop flavour, it **leaves the cell unmapped and warns** — it does not
  silently synthesise the missing feature out of gates. C3's "no surviving `$_`
  cells" assertion then errors the build.
- **`dfflegalize` is the pass that does the conversion**, rewriting an
  unsupported flop flavour into a supported one plus glue logic: a reset into an
  AND on D, an enable into a feedback mux. It must be run explicitly, before
  `dfflibmap`, and told which flavours the library actually supports.
- `-nodffe` is a **`dfflegalize`** flag, not a `dfflibmap` flag.

The *consequence* Draft 3 described is nonetheless real and important: with reset
and enable variants missing, `dfflegalize` inflates a 10-flop FSM by 20–30 gates
for no reason — enough to produce a spurious Red verdict at §6. Only the
attribution changes, not the conclusion.

| Cell | Function | Candidate part | Why it must be present |
|---|---|---|---|
| `DFF` | D-type, no reset | 1G79 | Baseline |
| `DFF_R` | Async active-low reset | 1G175 | Otherwise reset becomes an AND on every D input |
| `DFF_S` | Async set | — | One-hot initial state needs exactly one set flop |
| `DFF_SR` | Async set and reset | 1G74 | Full reset semantics |
| `DFFE` | Clock enable | — | Otherwise each becomes a feedback mux, 2–3 gates each |

**[R4-3] Required Liberty `ff` group contents**, since "proper `ff` groups" was
too vague to implement against:

| Cell | `ff` group must define |
|---|---|
| `DFF` | `next_state`, `clocked_on` |
| `DFF_R` | above + `clear` |
| `DFF_S` | above + `preset` |
| `DFF_SR` | above + `clear` **and** `preset`, plus `clear_preset_var1`/`var2` to fix set-vs-reset dominance so it matches `$_DFFSR_*` semantics |
| `DFFE` | `next_state : "MUX(en, d, q)"` — the mux-form enable |

The `DFFE` form is the most fragile mapping in `dfflibmap` and its behaviour is
version-dependent. **[R4-4] v0.1.0 therefore does not bet the gate-count story
on Liberty enable mapping:** the default is `dfflegalize`-generated mux-feedback
enables, with the mux cost reported **explicitly** as a line item rather than
left as unexplained gate count. Liberty `DFFE` mapping is available behind a
per-library opt-in flag, validated by a golden design, for the case where a real
enable-capable part exists and the mapping demonstrably works on the pinned
Yosys version.

**Latches are banned in synchronous designs.** `dfflibmap` will map transparent
latches happily. With per-package arrival skew and no common substrate,
level-sensitive latches are a hazard generator. C3 errors on any surviving
`$_DLATCH_*` or `$_SR_*` cell.

Asynchronous designs use cross-coupled feedback by construction, which is a
different mechanism and is permitted only through the async backend, never by
accidental latch inference.

### 9.3 F-cell design rules

- Single clock domain by default. A second domain requires explicit declaration
  and forces synchronisers on every crossing.
- Every declared async input generates a two-stage synchroniser, counted in the
  gate budget and shown in the schematic view.
- Reset is async-assert, sync-de-assert. The de-assert synchroniser is
  generated, not assumed.

### 9.4 M-cells — macro sequential parts

Counters and shift registers exist as MSI parts, and **Yosys will not infer
them** — Liberty cannot usefully express a 4-bit counter for ABC mapping.

Each M-cell has two artefacts: a **behavioural Verilog model** (hand-written,
reviewed, used by C4 for equivalence) and a **physical binding** to part number,
package and pinout (used by C5/C6).

| M-cell | Function | Candidate part | Notes |
|---|---|---|---|
| `CNT4` | 4-bit synchronous binary counter | 74LVC161/163 | Higher IQ than AUP |
| `CNT12` | 12-stage ripple counter | 74HC4040 | Ripple output; not for synchronous logic |
| `SIPO8` | 8-bit shift register | 74LVC164 | |
| `PISO8` | 8-bit shift register, parallel load | 74LVC165 | |
| `JOHN10` | Johnson decade counter, one-hot out | 74HC4017 | See below |
| `DIV2N` | Ripple divider | 74LVC4040 | Clock division only |
| `CELEM` | Muller C-element | discrete / 2-gate | **[R4-7]** Async primitive; instantiation-only, hand-reviewed model |

**[R4-8] VCC compatibility is a hard constraint on this table.** It mixes three
families with incompatible supply ranges — 74AUP (0.8–3.6 V), 74LVC
(1.65–5.5 V), 74HC (2–6 V). At the `vcc: 1.8` of the §10.2 example, **the 74HC
parts do not operate at all**, and the design would have shipped a BOM that
cannot be built. `parts.csv` gains `vcc_min` / `vcc_max` columns (§10.1) and C1
rejects any cell whose supply range excludes the project VCC. This is a
mechanical check, not a review item.

`JOHN10` is a one-hot state sequencer in a single package. For a
linear-sequential FSM — advance, advance, advance, reset — it collapses the
state register and its next-state logic into one part, eliminating both the gate
count and the clock-fanout problem. C1 detects compatible topology (simple cycle
or chain, no branching) and *suggests* it. It cannot be applied automatically:
branching transitions break it.

M-cells carry a power warning. 74LVC and 74HC draw substantially more static
current than AUP; a single 74HC4017 can dominate a design otherwise built from
sub-µA parts. C7 reports M-cell static contribution as a separate line so the
trade is visible.

### 9.5 S-cells — infrastructure

Parts that appear in the BOM and netlist but carry no logic function.

| S-cell | Purpose | Checked against |
|---|---|---|
| `SUPERVISOR` | Power-on reset | Threshold vs VCC; asserted width vs worst-case flop reset recovery; push-pull vs open-drain |
| `OSC` | Clock source | Frequency, stability, IQ, temperature grade |
| `CLKBUF` | Clock fanout relief | Drive capability vs flop count; added tPD |
| `DELAY` | Essential hazard mitigation (async) | Delay vs required minimum from C4 |
| `PULLUP` | Open-drain termination | Value vs leakage budget |
| `TESTPOINT` | Declared observation node (§13.1) | — |

Discrete logic has no internal power-on reset: every flop comes up undefined.
Modelling the supervisor as an S-cell means the BOM is complete and buildable
rather than carrying an implicit hole.

Two checks fall out for free, both catching real bugs nothing currently detects:

- **Every flop is reset-connected.**
- **Asserted reset width exceeds worst-case flop reset recovery time** from
  Liberty data.

S-cells carry the same power trap as M-cells: a supervisor drawing 1–2 µA
dominates a design of 0.9 µA gates. C7 breaks out S-cell static current
separately.

### 9.6 Clock and reset distribution

The largest structural weakness of discrete implementation. Twenty flops in
twenty packages is a clock net with twenty distributed loads, no clock tree, and
skew scaling with trace length. A monolithic device solves this in silicon;
discretes do not solve it at all.

- C7 reports flop count, clock net fanout, estimated worst-case skew budget, and
  margin against `tCO + tSU + skew`.
- Configurable design rule caps flop count (default 12).
- Where fanout exceeds source drive capability, C7 recommends a `CLKBUF` S-cell
  and reports the added tPD.
- The report states plainly that skew estimation excludes PCB routing and is
  advisory. Actual skew is a layout property.

### 9.7 Unused inputs and spare gates

A 2G package with one gate used leaves a spare gate whose inputs float near
Vcc/2, turning both transistors partially on. The resulting crowbar current
**increases** with temperature — precisely the parameter being optimised.

Handled in three places:

- **C5 (avoidance).** Spare gates are a cost in the packing objective, not free.
  The packer will sometimes select more packages to avoid leaving spares.
- **C6 (tie-off).** Every unconnected input is tied in the emitted netlist —
  spare gate inputs to a rail, unused inputs of used gates to the function's
  identity value. Direct rail tie-off is the default; resistive tie-off (a
  `PULLUP` S-cell) only where a datasheet requires it, since a resistor per
  input is a worse BOM and worse leakage than a trace.
- **C7 (reporting).** Spare gate count and estimated leakage penalty, reported
  as a line item.

**Packing efficiency metric change.** Gates ÷ packages is now wrong: it *drops*
when the packer correctly avoids spares, punishing the desired behaviour.
Efficiency is replaced by a cost function —

```
pack_cost = Σ(package_cost) + spare_count × spare_leakage_weight
```

— with package count and spare count reported alongside, so neither is hidden
inside a ratio.

---

## 10. Data model

### 10.1 `parts.csv`

```csv
cell,tier,family,part_suffix,equivalents,function,inputs,gates_per_pkg,package,mfrs,vcc_min,vcc_max,area,tpd_ns,iq_ua
INV,G,AUP,1G04,,!A,1,1,SOT-353,"TI;Nexperia;Diodes",0.8,3.6,1.0,4.6,0.9
NAND2,G,AUP,1G00,,!(A&B),2,1,SOT-353,"TI;Nexperia;Diodes",0.8,3.6,1.0,5.1,0.9
NAND2x2,G,AUP,2G00,,!(A&B),2,2,VSSOP-8,"TI;Nexperia",0.8,3.6,1.0,5.1,0.9
DFF,F,AUP,1G79,,,2,1,SOT-353,"TI;Nexperia",0.8,3.6,1.0,7.2,0.9
DFF_R,F,AUP,1G175,,,3,1,SOT-353,"TI;Nexperia",0.8,3.6,1.0,7.5,0.9
JOHN10,M,HC,HC4017,,,3,1,SO-16,"TI;Nexperia;onsemi",2.0,6.0,8.0,,4.0
SUPERVISOR,S,-,TPS3839,"APX803:Diodes;NCP303:onsemi",,1,1,SOT-23,"TI",1.6,6.0,2.0,,0.15
```

**[R4-9] The second-source model changed.** Draft 3's rule — "two or more
entries in `mfrs`" — means *this exact part number is made by N manufacturers*.
That works for jellybean logic (`74AUP1G00` really is made by TI, Nexperia and
Diodes) and is **wrong for everything else**. The Draft 3 example line
`SUPERVISOR,S,TPS3839,...,"TI;Diodes"` was a datasheet error: TPS3839 is a TI
part number. Diodes does not make it. What Diodes makes is APX803, a
*functionally equivalent, differently numbered* alternate — which the schema had
no way to express, so the rule would have either rejected every supervisor or
been satisfied by fabricated data.

Corrected model, two columns:

- `mfrs` — manufacturers of **this** part number.
- `equivalents` — alternate part numbers with their manufacturers, as
  `PN:mfr;PN:mfr`. Each requires its own citation in `parts.refs.md`, and
  pin-compatibility must be confirmed, not assumed.

Rules:

- A cell is second-sourced if `len(mfrs) + len(equivalents) ≥ 2`. Otherwise it is
  **excluded from the generated Liberty file** unless `--allow-single-source`,
  which fails CI by default. Mechanical enforcement of second-sourcing.
- **[R4-8]** `vcc_min`/`vcc_max` must bracket the project VCC or the cell is
  excluded, with the reason printed.
- `family` exists so 74LVC is a **data** addition rather than a code change
  (§21.2), even though v0.1.0 ships 74AUP only.
- M-cells and S-cells are excluded from the Liberty file entirely — they are
  never inference targets.
- `area` is the cost metric ABC minimises. Default 1.0 per gate; configurable to
  footprint mm² or unit price.
- All electrical data transcribed from datasheets with a citation in
  `parts.refs.md`. Nothing inferred or remembered.
- **[R4-21] The citation rule is enforced mechanically**, per principle 4.
  Draft 3 backed R8 with "two-person review", which a personal FOSS project
  cannot supply — an uncheckable control is worse than an acknowledged gap,
  because §14 then claims evidence that does not exist. Instead:
  `gatepack lib check` fails if any row lacks a `parts.refs.md` entry naming
  datasheet document number, revision and table/page for each electrical value;
  citations are pinned by document revision so a silent datasheet update is
  visible as a diff; and the golden "degenerate library must fail" and "FSM with
  reset + enable" designs (§18) catch the transcription errors that matter most.
  Human review is still valuable and still recommended — it is simply no longer
  claimed as a control.

### 10.2 `design.yaml`

```yaml
name: interlock_fsm
timing_model: synchronous          # or: asynchronous

clock: {signal: clk, freq_hz: 32768, source: OSC}
reset:
  signal: rst_n
  active: low
  async_assert: true
  sync_deassert: true
  source: SUPERVISOR               # S-cell, §9.5

encoding: one_hot

inputs:
  - {name: arm, sync: true}
  - {name: fault_a, sync: true}
  - {name: fault_b, sync: true}

outputs:
  - {name: enable}
  - {name: fault_led}

expressions:
  fault: "fault_a | fault_b"

states: [IDLE, ARMED, RUNNING, FAULT]
initial: IDLE

transitions:
  - {from: IDLE,    to: ARMED,   when: "arm & !fault"}
  - {from: ARMED,   to: RUNNING, when: "arm"}
  - {from: RUNNING, to: FAULT,   when: "fault"}
  - {from: FAULT,   to: IDLE,    when: "!arm & !fault"}

output_logic:
  enable:    "state == RUNNING"
  fault_led: "state == FAULT"

# §11 — checked against the behavioural source, not the netlist
properties:
  - {name: safe_enable,       kind: invariant,    expr: "!(enable & fault)"}
  - {name: fault_recoverable, kind: reachability, from: FAULT, to: IDLE}
  - {name: no_deadlock,       kind: liveness,     expr: "all states reach IDLE"}

# §13.2 — safe direction for stuck-at classification
safe_state:
  enable: 0
  fault_led: any

# §13.1 — user-declared; tool reports the consequence
test_points:
  - {net: state_RUNNING}
  - {net: fault}

macros:
  - {instance: dwell, cell: CNT4, clock: clk, enable: "state == RUNNING"}

# asynchronous designs only
fundamental_mode:
  mutually_exclusive: [[arm, fault_a], [arm, fault_b]]

constraints:
  max_flops: 12
  max_packages: 40
  vcc: 3.3                         # [R4-8] see §21.1; 1.8 excludes all 74HC M-cells
  max_static_ua: 20
```

### 10.3 Artefacts

| Artefact | Format | Committed |
|---|---|---|
| `<name>.gpk` | text — multi-document YAML | Yes — canonical, **single-file form** (§10.4) |
| `design.yaml`, `truth_table.csv`, `parts.csv` | text | Yes — canonical, **exploded form** (§10.4) |
| `design.layout.json` | JSON — node positions | **No** — gitignored |
| `build/generated.v`, `build/properties.sv` | Verilog | No — review artefacts |
| `build/mapped.json`, `build/cells.lib` | JSON, Liberty | No |
| `out/bom.csv`, `out/netlist.net` | CSV, KiCad | Yes |
| `out/report.md`, `out/manifest.json` | Markdown, JSON | Yes |

Node positions never enter `design.yaml`. Auto-layout with elk or dagre and
store nothing, or store in the gitignored sidecar. This keeps diffs about logic
rather than pixels.

### 10.4 Single-file project format

A whole project — specification, truth table, and optionally its cell library —
can live in **one file**, so a design can be mailed, attached to a ticket,
dropped in a gist, or opened by double-clicking, without the recipient having to
reassemble a directory.

**The format is plain multi-document YAML, never an archive.** This is the
binding constraint and it follows directly from principle 2. A zip or tar
container would give the same portability and destroy the property that
justifies the whole tool: `git diff` showing that a guard changed from
`arm & !fault` to `arm`, review comments anchored to a line, `grep` finding
every design that uses a part. A bundle you cannot diff is a binary, whatever
its extension, and it recreates precisely the vendor lock-in §1 exists to avoid.

```yaml
# interlock.gpk — one file, three documents
%YAML 1.2
---
gatepack: 1                      # format version, first key, always present
kind: design
name: interlock_fsm
timing_model: synchronous
# ... exactly the §10.2 design.yaml content ...
---
gatepack: 1
kind: truth_table
columns: [arm, fault_a, fault_b, enable]
rows:
  - [0, 0, 0, 0]
  - [1, 0, 0, 1]
---
gatepack: 1
kind: library                    # optional — see below
source: 74aup.csv
sha256: 3f9a…                    # of the exploded CSV, for provenance
parts:
  - {cell: INV, tier: G, family: AUP, part_suffix: 1G04, ...}
```

**Two equivalent representations, one semantic model.**

| Form | Shape | Best for |
|---|---|---|
| **Exploded** | `design.yaml` + `truth_table.csv` + `parts.csv` | git-tracked work, review, CI |
| **Single-file** | `<name>.gpk` | sharing, archiving, opening by double-click |

Neither is privileged. C1 accepts either and produces identical downstream
artefacts, and the conversion is lossless in both directions:

```
gatepack project bundle  ./            -o interlock.gpk    # explode -> single
gatepack project explode interlock.gpk -o ./               # single  -> explode
```

**Round-tripping must be byte-deterministic**, and a golden asserts
`explode(bundle(x)) == x` and `bundle(explode(y)) == y` for every §18 reference
design. Sorted keys, no timestamps, fixed document order (§C6). A format that
silently reorders or reformats on save makes every diff unreadable and would
quietly defeat its own purpose.

**The library document is optional, and the choice is a real trade.** Embedding
`parts.csv` makes the file genuinely self-contained and pins the exact library
the design was verified against, which serves reproducibility (§5.5) — the
recipient cannot accidentally build against a different revision. Referencing it
by path keeps one library shared across many projects, which is how a team
actually maintains part data. Both are supported; embedding records the source
filename and a `sha256` so a later divergence between embedded and on-disk
library is *detectable* rather than silent, and `lib check` reports it.

**What the file must never contain**, each for a reason already established:

- **Node positions.** §10.3 is unchanged: layout lives in the gitignored
  sidecar, so diffs stay about logic rather than pixels.
- **Build artefacts** (`build/`, `out/`). They are derived, and embedding
  derived data invites it to go stale and be trusted.
- **Binary blobs of any kind.** If it cannot be read in a text editor, it does
  not belong.

**Extension.** `.gpk`, documented as plain YAML and safe to open in any editor.
A distinct extension exists to give the desktop application a file association
(§16 C9, whose project scope widens from *a directory* to *a directory or a
`.gpk`*); it is not a claim to a proprietary format. Availability of the
extension is unchecked and should be confirmed alongside the §2 name search.

**Milestone.** Fold into **M2** (C1 already owns spec parsing and gains one
loader plus one writer) with the CLI verbs and round-trip goldens; the C9 file
association follows at **M12**.

---

## 11. Properties

Equivalence checking proves netlist ≡ generated Verilog ≡ spec. It proves
nothing about whether the spec is *correct*: a specification error propagates
cleanly through every check and emerges as a verified BOM.

Properties close that gap. They are declared in `design.yaml` (§10.2), compiled
by C1 to SystemVerilog assertions, and discharged by sby.

**Properties are checked against the behavioural source, not the mapped
netlist.** This keeps them orthogonal to equivalence — equivalence proves the
implementation matches the spec; properties prove the spec is sensible. Two
independent failure modes, two independent checks. Checking properties on the
netlist instead would let them pass vacuously on a degenerate result.

Kinds: `invariant` (always true), `reachability` (state B reachable from A),
`liveness` (bounded, with a documented bound), `mutex` (signals never
simultaneously asserted).

For asynchronous designs the same machinery expresses hazard-freedom
obligations, which is a second reason to have it.

---

## 12. Core components

### C1 — Front-end

Parses `design.yaml` or `truth_table.csv`, validates against a pydantic schema,
emits behavioural Verilog plus a properties file.

- Verilog carries `(* src = "..." *)` attributes tying every construct to its
  source location (§15).
- One-hot default; `binary` and `gray` available. Async uses race-free
  assignment (§7.2).
- Reject unreachable states, non-exhaustive transition sets, and overlapping
  guards. Guard overlap is checked with a SAT call, not by inspection.
- Emit synchroniser chains for `sync` inputs and reset de-assert.
- Instantiate M-cells; emit their behavioural models for C4.
- Bind S-cells and check declared parameters (§9.5).
- Detect Johnson-counter-compatible topology and surface as a suggestion.
- For async: require and validate `fundamental_mode` declarations.

### C2 — Liberty generator

`parts.csv` → `cells.lib`.

- `cell` blocks with `area`, `pin` directions, `function`.
- Sequential cells with proper `ff` groups (`next_state`, `clocked_on`, `clear`,
  `preset`) so `dfflibmap` can map them.
- Timing arcs from datasheet tPD at target VCC, selected per (`family` × VCC).
  **[R4-11, amended]** Review asserted that `abc -liberty` is purely
  area-driven and that timing arcs therefore cannot affect mapping at all. That
  overstates it — Yosys's default ABC script uses ABC's `map`, which is
  delay-driven with area recovery and does read Liberty timing. The safe,
  agreed part of the finding stands: arcs are **primarily** for the C7 delay
  report and for `dfflibmap` arc sanity, and delay-*constrained* mapping needs
  `abc -constr`, which is not planned. **M1 resolves this empirically** — map a
  golden with and without timing arcs on the pinned Yosys and record whether the
  result changes. Do not write either claim into the report until measured.
- Drop single-sourced cells; print what was dropped and why. Drop M- and
  S-cells.
- **Self-check:** verify the file parses under Yosys and the cell count matches
  expectation. A Liberty file that parses into a degenerate library is the most
  likely silent failure in this system.

### C3 — Synthesis

Dispatches on `timing_model` to a `SynthesisBackend` (§7).

**SynchronousBackend:**

```
# --- common front end: shared verbatim with C4's golden_prep (§C4) ---
read_verilog -sv build/generated.v
hierarchy -check -top <top>
proc; flatten; opt
                              # [R4-5] NO bare `fsm` — see below
select -assert-none t:$mem t:$memrd t:$memwr    # [R4-13] assert, don't hope
techmap; opt
setundef -zero                # [R4-12] BEFORE the split, so both sides match
select -assert-none t:$_DLATCH_* t:$_SR_*       # §9.2 latch ban
write_json build/premap.json  # [R4-14] provenance capture point (§15.1)
# --- end common front end ---

dfflegalize -cell $_DFF_P_ 01 -cell $_DFF_PP0_ 01 ...   # [R4-2] explicit
dfflibmap -liberty build/cells.lib
abc -liberty build/cells.lib
clean
stat -liberty build/cells.lib
write_json build/mapped.json
write_verilog -noattr build/mapped.v      # [R4-17] for Icarus (§C4.3)
```

Three corrections to the Draft 3 script, all of which would have caused silent
wrong behaviour:

**[R4-5] The bare `fsm` pass is removed.** `fsm` expands to
`fsm_detect; fsm_extract; fsm_opt; fsm_recode; fsm_map`, and `fsm_recode`
defaults to `-encoding auto` — it will **re-encode the state register**,
typically to binary. C1 has already chosen one-hot deliberately (§6.2), so
running `fsm` silently discards the design's central trade ("the flop output
*is* the state signal") *and* breaks equivalence by making the two sides'
encodings diverge. Since C1 is the RTL generator, there is nothing for `fsm` to
recover; it is pure downside. If FSM extraction is ever wanted, it is
`fsm -encoding one-hot` with a golden asserting the encoding is stable across
the pinned version — never bare `fsm`.

**[R4-12] `setundef -zero` moves before the split.** In Draft 3 it ran after
`abc`, so `mapped.json` had don't-cares resolved to 0 while the behavioural
golden still carried `x`. Equivalence would then either disagree spuriously or
need `-undef` handling on one side only. Resolving undefs in the shared front
end means both sides see identical don't-care semantics by construction.

**[R4-2] `dfflegalize` is explicit.** The set of supported flop flavours is
derived from `cells.lib`, and the glue-logic cost it introduces is captured and
reported per §9.2 rather than appearing as unexplained gate count.

**[R4-13] `memory_map`** is replaced by an assertion. Draft 3 said "should
no-op; error if it fires" — but `memory_map` is silent, so there was nothing to
detect. `select -assert-none t:$mem` actually fails the build. C1 must also be
pinned to emit truth tables as combinational `case`/`$pmux`, never as memory.

**AsynchronousBackend:** Espresso hazard-free cover → structural `techmap` with
a custom map file → no ABC optimisation pass. Reports gate-count delta against
what the synchronous path would have produced.

Both: error on any surviving `$_`-prefixed cell (netlist not implementable);
error on `$_DLATCH_*`/`$_SR_*` in synchronous mode; pin the Yosys version into
`manifest.json`.

`dfflibmap` **must** precede `abc` — ABC is combinational-only, and omitting
this is a common and confusing failure.

### C4 — Verification

**The most important component. Build it before the packer.**

Dispatches on `timing_model` to a `VerificationStrategy`.

Both strategies:

1. **Formal equivalence.** **[R4-12] Draft 3's formulation would not have
   closed.** `equiv_make` cannot compare raw behavioural `generated.v` — with
   `always` blocks and surviving `$process` cells — against a library-mapped
   `mapped.json`. Both sides must be brought to a common abstraction first.

   The mechanism is a **`golden_prep` script that is literally the same text as
   C3's common front end** (§C3), shared from one file so the two cannot drift:
   the golden runs `proc; flatten; opt; techmap; opt; setundef -zero` and then
   **stops**, before `dfflegalize`/`dfflibmap`/`abc`. Then `equiv_make -seq`
   against `mapped.json`, `equiv_induct`, `equiv_status -assert`.

   Sharing the front end is also what makes k-induction *close*: induction
   requires the two sides' state encodings to correspond bit-for-bit, which
   holds only if neither side re-encodes. This is the second reason `fsm` is
   removed **[R4-5]**.

   **Fallback terminology, corrected.** Draft 3 said "where induction does not
   close, SymbiYosys BMC" — conflating two mechanisms. sby is for §11
   *properties*. The equivalence fallback ladder is `equiv_simple`
   (combinational cones) → `equiv_induct -seq N` with N raised → and only then a
   hand-built miter BMC'd in sby, which is a separate construction and not a
   drop-in. M-cells compared against their behavioural models.
2. **Properties** (§11) discharged by sby against the behavioural source.
3. **Exhaustive simulation.** Combinational: all 2ⁿ vectors through the mapped
   netlist under Icarus, compared against the truth table. Sequential:
   exhaustive over (state × input) transitions.

   **[R4-17] Prerequisite Draft 3 omitted entirely:** Icarus cannot read Yosys
   JSON, and the Liberty file contains no Verilog, so there is nothing to
   simulate. C2 must additionally emit **`build/cells_sim.v`** — behavioural
   Verilog models of every G-, F-, M- and S-cell — and C3 must
   `write_verilog build/mapped.v`. The M-cell models here and the ones C4 uses
   for equivalence must be *the same files*, or mutation testing silently
   compares a model against itself. This is a real M5 dependency and is now
   scheduled (§20).

   **[R4-18] Random-vector fallback is cut.** Above the exhaustive limit the
   tool does **not** fall back to random vectors with a coverage figure. A
   coverage percentage on random stimulus reads as reassurance while proving
   nothing, and formal equivalence (check 1) is the actual guarantee at any
   width. Behaviour above the cap: report exhaustive simulation as *not
   applicable*, state that correctness rests on equivalence, and offer random
   vectors only as an explicitly-labelled smoke test that never contributes to
   a green status (§21.4).
4. **Mutation testing.** Inject a deliberate fault — swap NAND for AND, invert a
   flop's D input, flip a reset polarity — and assert checks 1–3 **fail**. Runs
   in CI on every commit.

Asynchronous only:

5. **Hazard analysis.** For each single-input-change transition, verify no
   output glitch is possible in the mapped cover.
6. **Essential hazard detection.** Report, with the minimum delay required for
   mitigation, feeding a `DELAY` S-cell.
7. **Fundamental-mode check.** Verify declared mutual exclusions are consistent
   with the transition set.

Check 4 is not optional. An equivalence check that passes vacuously is worse
than no check, because it survives design review. The mutation suite is the only
thing distinguishing a real proof from a misconfiguration.

### C5 — Packer

Constrained bin packing. Nothing off the shelf does it; expect to iterate, and
treat generated code as a first draft.

- Group by function type. A 74AUP2G02 holds two NOR2 gates, not one NOR and one
  NAND.
- Deduplicate configurable-gate configurations sharing a `part_suffix` (§9.1).
- **Spare gates are a cost** in the objective (§9.7), not free.
- **Packing is advisory.** Two gates sharing a package must be physically
  adjacent, or packing trades package count for long traces and added routing
  capacitance — the opposite of the design intent. Emit both unpacked and packed
  netlists with per-package rationale; overrides persist in `design.yaml`.
- Report `pack_cost`, package count and spare count separately.

### C6 — Emitters

- BOM CSV: part number, manufacturers, package, quantity, reference designators,
  tier, unit price where available.
- KiCad `.net` s-expression netlist, including tie-offs (§9.7), S-cells and
  declared test points. **[R4-20]** Three cases Draft 3 left unspecified and
  which KiCad treats as distinct: rail tie-offs emit as **global power
  references** (power symbols), not ordinary nets; genuinely unconnected pins
  emit `no_connect` flags; and S-cells carry no logic `function`, so C5, C6, C7
  (SCOAP) and C12 must each special-case them — no cone, no fault injection, no
  ABC.
- **[R4-19] Reference designator stability, corrected.** Draft 3 derived the
  refdes from "a hash of the logic cone", which cannot work: a refdes identifies
  a *package*, and two gates sharing a package have different cones. Worse, ABC
  re-optimises globally, so one small edit churns many cones and renumbers a
  board that barely changed — the exact failure the scheme existed to prevent.

  Replaced by a three-stage pipeline, each stage deterministic:

  1. **Stable cell naming.** Each mapped cell gets an identity from its function
     plus the topologically-ordered hash of its input cones.
  2. **Deterministic packing.** C5 is a pure function of the named cell set.
  3. **Stable refdes assignment.** Assigned in sorted order over packages, with
     the cell→refdes mapping recorded in the provenance map (§15.1) rather than
     recomputed.

  Churn under re-optimisation is reduced, not eliminated. C6 reports refdes
  delta against the previous build so renumbering is visible before layout,
  never discovered after.
- Deterministic: sorted output, no dict-order dependence, no timestamps in
  payload.

### C7 — Analysis

See §13.

### C8 — Report generator

Assembles C7 output into `report.md`, with every estimate carrying its
assumptions inline rather than in a footnote.

---

## 13. Analysis

### 13.1 Testability (SCOAP)

Test points are **user-declared** in `design.yaml`. The tool reports the
consequence rather than choosing placement.

- Compute SCOAP combinational controllability (CC0, CC1) and observability (CO)
  across the netlist.
- **Delta analysis** — run with and without each declared test point, so the
  report states what each one buys: "TP3 makes 12 additional nets observable;
  TP4 makes 1." That tells you where the next one should go, and whether an
  existing one earns its footprint.
- List nets that remain unobservable regardless. Those are the faults
  undetectable at ICT, worth knowing before layout rather than after.

### 13.2 Fault analysis

Single stuck-at analysis, reusing C4's exhaustive vector infrastructure. A
25-package design is roughly 100 fault simulations — seconds.

- For each package pin, inject stuck-at-0 and stuck-at-1, re-run the vector set,
  record which outputs diverge.
- Classify against the declared `safe_state` (§10.2): **safe-fail**,
  **dangerous-fail**, or **undetected**. Undetected is derived from §13.1 — a
  fault that changes no observable output cannot be detected at test.
- **Independence statement:** package count, and the fact that each is a
  separate die with separate bond wires. This is the common-cause argument for
  discrete over monolithic implementation, and it is only claimable because the
  BOM documents the structure.

**Explicitly excluded, and stated as such in the report:**

- **Open-circuit faults.** A floating CMOS input is indeterminate, not a logic
  value, and cannot be simulated as stuck-at. Reported as "requires analysis"
  rather than given a fabricated result.
- **Quantitative reliability.** Failure rates, diagnostic coverage and safe
  failure fraction need part-level failure-mode data the tool does not have.

The report states plainly: this is a single-point stuck-at analysis, not a
safety case, and not a substitute for one.

### 13.3 Power and clock

- Static current: Σ IQ at target temperature with datasheet derating, **broken
  out by tier** — G, F, M and S separately, because a single M- or S-cell can
  dominate a sub-µA design.
- Spare-gate leakage penalty (§9.7).
- Dynamic current estimate, flagged as excluding inter-package routing
  capacitance, which will dominate. State the assumption; do not present the
  number as a budget.
- Clock report per §9.6.
- Worst-case combinational depth and cumulative tPD, with the explicit caveat
  that this excludes PCB parasitics and is not STA.

---

## 14. Verification and qualification posture

| Claim | Evidence |
|---|---|
| Mapped netlist implements the specification | Formal equivalence, CI-enforced |
| The specification itself is sensible | Properties discharged by sby |
| Equivalence check is not vacuous | Mutation suite, CI-enforced |
| Async netlist is hazard-free | **v0.2.** v0.1.0 claims nothing here — it refuses to synthesise async (§7.3) |
| M-cells behave as modelled | Behavioural model equivalence, hand review |
| Every BOM line is second-sourced | Cell library construction, CI-enforced |
| Build is reproducible | Container digest + output hash comparison in CI |
| Synthesis engine is mature | Yosys/ABC/Espresso, long track record |
| GUI cannot affect correctness | CI has no dependency on the application |

The last row is why principle 7 exists. Keeping the desktop application strictly
a view over CLI-produced artefacts keeps it out of any future qualification
path.

---

## 15. Linked selection and provenance

The dynamic, linked UI requirement reduces to one hard problem: mapping
artefacts back to source. Everything else is rendering.

### 15.1 Provenance spine

**[R4-14] Draft 3's second bullet was the single most load-bearing false
assumption in the document.** It asserted that Yosys propagates `src` attributes
through to the mapped cells in `write_json`. It does not survive the passes that
matter: `dfflibmap` and `abc` *replace* cells with library instances that carry
no attributes, and ABC renames freely. Attributes survive `proc`, `flatten`,
`opt` and `techmap` reasonably well, and then are lost at exactly the boundary
the UI needs. So the map "source ↔ mapped cell ↔ refdes ↔ BOM" had no spine on
the mapped netlist — which is precisely what C12 renders and what M16's linked
selection reads. The Draft 3 caveat ("many-to-many and lossy") was too generous:
the default state on the mapped netlist is *total* loss, not partial.

Since linked selection is "the feature that makes the application worth
building" (§15.2), the whole GUI rationale rested on this. Revised spine:

- C1 emits Verilog carrying `(* src = "design.yaml:42:transitions[2]" *)`.
- **Provenance is captured pre-ABC**, from `build/premap.json` (§C3), where
  attributes are still intact.
- **Forward-matching to the mapped netlist is an explicit algorithm, not an
  assumption.** Match pre-map cells to post-map cells by structural
  correspondence — connectivity and cone signature — and record a confidence per
  link. Where ABC has merged or duplicated logic, a link is many-to-many; where
  it has restructured beyond recognition, there is no link and the map says so.
- C5 records which mapped cell landed in which package.
- `gatepack` assembles the **provenance map**: source construct ↔ Verilog line ↔
  pre-map cell ↔ mapped cell (with confidence) ↔ package refdes ↔ BOM line.

**This is now a first-class design item with its own spike (M0, §20), run before
M16 is scheduled.** If structural matching turns out to give poor coverage on
the golden designs, that is a finding that must land early — it would mean
scoping linked selection down to source↔pre-map↔package (dropping gate-level
highlighting in the schematic view), and that is a decision worth making in
week one rather than at M16.

**Honest limitation, retained and sharpened:** the map is many-to-many, lossy,
and now additionally probabilistic. The UI must render partial provenance
gracefully — show what is known, grey what is not, distinguish high- from
low-confidence links, and never imply a false one-to-one.

### 15.2 Selection model

```ts
type Selection =
  | {kind: 'state',      id: string}
  | {kind: 'minterm',    index: number}
  | {kind: 'input',      name: string}
  | {kind: 'cell',       name: string}
  | {kind: 'net',        name: string}
  | {kind: 'package',    refdes: string}
  | {kind: 'transition', from: string, to: string}
  | {kind: 'property',   name: string}
  | {kind: 'fault',      pin: string, stuck: 0 | 1}
```

Every view both emits and reflects selection:

| Select this | Highlights |
|---|---|
| A truth table row | Gates active for that minterm; resulting output nets |
| A gate in the schematic | Its BOM line, package, and the truth table rows it affects |
| A state in the FSM graph | Its flop, next-state cone, output logic |
| A transition edge | The guard's gate cone and source YAML line |
| A package card | All contained gates, highlighted in the schematic |
| An input | Its full fanout cone across every view |
| A failing property | The states and transitions in the counterexample trace |
| A dangerous-fail fault | The package, and the outputs that diverge |

Hover previews; click pins. Multi-select unions the highlight sets.

This is the feature that makes the application worth building. Without it, six
panels showing six unrelated things is worse than six CLI outputs, because it
implies a connection it does not deliver.

---

## 16. Desktop application

### C9 — Session manager (main process)

Project open/close scoped to **a directory or a single `.gpk` file** (§10.4),
file watching with debounce, git status, child-process lifecycle, incremental
build orchestration and cancellation, schema-validated IPC.

Opening a `.gpk` explodes it into a temporary working form; saving re-bundles it
deterministically. The user sees one file; the core sees the same semantic model
either way, so nothing downstream of C1 knows which form was opened.

### C10 — Spec editor

Three synchronised representations of the same `design.yaml`: Monaco text editor
with schema-aware completion; structured form for inputs, outputs, properties,
constraints; FSM graph (React Flow) with states as nodes and transitions as
labelled edges. Text is authoritative; a graph edit is a document mutation, not
a separate model. Positions go to the gitignored sidecar.

### C11 — Truth table grid

Editable grid with `-` for don't-care. **Live computed outputs** from the
specification, evaluated client-side — arithmetic, no synthesis needed.
**Simulated outputs** from the mapped netlist in an adjacent column with
per-row divergence highlighting: C4's exhaustive check rendered interactively,
showing exactly which minterm disagrees. Coverage indicator for specified,
don't-care and unreachable minterms.

**Live minimised-cover preview** (§24.2). Alongside the columns above, show the
current Espresso cover and an estimated package count, recomputed on a debounced
sub-second core call within the §16.1 `< 1 s` synthesis-preview budget.

The reason is principle 8. §6.1 already suggests input-space collapse — encode
one-hot groups, state-gate inputs, pre-combine OR'd faults — but a suggestion
without a number is advice the engineer cannot weigh. Showing the cover shrink as
don't-cares and collapses are edited turns each suggestion into a visible cost
delta, and lets §6.1 cite a measured figure rather than a category. The
suggestion is still never applied automatically.

### C12 — Schematic view

**netlistsvg**, not React Flow. It consumes Yosys `write_json` directly and lays
out with elkjs, producing IEEE gate symbols and orthogonal routing. React Flow
would give rounded rectangles and bezier edges — which no engineer accepts as a
schematic view, and which would mean reimplementing symbol rendering and
orthogonal routing from scratch.

Layers: mapped netlist (logical), packed netlist (package boundaries as
containers), and an overlay for test points and unobservable nets from §13.1.

**Per-vector signal-value overlay** (§24.2). For a selected minterm, state, or
property counterexample, colour every net by its simulated 0/1 value for that
vector.

§15.2 currently maps a truth table row to *which gates are active* — membership.
Value is strictly more informative, and C4 already computes the exhaustive
vectors, so this is a rendering increment over data that exists rather than new
analysis. It is what turns C12 from a picture into a debugger, and it is the
clearest expression of the linked selection that justifies building the
application at all. Schematic-capture simulators (Logisim-evolution, Digital)
get their teachability almost entirely from this one affordance.

C12 remains a **rendering**, never an editor (§24.3).

### C13 — Packing and BOM view

Package groupings as cards, drag-to-regroup, live `pack_cost` and spare count,
per-group rationale, override writing back to `design.yaml`. Adjacent BOM table
with second-source status and a hard visual marker on any single-sourced part.

The view most likely to justify the GUI: reviewing packing against board
adjacency is a genuine interactive judgement that text handles badly.

### C14 — Analysis dashboard

Live metrics against the `constraints` block, red on violation: package count,
spare count, flop count, clock fanout, static current by tier, worst-case tPD,
`pack_cost`. Plus the §6 viability verdict, the SCOAP delta table, and the
stuck-at classification summary.

### C15 — Verification panel

**[R4-25] Four states** per check, not three: **passed**, **bounded pass**,
**failed**, **not run**. The fourth exists because k-induction does not always
close and BMC is the fallback (§21.5) — rendering a bounded result as a plain
green tick would recreate the vacuous-pass failure mode R2 and R18 exist to
prevent. "Bounded pass" displays its bound. Never show a stale pass against
edited source — invalidate immediately on document change.

Formal verification takes seconds, not milliseconds. Run on explicit request and
on save, not on keystroke. The synthesis preview updates live; the proof does
not, and the UI must never let those two be confused.

Failing properties show their counterexample trace, selectable into the FSM
graph via §15.2.

### 16.1 Responsiveness budget

| Action | Target | Mechanism |
|---|---|---|
| Keystroke → parse + diagnostics | < 50 ms | Client-side, incremental |
| Keystroke → truth table outputs | < 50 ms | Client-side evaluation |
| Edit → synthesis preview | < 1 s | 300 ms debounce, cancellable child process |
| Synthesis → schematic render | < 300 ms | elkjs in a web worker |
| Save → full verification | < 10 s | Background, non-blocking, cancellable |
| Analysis (SCOAP + stuck-at) | < 5 s | Background, after synthesis |

Cancel in-flight work on new input. A stale result arriving after a newer edit is
a correctness bug in the UI, not a performance issue.

---

## 17. Repository layout

```
gatepack/
  pyproject.toml
  LICENSE                     GPL-3.0
  Dockerfile                  pinned yosys, abc, sby, espresso, iverilog
  gatepack/                   core — pure Python, no GUI dependency
    frontend/ liberty/ emit/ report/
    synth/
      base.py                 SynthesisBackend interface
      synchronous.py
      asynchronous.py
    verify/
      base.py                 VerificationStrategy interface
      synchronous.py
      asynchronous.py
      properties.py
      mutation.py
    pack/
    analysis/                 scoap.py, faults.py, power.py, clock.py
    provenance/               capture.py, match.py    # §15.1 — first-class
    macros/                   M-cell models + physical bindings
                              cells_sim.v  ← shared with C4 (§C4.3)
    infra/                    S-cell definitions + parameter checks
    yosys/                    common_frontend.ys      # shared by C3 and golden_prep
    cli.py
  app/                        Electron application
    main/ preload/ renderer/ resources/bin/
  libraries/
    74aup.csv
    74aup.refs.md             datasheet citations
  examples/                   ALL SYNTHETIC — see §1.3
    golden/
    sync_interlock/
    async_handshake/
  tests/
    unit/ golden/ mutation/ e2e/
  docs/
```

CLI:

```
gatepack estimate design.yaml        # §6 viability verdict
gatepack project bundle  ./ -o x.gpk # §10.4 exploded -> single-file
gatepack project explode x.gpk -o ./ # §10.4 single-file -> exploded
gatepack build    design.yaml --library 74aup.csv --out out/
gatepack verify   out/
gatepack analyse  out/               # SCOAP + stuck-at, standalone
gatepack lib check 74aup.csv
gatepack gui
```

---

## 18. Golden reference designs

| Design | Purpose |
|---|---|
| 2-input XOR | Minimal smoke test |
| 4-bit binary counter (gates) | Sequential mapping, `dfflibmap` correctness |
| 4-bit counter (M-cell) | M-cell instantiation and model equivalence |
| 3-to-8 decoder | Fan-out and area cost behaviour |
| 4-bit ripple-carry adder | Depth and structural sharing |
| Traffic-light FSM | End-to-end, one-hot encoding |
| Linear sequencer | Johnson-counter suggestion fires |
| FSM with reset + enable | F-cell variant coverage; catches missing DFF_R/DFFE |
| **Async C-element** | Async backend; hazard-free cover retained |
| **Async handshake** | Essential hazard detected and reported |
| **Hazard-injected async** | ABC-optimised cover **must fail** hazard analysis |
| Property-violating FSM | Property check **must fail** |
| Latch-inferring design | Build **must fail** (§9.2) |
| **Degenerate library** | Broken `.lib`; build **must fail** |
| **Encoding-stability check** | One-hot encoding survives synthesis unchanged (**[R4-5]**) |
| **Timing-arc A/B** | Same design mapped with and without Liberty arcs; records whether ABC's result differs (**[R4-11]**) |
| **VCC-incompatible part** | 74HC M-cell at `vcc: 1.8`; build **must fail** (**[R4-8]**) |
| **Single-source-only supervisor** | No `equivalents`; build **must fail** without override (**[R4-9]**) |
| **Async design** | Refused with a clear verdict in v0.1.0, not silently synthesised (§7.3) |
| **Provenance coverage** | Reports % of mapped cells traceable to source; a floor, not a pass/fail (**[R4-14]**) |

The must-fail entries matter as much as the rest. A malformed Liberty file that
parses cleanly yields an implausibly low gate count, which reads as success.

---

## 19. Risk register

| # | Risk | Sev | Control |
|---|---|---|---|
| R1 | Malformed Liberty → degenerate mapping, implausibly good result | High | Golden designs; C2 self-check; degenerate-library test |
| R2 | Equivalence check passes vacuously | High | Mutation suite in CI |
| R3 | Design exceeds discrete viability, tool emits BOM anyway | High | §6 verdict; Red blocks build without `--force` |
| R4 | Clock skew across distributed flops breaks timing | High | §9.6 report; flop cap; independent viability metric |
| R5 | Missing F-cell variants inflate gate count → spurious Red verdict | High | §9.2 variant coverage; golden test with reset + enable |
| R15 | **Async constrained mapper produces hazardous netlist** | **High** | Hazard analysis in C4; hazard-injected golden test; §7.1 |
| R16 | Async constraints leak into synchronous backend | High | Strategy interface from M4; separate golden suites |
| R6 | Packing degrades layout (adjacency ignored) | Med | Advisory output; both netlists; override mechanism |
| R7 | ABC result varies across versions → non-reproducible | Med | Pinned container; output hash in CI |
| R8 | Datasheet transcription errors in `parts.csv` | Med | `parts.refs.md` citations; two-person review |
| R9 | M-/S-cell power dominates a sub-µA design unnoticed | Med | C7 static current broken out by tier |
| R10 | Provenance map lossy → misleading UI links | Med | Render partial provenance explicitly; never imply false 1:1 |
| R11 | GUI shows stale pass against edited source | Med | C15 invalidates on change; tri-state status |
| R12 | Electron security surface | Med | §5.2 posture; no network; hash-pinned binaries |
| R17 | Stuck-at analysis mistaken for a safety case | Med | Explicit exclusions in §13.2 and in the report itself |
| R18 | Properties pass vacuously (unsatisfiable antecedent) | Med | Cover statements alongside assertions; mutation coverage |
| R13 | Scope creep into placement, timing, schematic generation, FMEDA | Med | §1.2 non-goals are binding |
| R14 | Single-source part enters BOM via override | Low | Flag surfaces in report; fails CI by default |
| R19 | **`src` attributes lost at `dfflibmap`/`abc`; provenance map has no spine** | **High** | Pre-ABC capture + structural forward-matching; M0 spike before M16 (§15.1) |
| R20 | **Equivalence never closes: golden and mapped sides not in a common form** | **High** | Shared `golden_prep` front end; no `fsm` re-encoding; `setundef` before the split (§C4) |
| R21 | Async netlist emitted despite unsolved hazard-preserving factoring | High | v0.1.0 refuses async synthesis outright (§7.3) |
| R22 | BOM specifies a part that cannot operate at project VCC | Med | `vcc_min`/`vcc_max` columns; C1 mechanical check; golden must-fail (§9.4) |
| R23 | Second-source rule satisfied by fabricated `mfrs` data | Med | `equivalents` column; per-PN citation enforced by `lib check` (§10.1) |
| R24 | Refdes churn on unrelated edits makes layout unmaintainable | Med | Stable cell naming → deterministic packing → sorted assignment; refdes delta reported (§C6) |
| R25 | Mutation testing compares an M-cell model against itself | Med | One shared model file for `cells_sim.v` and equivalence (§C4.3) |

---

## 20. Milestones

**Core — must complete before any GUI work.**

**[R4-22] Revised throughout.** Draft 3's estimates assumed the toolchain
behaved as described in §12; several corrections above add work, and two
milestones were resequenced because they had dependencies that made their exit
criteria unreachable. Draft 3 totals are kept in a column so the delta is
visible rather than quietly absorbed.

| ID | Deliverable | Exit criterion | D3 | Est. |
|---|---|---|---|---|
| **M0** | **Toolchain + provenance spike** | Pinned container; `src` survival measured through `dfflibmap`/`abc`; structural matching prototyped on 2 goldens; timing-arc A/B recorded | — | **3 d** |
| M1 | C2 Liberty generator + `cells_sim.v` | `dfflibmap` maps DFF/DFF_R/DFF_S/DFF_SR from hand-written Liberty; degenerate library fails; sim models simulate | 3 d | **7 d** |
| M2 | C1 front-end (sync) | `design.yaml` → reviewable Verilog with `src` attributes; SAT guard-overlap check | 4 d | 5 d |
| M3 | C3 SynchronousBackend + `gatepack estimate` | Mapped netlist; no `$_`, latch or `$mem` cells; encoding-stability golden passes; **`estimate` delivered here, not at M1** | 2 d | **4 d** |
| M4 | **Backend strategy interfaces** | Sync path runs through the interface; async stub refuses cleanly | 2 d | 2 d |
| M5 | C4 sync verification | `golden_prep` shared front end; equivalence closes on all goldens; exhaustive sim under Icarus; **mutation suite passing** | 5 d | **10 d** |
| M6 | Properties (§11) | sby discharges invariants, reachability, liveness; cover statements guard vacuity | 3 d | 4 d |
| ~~M7~~ | ~~AsynchronousBackend~~ | **Deferred to v0.2** (§7.3). v0.1.0 detects and refuses. | 8 d | **0 d** |
| M8 | M-cell and S-cell libraries | CNT4 + SUPERVISOR + tie-off only (§23.2); shared behavioural models | 4 d | 4 d |
| M9 | C5 packer | `pack_cost` reported; spare avoidance; deterministic; override works | 4 d | **9 d** |
| M10 | C6 emitters + C7 analysis + C8 report | KiCad import clean incl. power symbols and no-connects; SCOAP delta; stuck-at classification; refdes delta | 6 d | **8 d** |
| M11a | CI, reproducibility, licence audit | Two clean builds hash-identical | — | 2 d |
| M11b | **Provenance map** | Coverage measured and reported on every golden; partial links explicit | — | **6 d** |

Core total: **64 d** against Draft 3's 45 d — but Draft 3's 45 d excluded async
being genuinely intractable (§7.3), so the honest comparison is 64 d against
53 d for a *smaller* and considerably more likely-to-work scope.

**Application.**

| ID | Deliverable | Exit criterion | Est. |
|---|---|---|---|
| M12 | Electron shell + C9 | Project opens; core invoked; §5.2 posture verified | 4 d |
| M13 | C10 spec editor | Three-way sync; positions in sidecar only | 5 d |
| M14 | C11 truth table grid | Live spec + simulated outputs; divergence highlighting | 4 d |
| M15 | C12 schematic view | netlistsvg rendering all layers | 3 d |
| M16 | **Linked selection (§15)** | All cross-highlights in the §15.2 table work | 5 d |
| M17 | C13–C15 | Packing override, dashboard, verification tri-state | 6 d |
| M18 | Packaging, docs, v0.1.0 | Signed installers; worked example; CI green | 5 d |

Sequencing notes:

- **[R4-22] `gatepack estimate` moved from M1 to M3.** Draft 3 made it the M1
  exit criterion and §22 the immediate next action — but §6 defines `estimate`
  as running the front-end *and* synthesis, so it silently depended on C1 and C3.
  M1 could not have delivered it. M1 is now honestly scoped as "Liberty
  generator, sim models, and a hand-driven synthesis smoke test."
- **[R4-14] M0 precedes everything.** The provenance question determines whether
  §15's linked selection — the stated justification for building a GUI at all —
  is achievable. Three days to find out is cheap; discovering it at M16 is not.
- **M4 still exists despite M7's deferral.** The strategy boundary is what lets
  async be refused cleanly rather than mis-synthesised, and it keeps async
  constraints out of the sync path (R16).
- **M5 precedes M9.** Verification must exist before the optimisation that most
  needs verifying. Building the packer first is the failure mode to avoid.
- **M11b precedes M16.** Linked selection is impossible without provenance.
- **M1–M11 complete and green before M12 starts.** A GUI over an unverified core
  is worse than no GUI.
- **GUI milestones carry +30%** (M12–M18: 32 d → 42 d), with M16 the most
  exposed since it consumes M11b's output.

Estimates assume LLM-assisted implementation. M9 is where generated code needs
the most iteration; M1, M5 and M11b are where it fails *silently* and needs the
most scrutiny.

---

## 21. Resolved questions

**[R4-23]** Draft 3's seven open questions are answered. Each was reviewed;
where the answer changes the design, the change is already made above.

**21.1 Target VCC — 3.3 V default, per-project setting.** `constraints.vcc`,
defaulting to 3.3 V for v0.1.0. 1.8 V immediately eliminates every 74HC M-cell
(2 V minimum) and narrows the 125 °C dual-source pool sharply, while 74AUP stays
sub-µA at 3.3 V — so the power story survives the choice and the part-selection
story does not survive the alternative. The authoritative tPD column is selected
per (`family` × VCC) at Liberty-generation time (§C2), never globally. Note this
changes the §10.2 example, which showed `vcc: 1.8`.

**21.2 74AUP only for v0.1.0 — but the schema anticipates 74LVC now.** Shipping
two families doubles the datasheet-validation and timing-model surface for
marginal benefit. The `family` column exists from day one (§10.1) so adding
74LVC later is a data change, not a code change. Ship AUP, design for LVC.

**21.3 Expect heavy pruning of §9.4/§9.5 — and fix the data model first.** At
125 °C with genuine dual sourcing, most of the M- and S-cell candidates will
drop. The Draft 3 `TPS3839 / "TI;Diodes"` line was already wrong (§10.1), which
is evidence the rule was unenforceable rather than merely unenforced. `parts.csv`
gains `equivalents` before any of this table is trusted. v0.1.0 keeps CNT4
(genuinely multi-sourced) and SUPERVISOR; the rest waits.

**21.4 Refuse to downgrade — no random-vector fallback.** Exhaustive simulation
runs up to a runtime cap rather than a fixed n = 20; roughly 2²⁴ vectors is
tractable under Icarus for combinational logic. Above the cap the tool reports
exhaustive sim as not applicable and rests on formal equivalence, which is the
actual proof at any width. A coverage figure on random stimulus is a confidence
trick and never contributes to a green status (§C4.3).

**21.5 BMC is acceptable as a labelled fallback, never as "passed".** k-induction
is primary, default k = max(2 × state count, 64), overridable. Where BMC is used,
C15 shows a **fourth state — "bounded pass"** — and the report prints the bound.
Folding a bounded result into a green check would recreate exactly the vacuous
pass R2 and R18 exist to prevent.

**21.6 Linux and Windows for v0.1.0; macOS deferred.** AppImage or .deb, plus an
unsigned NSIS installer or zip. macOS notarisation costs money and time and has
no bearing on whether the tool is correct; a personal FOSS project should not
block a release on a signing certificate. Unsigned binaries are documented as
such. Signing is added when there are users who need it.

**21.7 Async primitives must be instantiated — they do not fall out.** A Muller
C-element is a state-holding majority gate with no two-level Boolean equivalent,
so no Espresso cover and no ABC mapping will ever produce one, and a handshake
built without one will simply be wrong. It is instantiation-only with a
hand-reviewed behavioural model — the M-cell contract — so it folds into that
tier rather than becoming a fifth (§8).

### 21.1 Still open

1. What provenance coverage does structural forward-matching actually achieve on
   the golden designs? M0 answers this empirically; §15.1's fallback plan
   depends on the number.
2. Does Liberty timing data change ABC's mapping on the pinned Yosys version?
   M1's timing-arc A/B golden answers it (§C2).

---

## 22. Immediate next action

**[R4-22] Build M0, not M1.** Draft 3's next action was M1 delivering
`gatepack estimate`, which it could not have done (§20 sequencing notes).

M0 is a three-day spike answering the two questions that determine whether the
architecture holds:

1. **Does provenance survive?** Run a golden through the full C3 script and
   measure how many mapped cells still carry usable `src` attributes. Prototype
   structural forward-matching from `premap.json` and record its coverage. This
   determines whether §15 linked selection — the entire GUI justification — is
   achievable as specified (R19).
2. **Does the toolchain behave as §12 claims?** Pin the container. Confirm
   `dfflibmap` maps a hand-written `DFF_R` from Liberty. Confirm `equiv_make`
   closes with the shared `golden_prep` front end. Record the timing-arc A/B
   result (§C2).

Both are cheap now and expensive later: the first would surface at M16, the
second at M5, and in each case after code has been written on the assumption it
was fine.

Then M1 — C2 plus `cells_sim.v`, validated against the golden designs — and
`gatepack estimate` at M3 where it belongs.

---

## 23. v0.1.0 scope

**[R4-24]** Draft 3 had no explicit cut list, which is how a design of this size
ships nothing. The line is drawn at *a correct, verified synchronous tool*.

### 23.1 In

Synchronous front-end, synthesis, verification (equivalence + properties +
exhaustive sim + mutation), packing, emitters, analysis, report, provenance,
CLI, and the desktop app as a read-mostly view.

### 23.2 Cut or deferred

| Item | Disposition | Why |
|---|---|---|
| Async synthesis (M7) | **v0.2** | Three unsolved sub-problems (§7.3); refuse cleanly instead |
| §9.4 beyond CNT4 | v0.2 | Each M-cell is a hand-reviewed model; 4017/4040 are HC and VCC-incompatible at 3.3 V anyway |
| `CLKBUF`, `OSC`, `DELAY` S-cells | v0.2 | `DELAY` is async-only; the others wait for a golden that needs them |
| Random-vector simulation | **cut** | Proves nothing; formal equivalence is the guarantee (§21.4) |
| Configurable-gate merge pass | v0.2 | Area biasing ships instead (§9.1) |
| Liberty `DFFE` mapping | opt-in | Mux-feedback default; too version-fragile to depend on (§9.2) |
| C13 drag-to-regroup | v0.2 | Read-only BOM/package table first; override via `design.yaml` |
| macOS installer | v0.2 | Signing cost, no correctness bearing (§21.6) |

### 23.3 v0.2 candidates

Async synthesis as a research task; the full M/S-cell inventory; 74LVC family;
interactive packing; macOS distribution.

From §24: package pinout rendering on the C13 packing cards (blocked on pinout
*data*, not on the renderer); Verilog handoff to Digital for interactive
simulation; an optional LTspice deck export.

### 23.4 Review findings not adopted

- **"`abc -liberty` is purely area-driven, so timing arcs cannot affect
  mapping."** Overstated — Yosys's default ABC script uses delay-driven `map`
  with area recovery. The useful half is adopted (arcs are primarily for
  reporting; delay-*constrained* mapping needs `abc -constr`, not planned) and
  the claim is resolved by measurement at M1 rather than asserted either way
  (§C2).
- **"Drop C14 first."** The analysis dashboard is where the §6 verdict lives and
  is among the cheapest panels to build; C13's interactivity is the better cut,
  and is cut (§23.2).

---

## 24. Prior art and interoperation

Added Draft 4.1 after a survey of the simple-logic-simulator field
(`docs/reviews/2026-08-15-deepseek-simulator-survey.md`), prompted by the
Hackaday survey of June 2021. The field is dominated by schematic-capture
educational simulators — close to the inverse of gatepack's premise — so this
section records what was taken, what was declined, and why, so the questions are
not reopened from scratch later.

### 24.1 Digital (Helmut Neemann)

`github.com/hneemann/Digital` — GPL-3.0, Java/Maven, actively maintained. The
closest neighbour in the field: a schematic simulator built around **real 74xx
packages** rather than abstract gates.

Verified facts, not inferences:

- **131 74xx component definitions** under `src/main/dig/lib/DIL Chips/74xx/`,
  as XML `.dig` files carrying description, DIL shape, pin positions and
  internal logic.
- **They contain no electrical data** — no tPD, no IQ, no supply range, no
  manufacturer, no second source.
- **Verilog and VHDL both ways.** Components can be *defined* in Verilog
  (simulated via Icarus) and circuits *exported* to Verilog or VHDL.
- **JEDEC export** for GAL16V8, GAL22V10 and ATF150x.

Consequences for gatepack:

- **The 74xx library is a cross-check corpus, never a source of record.** §10.1
  [R4-21] requires a datasheet citation with document revision and table/page
  for every electrical value, and Digital carries none — its delays are
  simplified simulation values. It is useful for confirming pinouts and catching
  transcription slips in `parts.csv`, and for nothing else. It does **not**
  reduce the datasheet-transcription burden of R8.
- **A two-way Verilog handoff exists and costs nothing.** Digital consumes
  Verilog-defined components using the same Icarus gatepack already depends on
  for C4, so `build/generated.v` can be dropped into Digital and simulated
  interactively. This is a strictly better interchange route than exporting an
  undocumented `.circ`, and requires no new dependency. v0.2, low cost.
- **The CPLD escape hatch in §6 is real, and worth asserting.** Digital
  demonstrates that compiling this class of logic into a constrained device is
  routine. gatepack's Red verdict already recommends a flash CPLD; the
  constraints that make RTL fit such a device — no `$mem`, no latches, no async,
  no surviving `$_` cells — are the ones C3 **already enforces** ([R4-13], §9.2).
  Make that explicit: state in the report which alternative consumes
  `generated.v`, and add a golden that fails if a CPLD-hostile construct appears.
  Fold into M3; low cost.
- **Single-gate stepping and oscillation analysis** is the one capability in the
  field that gatepack cannot express. Formal equivalence compares steady-state
  functions and says nothing about transient behaviour — precisely the §7.1
  problem where an async netlist is equivalent yet glitches. Relevant to v0.2
  async work as a debugging aid; not a substitute for hazard analysis.

### 24.2 Adopted from the wider field

- **Live minimised-cover preview** in C11 (§16, M14), from Logic Friday's
  interaction model — the missing *number* behind the §6.1 suggestions.
- **Per-vector signal-value overlay** in C12 (§16, M16), from Logisim-evolution
  and Digital — value rather than membership, over vectors C4 already computes.
- **Package pinout rendering** on the C13 cards. Deferred to v0.2 and blocked on
  *data*: `parts.csv` carries `package` but no pin map, and adding one increases
  the transcription burden R8 warns about. The renderer is the easy half.

### 24.3 Declined, with the principle each would breach

- **Interactive schematic capture** (Logisim-evolution, Digital, CEDAR, TKGate,
  Falstad) — breaches principle 2. Editable schematic state is exactly the
  lock-in gatepack exists to avoid. C12 renders; it never edits.
- **Analogue or live electrical simulation** (LTspice, Falstad, Proteus,
  Multisim) — breaches §1.2. An optional SPICE *deck export*, for the engineer to
  run against their own vendor models, stays on the right side of the line;
  bundling models or running SPICE does not. Vendor 74xx SPICE models are
  frequently "use but do not redistribute", so they must never be shipped.
- **Interactive simulation as the deliverable** — gatepack is a verifier, not a
  sandbox. Its guarantee is equivalence plus exhaustive simulation plus mutation,
  not a poke-able waveform.
- **K-map / Quine–McCluskey visual editors** — the truth-table grid with
  don't-cares is strictly more general (K-maps cap out around six variables) and
  Espresso already minimises. Adopt the preview affordance, not the UI.
- **Importing RTL or capture files as source** (`.circ`, EDIF, BLIF, Verilog) —
  breaches principle 2 and §1.1. gatepack compiles *specifications*; accepting
  netlists would make it a Yosys front-end with none of the validation, verdict
  or provenance that justify it.
- **Building on Amaranth/nmigen** rather than emitting Verilog text. Not a
  licence objection (BSD-2-Clause): an EDSL inserts a version-drifting
  elaboration step into the byte-identical path (principle 5, §5.5), and blurs
  the precise control over provenance attributes and construct choice that §15.1
  and [R4-13] require. It would still emit Verilog at the end.

### 24.4 Where gatepack actually differs

Judged against this field, and worth stating because it is easy to lose sight of
while building: no surveyed tool performs formal equivalence with a
non-vacuous guarantee (§C4, R2), produces text-canonical reproducible builds, or
emits a viability verdict (§6). None does BOM generation, package packing,
mechanical second-sourcing, or spare-gate leakage accounting (§9.7, §10.1). None
reports electrical consequence from cited datasheets, and none does stuck-at
classification or SCOAP testability (§13). None maps an artefact back to a
specification line (§15), because none of them has a specification to map to.

The field simulates ideal logic. gatepack compiles a specification into a
buildable, verified bill of materials.
