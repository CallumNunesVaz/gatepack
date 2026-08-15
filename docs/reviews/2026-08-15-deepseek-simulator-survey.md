## Verdict

Nothing here overturns gatepack's premise; the survey is dominated by schematic-capture educational simulators, which is the opposite of gatepack's text-canonical, verify-on-build model. The two genuine takeaways are both incremental: **Digital** (Helmut Neemann) is the closest domain neighbour and its real contribution is as a *cross-check corpus* and a proof that a constrained-device (GAL/CPLD) fallback is real, not as a codebase; **Logic Friday** suggests one UI affordance — a live minimised-cover preview — that sharpens an existing §6.1 feature. Everything else worth doing is *interoperation* (a SPICE handoff, a CPLD-safety statement), not adoption. The field as a whole confirms rather than threatens gatepack's differentiation: nobody else does formal equivalence + mutation, reproducible text-canonical builds, or BOM/packing.

## Worth adopting

1. **Live minimised-cover and gate-count preview in the truth-table grid.**
   *Tool:* Logic Friday (Espresso front-end — truth-table entry → minimise → cover + gate count, instantly).
   *Why it fits:* gatepack already runs Espresso and already plans §6.1 input-space collapse as "suggested, never applied". The missing piece is the *number* that makes the suggestion actionable: Logic Friday's whole interaction is "edit the table, watch the cover shrink". Showing a debounced Espresso cover + estimated package count next to the existing computed/simulated columns turns don't-care and collapse edits from abstract advice into a visible cost delta. This is principle 8 (report the consequence, let the engineer decide), not a silent optimisation.
   *Where:* C11, **M14**, plus the §6.1 suggestions can cite the measured delta.
   *Cost:* Low. Reuse the C3 Espresso wrapper behind a debounced sub-second core call (fits the §16.1 `<1 s` synthesis-preview budget); no new machinery.

2. **Per-vector signal-value overlay in the schematic.**
   *Tool:* Logisim-evolution / Digital (poke a wire, see live 0/1 propagation).
   *Why it fits:* §15.2 already maps "truth-table row → gates active for that minterm". Logisim-evolution shows that *membership* is weaker than *value*: for a selected minterm or counterexample trace, colour each net by its simulated 0/1. C4 already computes exhaustive vectors, so this is a rendering increment, not new analysis. It makes C12 a *debugger* rather than a picture, and it is exactly the linked-selection behaviour that "makes the application worth building".
   *Where:* C12, **M16** (M15 renders structure; this adds value rendering on top).
   *Cost:* Low. Render the already-computed vector onto netlistsvg nets; no new toolchain.

3. **Package pinout rendering on the packing cards.**
   *Tool:* Digital (its whole model is real 74xx packages with pin numbers).
   *Why it fits:* C13 is singled out as "the view most likely to justify the GUI" because packing review is an adjacency/pinout judgement. Digital's package view — gate function mapped to actual physical pins within a package, power pins shown — is the concrete thing that makes a packing override *judgeable*. gatepack currently carries `package` but **not pin maps**, so this is a data addition before it is a feature.
   *Where:* C13, **M17**; requires a `pinout` column (or per-part pin-map file) in the §10.1 schema.
   *Cost:* Medium — schema change + a pinout renderer, and every row needs pinout data (adds to the M8/M11 datasheet-transcription burden). Deferrable to v0.2 without damage.

4. **CPLD-portability of `generated.v` as an explicit, asserted property.**
   *Tool:* Digital (the only surveyed tool that compiles logic into a real constrained device, a GAL).
   *Why it fits:* §6's escape hatch ("use a flash CPLD such as MAX V with portable inferred Verilog") is currently a suggestion. Digital proves the GAL/CPLD fallback target is real, and its hard constraint is what makes gatepack's own assertions load-bearing: CPLD-safe RTL is exactly the "no `$mem`, no latch, no async, no `$_` cells" set gatepack already enforces (§C3 R4-13, §9.2). The adoption is a *stated* line: a lint that asserts CPLD-safety and a report sentence naming which alternative consumes the Verilog.
   *Where:* C3/C8, fold into **M3**.
   *Cost:* Low — the assertions mostly exist; this adds a report line and a golden that fails if a CPLD-hostile construct appears.

## Worth interoperating with, not rebuilding

- **Digital's 74xx library as a cross-check corpus.** gatepack is GPL-3.0-or-later and Digital is GPL (compatible), so the data *could* be consumed. But gatepack's mechanical datasheet-citation rule (§10.1, R4-21) means Digital's library can only be a *candidate list* and a *discrepancy check* against `parts.csv` — never a source of record. Use it to sanity-check the §9.4/§9.5 inventory and catch transcription slips; cite datasheets anyway.
- **LTspice as a handoff, not a feature.** An optional export of a SPICE deck for the engineer to sanity-check crowbar current (§9.7), skew (§9.6) or static current with *their own* vendor 74xx models stays on the "report the consequence" side of §1.2. gatepack must not bundle models or run SPICE (analogue non-goal; LTspice is closed freeware). Low value for v0.1.0; worth listing as a v0.2 candidate only if users actually ask for it.
- **CPLD/GAL fitter handoff.** Digital compiles to JEDEC for ATF150x; gatepack should *not* rebuild a fitter (§1.2, §3.1) — it should keep `generated.v` portable so a vendor tool (Quartus for MAX V, or a GAL flow) consumes it directly. Digital validates that this target exists; it does not itself consume Verilog, so there is no direct two-way path.
- **Logisim-evolution `.circ` export (tentative).** Exporting a `.circ` so a user can *simulate* the result in a familiar tool is a nice-to-have, but the format is undocumented and version-unstable (uncertain), and gatepack already exhaustively simulates and renders. Only worth it as an explicit "poke it yourself" convenience, gated on the format being stable.

