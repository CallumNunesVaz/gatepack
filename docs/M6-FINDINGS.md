# M6 findings — measured against real SymbiYosys

Measured on 2026-08-15 in `gatepack-toolchain:m6` (Debian bookworm, Yosys 0.23
from the archive, sby pinned to `beb8b3c6e38ee716cd9771eb906c37684e83eab4`,
z3 from the archive). Everything below was run, not reasoned about.

**Where this document and `gatepack-design.md` §11 disagree, this document
wins.** Same standing as `docs/M0-FINDINGS.md`.

## 1. `assert property (@(posedge clk) ...)` does not parse

The design's §11 and the existing front-end test
(`test_properties_file_emits_assertions`) call for SVA concurrent assertions
with `disable iff`. Measured on Yosys 0.23:

```
cnt.sv:8: ERROR: syntax error, unexpected '@'
```

Open-source Yosys does not implement SVA concurrent assertions; that path
requires the Verific front end, which is commercial. The read-only subset that
works is the **immediate assertion inside a clocked always block**:

```systemverilog
always @(posedge clk) if (f_past_valid && rst_n) begin
  a_range: assert (c <= 3'd5);
  c_reach: cover  (c == 3'd5);
end
```

`disable iff (!rst_n)` becomes the `rst_n &&` guard on the enclosing `if`.
This is a change to C1's property emission, not just to the verification
driver, and it invalidates the assertions in the current
`test_properties_file_emits_assertions`.

## 2. Properties need an explicit reset assumption or they fail spuriously

This is the finding most likely to be misdiagnosed as a broken design.

A formal engine starts from a **completely unconstrained** state. A register
with no initial value can start at any value, including states the circuit can
never physically reach after reset. A true invariant therefore fails at step 1:

```
BMC failed!
Assert failed in cnt: a_range        # c <= 5, with c starting at 6 or 7
```

Induction passed while the base case failed — the signature of exactly this
problem, and worth recognising in the parser.

The fix is to give the proof the reset that real hardware would get:

```systemverilog
reg f_past_valid = 1'b0;
always @(posedge clk) f_past_valid <= 1'b1;
always @(posedge clk) if (!f_past_valid) assume (!rst_n);
```

With this added, the same property returns `PASS` for both basecase and
induction. **C1 must emit this wrapper into the properties file.** Without it
M6 reports failures against correct designs, which is worse than reporting
nothing.

## 3. Measured status recipes for all four `CheckStatus` values

| Result | How it is produced | sby output |
|---|---|---|
| `passed` | `mode prove`, both phases pass | `returned pass for induction` **and** `returned pass for basecase`, `DONE (PASS, rc=0)` |
| `bounded` | `mode bmc`, depth k | `Status: passed`, `DONE (PASS, rc=0)` — bound is the configured `depth` |
| `failed` | assertion violated | `Assert failed in <mod>: <label>`, `DONE (FAIL, rc=2)`, VCD at `<task>/engine_0/trace.vcd` |
| `not_run` | `sby` absent from PATH | no invocation; report with `skippedReason` |

A deliberately false assertion (`c != 3'd4` on a counter that reaches 4) was
caught with a counterexample trace, so the check demonstrably *can* fail —
the anti-vacuity requirement of R2/R18 is satisfied by construction here.

### 3.1 The parsing trap

**`mode prove` and `mode bmc` both emit the literal string `returned pass`.**
A parser that keys on the summary line alone cannot tell a complete proof from
a bounded one, and would render a depth-12 BMC result as a full pass — which is
precisely the vacuous-green-tick failure mode §C15 [R4-25] introduced the fourth
state to prevent.

The distinguishing information is **the mode the driver chose**, which the
driver knows because it wrote the `.sby` file. Carry it forward explicitly:

- `mode prove` → `passed` only if **both** `basecase` and `induction` returned
  pass. Induction pass with basecase fail is *not* a bounded pass — see §2, it
  usually means the reset assumption is missing.
- `mode bmc` → always `bounded`, with `bound` = the configured depth.

Never infer the status from `DONE (PASS)` alone.

## 4. Cover statements report their step

`mode cover` reports `Reached cover statement at c_reach in step 7`, so the
anti-vacuity check yields not just reachability but the depth at which the
antecedent first becomes reachable. Worth surfacing: a cover reached only at a
large step is a hint that the property is nearly vacuous.

An unreached cover is the vacuity failure and must be reported as a failed
check, never as a passing property.

## 5. Version skew is real and had to be pinned by measurement

The current SBY release (v0.68) **does not work with Yosys 0.23**. It emits

```
formalff -setundef -clk2ff -ff2anyinit -hierarchy
ERROR: Command syntax error: Unknown option or option in arguments.
```

because `formalff -hierarchy` postdates Yosys 0.23. The oldest tagged sby
release is `yosys-0.26`, so **no tagged sby matches the pinned Yosys**, and the
pin has to be a bare commit contemporaneous with it:
`beb8b3c6e38ee716cd9771eb906c37684e83eab4` (2022-12-19), which is measured to
work.

This is an argument for revisiting the Yosys pin at some point — Debian
bookworm's 0.23 is what M0 measured against, and every finding in
`M0-FINDINGS.md` is tied to it, so the version cannot be moved casually. But it
does mean the toolchain is pinned to a combination that upstream no longer
tests together.

`yosys-smtbmc` and `yosys-witness` already ship with the Debian `yosys`
package, so sby is the only missing piece.

## 6. Hierarchical references silently become free wires — properties checked nothing

The worst finding here, and it was invisible until the properties were run
against a real prover.

C1 emitted its property bodies against `dut.<signal>` — a hierarchical
reference into the instantiated design. Yosys 0.23 does not resolve these:

```
h.sv:9: Warning: Identifier `\dut.red' is implicitly declared.
Warning: Wire h.\dut.red is used but has no driver.
```

It **creates a new, undriven wire of that name** and carries on with a warning.
The assertion is then evaluated over free variables that have no connection to
the design at all. The prover dutifully finds an assignment that violates the
property and reports a failure — or, for a different property, a pass — and in
neither case has it said anything whatsoever about the circuit.

This was diagnosed by isolation, and the isolation is worth repeating because
the symptom pointed the wrong way. The traffic-light mutex property failed with
a trace showing all three lights high while reset was asserted, which looks
exactly like a broken reset. It was not: a probe asserting on the *local* wires
of the same harness passed, and the identical probe rewritten to use `dut.red`
produced the warnings above. The design was never at fault.

**Consequence:** the fix is not a syntax change. Assertions must be emitted
where the signals they reference actually exist — inside the design module,
under an `` `ifdef GP_FORMAL `` guard — with the harness reduced to what can
legitimately live at the port boundary: the reset assumption and the
instantiation. `bind` would be the idiomatic alternative and is not available
in Yosys 0.23.

**And a check that must exist:** any run whose log contains
`is used but has no driver` or `implicitly declared` for a signal named in a
property must be treated as a hard failure, never a result. A property over an
undriven wire is the purest form of the vacuous pass this project is built to
prevent — worse than no property, because it reports a status.
