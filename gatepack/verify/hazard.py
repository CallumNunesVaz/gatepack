"""Stage 5 — independent hazard verification of a mapped netlist (§7.3).

This is the safety net that lets the rest of the asynchronous backend ship.  It
reads the **mapped netlist** — the actual output — and must **not** import from
:mod:`gatepack.synth.async_` (a test enforces that): a verifier that shares the
synthesiser's data structures verifies nothing.

Two independent checks:

**5a. Ternary (three-valued) simulation.**  For every specified single-input
transition, the changing input is set to ``X``, every other input (and any
declared state net) to its stable value, and ``X`` is propagated through the
mapped gates with standard 0/1/X truth tables to a fixed point.  Any output that
is stable across the transition (0->0 or 1->1) but evaluates to ``X`` has a
potential **static hazard** — refused, naming the output and the transition.
This is decidable, runs on the real netlist, and catches exactly the damage that
factoring or an unexpected mapping would do.

**5b. Icarus glitch simulation.**  The same transitions are driven through the
mapped netlist under a unit-delay behavioural model with per-seed delay
perturbation, and the testbench asserts that a stable output never changes value.
Empirical and complementary: 5a can be conservative, 5b can miss cases, and a
disagreement between them is a finding, not something to smooth over.

The hazard guarantee is **fundamental mode only**: one input changes at a time
and the circuit settles before the next change.  It does **not** extend to
concurrent input changes.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from gatepack.liberty import boolean
from gatepack.netlist import MappedNetlist

#: Three-valued logic: 0, 1, and 2 for X.
_ZERO = 0
_ONE = 1
_X = 2


@dataclass(frozen=True)
class TransitionProbe:
    """One specified single-input transition to check for static hazards.

    ``changing_input`` is set to ``X`` during the ternary check; ``stable_inputs``
    holds every *other* primary input at its stable value; ``fixed_nets`` holds
    any state (feedback) nets at their stable value; ``from_value`` is the value
    the changing input holds before the transition (its direction).
    """

    changing_input: str
    stable_inputs: Mapping[str, bool]
    fixed_nets: Mapping[str, int] = field(default_factory=dict)
    from_value: bool = False


@dataclass(frozen=True)
class HazardFinding:
    """A potential static hazard: a stable output that evaluates to X."""

    output: str
    changing_input: str
    stable_value: int  # 0 or 1
    transition: Mapping[str, int]

    @property
    def kind(self) -> str:
        return "static-1" if self.stable_value == 1 else "static-0"


class _Function:
    """A parsed cell function, evaluable in the binary and ternary domains."""

    def __init__(self, func: str) -> None:
        self.count = _count_vars(func)
        self.node = boolean.parse_function(func, self.count)
        self.pins = boolean.pin_names(self.count)

    def eval_ternary(self, args: Sequence[int]) -> int:
        xs = [i for i, v in enumerate(args) if v == _X]
        if not xs:
            return self._eval_binary(args)
        outcomes: set[int] = set()
        for mask in range(1 << len(xs)):
            completed = list(args)
            for j, pos in enumerate(xs):
                completed[pos] = (mask >> j) & 1
            outcomes.add(self._eval_binary(completed))
        return outcomes.pop() if len(outcomes) == 1 else _X

    def _eval_binary(self, args: Sequence[int]) -> int:
        env = {pin: bool(v) for pin, v in zip(self.pins, args)}
        return _ONE if boolean.eval_function(self.node, env) else _ZERO


def _count_vars(func: str) -> int:
    """Number of distinct input pins referenced by a boolean function string."""
    return len(set(re.findall(r"[A-Z]", func)))


def _compile_functions(cell_functions: Mapping[str, str]) -> dict[str, _Function]:
    return {cell: _Function(func) for cell, func in cell_functions.items()}


def evaluate_fixed_point(
    netlist: MappedNetlist,
    cell_functions: Mapping[str, str],
    input_values: Mapping[str, int],
    ternary: bool,
) -> dict[str, int]:
    """Propagate input values through the netlist to a fixed point.

    ``input_values`` maps primary input names (and any held state/fixed nets) to
    0/1 (and, when ``ternary``, to 2 for X).  Every key of ``input_values`` is
    *held*: a gate that drives such a net does not overwrite it.  This is what
    cuts the state-feedback loop for the fundamental-mode hazard check — the
    state is held at its settled value while the combinational logic settles
    around an input change.  Unknown nets stay X.
    """
    funcs = _compile_functions(cell_functions)
    values: dict[str, int] = dict(input_values)
    held = frozenset(input_values)
    for _ in range(len(netlist.cells) + 2):
        changed = False
        for cell in netlist.cells:
            fn = funcs.get(cell.cell)
            if fn is None:
                continue
            args = [_pin_value(cell, pin, values) for pin in cell.input_pins]
            out = fn.eval_ternary(args) if ternary else fn._eval_binary(args)
            out_net = cell.connections.get(cell.output_pins[0], "")
            if out_net in held:
                continue
            if values.get(out_net, _X) != out:
                values[out_net] = out
                changed = True
        if not changed:
            break
    return values


def _pin_value(cell, pin: str, values: Mapping[str, int]) -> int:
    net = cell.connections.get(pin)
    if net == "0":
        return _ZERO
    if net == "1":
        return _ONE
    if net in ("x", "z"):
        return _X
    return values.get(net, _X) if net is not None else _X


def check_static_hazards(
    netlist: MappedNetlist,
    cell_functions: Mapping[str, str],
    probes: Sequence[TransitionProbe],
    outputs: Sequence[str] | None = None,
) -> tuple[HazardFinding, ...]:
    """Return every stable output that evaluates to X across a specified transition.

    For each probe the binary value of every output (primary outputs by default,
    or the explicit ``outputs`` list — which the asynchronous verifier uses to
    also cover the state feedback nets) is computed with the changing input at 0
    and at 1; an output equal in both (0->0 or 1->1) that then evaluates to X
    under ternary simulation is a potential static hazard.
    """
    findings: list[HazardFinding] = []
    checked = list(outputs) if outputs is not None else list(netlist.outputs)
    for probe in probes:
        base = {name: (_ONE if v else _ZERO) for name, v in probe.stable_inputs.items()}
        base.update(probe.fixed_nets)
        v0 = evaluate_fixed_point(netlist, cell_functions, {**base, probe.changing_input: _ZERO}, False)
        v1 = evaluate_fixed_point(netlist, cell_functions, {**base, probe.changing_input: _ONE}, False)
        vx = evaluate_fixed_point(netlist, cell_functions, {**base, probe.changing_input: _X}, True)
        for output in checked:
            a = v0.get(output, _X)
            b = v1.get(output, _X)
            x = vx.get(output, _X)
            if a == b and a in (_ZERO, _ONE) and x == _X:
                findings.append(
                    HazardFinding(
                        output=output,
                        changing_input=probe.changing_input,
                        stable_value=a,
                        transition={**base, probe.changing_input: _X},
                    )
                )
    return tuple(findings)


# ---------------------------------------------------------------------------
# 5b — Icarus glitch simulation
# ---------------------------------------------------------------------------


def unit_delay_cells(
    cell_functions: Mapping[str, str],
    seed: int = 0,
    base_delay_ns: float = 1.0,
) -> str:
    """Emit unit-delay behavioural models (one ``assign #delay`` per cell).

    Delays are perturbed per cell type and per ``seed`` so several runs explore
    different delay relationships; a glitch that depends on a particular
    inter-gate delay is caught by at least one seed rather than assumed away.
    """
    rng = random.Random(seed)
    lines = [
        "// Unit-delay behavioural models for the glitch check (stage 5b).",
        "`timescale 1ns/1ps",
        "",
    ]
    for cell, func in sorted(cell_functions.items()):
        count = _count_vars(func)
        delay = base_delay_ns + rng.uniform(0.0, base_delay_ns)
        node = boolean.parse_function(func, count)
        pins = boolean.pin_names(count)
        ports = [f"input wire {name}" for name in pins] + ["output wire Y"]
        lines.append(f"module {cell} (")
        lines.append(",\n".join(f"  {p}" for p in ports))
        lines.append(");")
        lines.append(f"  assign #{delay:.3f} Y = {_to_verilog(node)};")
        lines.append("endmodule")
        lines.append("")
    return "\n".join(lines)


def _to_verilog(node) -> str:
    if node[0] == "var":
        return node[1]
    if node[0] == "not":
        return f"(~{_to_verilog(node[1])})"
    op = {"&": "&", "|": "|", "^": "^"}[node[1]]
    return f"({_to_verilog(node[2])} {op} {_to_verilog(node[3])})"


def build_glitch_testbench(
    top: str,
    input_names: Sequence[str],
    output_names: Sequence[str],
    transitions: Sequence[TransitionProbe],
) -> str:
    """A self-checking testbench that flags any stable output that glitches.

    For each transition it drives the inputs to their stable values, lets the
    circuit settle, records the output, toggles the changing input, and samples
    the output at unit-delay granularity — any deviation from the settled value
    is a glitch, and a final value that differs from the initial is a functional
    error.
    """
    lines = [
        "// Glitch-simulation testbench (stage 5b). Fundamental mode only.",
        "`timescale 1ns/1ps",
        "",
        "module glitch_tb;",
    ]
    for name in input_names:
        lines.append(f"  reg {name};")
    for name in output_names:
        lines.append(f"  wire {name};")
    for name in output_names:
        lines.append(f"  reg _exp_{name};")
    lines.append("  integer _glitches;")
    lines.append("")
    conn = [f".{name}({name})" for name in input_names]
    conn += [f".{name}({name})" for name in output_names]
    lines.append(f"  {top} dut ({', '.join(conn)});")
    lines.append("")
    lines.append("  initial begin")
    lines.append("    _glitches = 0;")

    for probe in transitions:
        changing = probe.changing_input
        for name in input_names:
            if name == changing:
                continue
            bit = "1'b1" if probe.stable_inputs[name] else "1'b0"
            lines.append(f"    {name} = {bit};")
        # hold the state (feedback) nets at their settled source values so the
        # combinational logic is exercised around the input change alone
        for net, value in sorted(probe.fixed_nets.items()):
            lines.append(f"    force dut.{net} = 1'b{value};")
        lines.append(f"    {changing} = 1'b{'1' if probe.from_value else '0'};")
        lines.append("    #10;")
        # record the settled value of each output, then toggle and watch for a
        # transient change away from it
        for name in output_names:
            lines.append(f"    _exp_{name} = {name};")
        lines.append(f"    {changing} = 1'b{'0' if probe.from_value else '1'};")
        lines.append("    repeat (10) begin")
        lines.append("      #1;")
        for name in output_names:
            lines.append(
                f"      if ({name} !== _exp_{name}) begin "
                f'$display("GLITCH: {name}"); _glitches = _glitches + 1; end'
            )
        lines.append("    end")
        for name in output_names:
            lines.append(
                f"    if ({name} !== _exp_{name}) begin "
                f'$display("STABLE_FAIL: {name}"); _glitches = _glitches + 1; end'
            )
        for net in sorted(probe.fixed_nets):
            lines.append(f"    release dut.{net};")
    lines.append("    if (_glitches == 0) $display(\"GLITCH_PASS\");")
    lines.append("    else $display(\"GLITCH_FAIL (%0d)\", _glitches);")
    lines.append("    $finish;")
    lines.append("  end")
    lines.append("endmodule")
    lines.append("")
    return "\n".join(lines)