## Explicitly reject

- **Interactive schematic capture / circuit editing** (Logisim-evolution, CEDAR, TKGate, Digital, Falstad). Violates principle 2 ("text is canonical; the GUI is a view") — editable schematic state is precisely the lock-in gatepack exists to avoid. C12 stays a *rendering* of the netlist, never an editor.
- **Live analogue / electrical simulation** (Falstad, LTspice, iCircuit, Multisim, Proteus). Violates §1.2 "analogue anything". gatepack reports coarse electrical *estimates* from datasheet data; it does not simulate silicon.
- **Interactive simulation as the deliverable** (all of them). gatepack is a verifier, not a sandbox: its guarantee is formal equivalence + exhaustive simulation + mutation, not a poke-able waveform. Building a simulator is the wrong product.
- **K-map / Quine–McCluskey visual editors** (Logic Friday, Digital). gatepack's truth-table grid with `-` don't-cares is strictly more general (K-maps cap at ~6 variables); Espresso already does the minimisation. Adopt the *preview affordance*, reject the K-map UI.
- **Importing arbitrary RTL or capture files as source** (Logisim `.circ`, VHDL, EDIF, Verilog, BLIF-as-source). gatepack compiles *specifications* (`design.yaml`/`truth_table.csv`), not netlists. Accepting RTL makes it a Yosys front-end with none of the validation, verdict, or provenance value, and breaks text-canonical.
- **Building on Amaranth/nmigen instead of emitting Verilog text.** Rejected on three grounds independent of licence: (a) the AGENTS.md "no new runtime deps beyond pydantic" rule; (b) reproducibility (§5.5 / principle 5) — an EDSL's elaboration adds a version-drifting step to the byte-identical path, whereas direct text is deterministic; (c) provenance (§15.1) — gatepack needs precise control over `(* src = ... *)` attributes and construct choice (`case`/`$pmux` vs memory, §C3 R4-13) that an IR indirection would blur. Amaranth would also still emit Verilog, so it is an extra layer with zero benefit.

## What none of these tools do

- **Formal equivalence with a non-vacuous guarantee.** Every simulator here shows waveforms; none proves netlist ≡ spec, and none runs a mutation suite to prove the check itself is real (§C4, R2). This is the single largest gap in the field.
- **Text-canonical, reproducible, git-tracked builds.** Simulators are session-stateful and hand-drawn; gatepack's `design.yaml` → byte-identical netlist → BOM is a compiler, not a document.
- **A viability verdict.** No simulator says "this is 50 packages and you shouldn't build it discretely — use a CPLD". §6 is a product feature, not a simulation.
- **BOM / package packing / second-sourcing / spare-gate crowbar accounting.** Nothing here maps gates into physical multi-gate packages, enforces dual-sourcing mechanically, or prices in leakage and tie-off (§9.7, §10.1).
- **Electrical consequence reporting from cited datasheets** — static current by tier, clock-fanout skew, flop reset-recovery checks (§9.5). Simulators model ideal logic; none model the *board*.
- **Fault analysis and testability** — stuck-at classification against a declared safe state, SCOAP delta, independence statement (§13). Digital's measurement tools are signal-level, not test-coverage.
- **Provenance / linked selection** — source ↔ gate ↔ package ↔ BOM. No simulator maps a schematic element back to a spec line, because none has a spec.

## Licence and provenance notes

- **Digital (Helmut Neemann):** I believe GPL-3.0-or-later, but **confirm before any reuse**. Its 74xx library is *licence-compatible* with gatepack (GPL-3.0-or-later), so reuse is legally possible; practically it is a cross-check only, because gatepack's R4-21 rule requires datasheet citations that Digital's library does not carry, and its delays are simplified simulation values, not datasheet numbers.
- **Logic Friday:** closed-source freeware (Sontrak, wraps Espresso). Interaction model only; no code or data can be reused. Its Espresso wrapping is irrelevant — gatepack bundles Espresso directly (BSD-style, already in §4).
- **Logisim (Carl Burch):** GPL (GPL-2.0+, I believe — confirm). **Logisim-evolution:** GPL-3.0 (confirm). `.circ` is XML with no stable public spec (uncertain) — treat any export as best-effort.
- **CEDAR Logic Simulator:** freeware, closed — model only.
- **TKGate:** GPL (confirm exact version).
- **Falstad:** GPL-2.0 (uncertain — verify before any reference).
- **LTspice:** closed freeware. **Vendor 74xx SPICE models** are the real hazard: many are "use but do not redistribute", and licences vary per vendor — gatepack must never bundle them, only hand off to the user's own.
- **Amaranth/nmigen:** BSD-2-Clause (I'm confident) — licence is *not* the objection; the rejection is reproducibility/deps/provenance, per above.
- **Logicsim (1983):** the article's "open source (personal/research use)" is not a recognised licence — effectively non-redistributable; do not touch.
- **None of these projects** practices gatepack's datasheet-citation discipline, so any data drawn from them must be re-verified against primary datasheets — never trusted at face value.
