"""AsynchronousVerify — independent hazard verification (stage 5, §7.3).

The asynchronous verification strategy runs the two independent hazard checks
over the *mapped netlist* (the actual output): the ternary simulation (5a) and
the Icarus glitch simulation (5b).  The check itself lives in
:mod:`gatepack.verify.hazard`, which imports nothing from the synthesis stages.

The strategy re-derives the flow table and the single-variable-change assignment
from the compiled spec (they are deterministic functions of the spec), then
enumerates the fundamental-mode transition probes itself.  The one hard rule of
the package applies: a netlist that fails either check is refused — the check
results are honest ``FAILED`` checks, and the caller must not emit.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Mapping, Sequence

from gatepack.frontend.model import CompiledDesign
from gatepack.netlist import MappedNetlist, parse_mapped_json
from gatepack.synth.async_.assign import Assignment
from gatepack.synth.async_.flowtable import FlowTable
from gatepack.verify import hazard
from gatepack.verify.base import (
    CheckResult,
    CheckStatus,
    ToolRunner,
    VerificationReport,
    VerificationStrategy,
    VerifyConfig,
)
from gatepack.toolchain import iverilog_command, vvp_command


def cell_functions_from_liberty(lib_text: str) -> dict[str, str]:
    """Extract the G-cell ``function`` strings from a Liberty file.

    The asynchronous netlist is mapped to the same G-cells the Liberty file
    describes (INV/AND2/OR2/…), so the function table the hazard checker needs is
    read from the actual library, not hard-coded.  F-cells' ``function`` values
    (``IQ``/``IQN``, the state-variable reference on the ``Q`` pin) are not
    boolean expressions over ``A``/``B``/``C`` and are excluded, because the
    asynchronous netlist never instantiates an F-cell and the hazard checker
    cannot evaluate a state variable.
    """
    pattern = re.compile(
        r'cell\s*\(\s*(\w+)\s*\)\s*\{.*?function\s*:\s*"([^"]+)"', re.DOTALL
    )
    return {
        cell: func
        for cell, func in pattern.findall(lib_text)
        if func not in ("IQ", "IQN")
    }


#: Upper bound on the number of total-state/input-change pairs the functional
#: check will enumerate.  Above it the check reports ``not applicable`` (§21.4):
#: an asynchronous design that needs more than this many pairs to check has
#: outgrown exhaustive simulation, and a coverage figure on random stimulus is
#: never allowed to stand in for it.  Mirrors the synchronous ``exhaustive_cap``.
ASYNC_FUNC_ENUM_CAP = 1 << 24

#: The functional check's name in the report and manifest.
FUNCTIONAL_CHECK_NAME = "functional (fundamental mode)"


def enumerate_functional_pairs(table: FlowTable) -> list[tuple[int, int, int]]:
    """Every ``(state_index, source_combo_index, changing_input_index)`` pair.

    The functional check's domain: every **stable total state** (a state/input
    combination the flow table marks stable) combined with every **single-input
    change**.  Under fundamental mode and the declared mutual exclusion only a
    single input may change at a time, so every single-input change from a stable
    total state is admissible; the enumeration is exhaustive over that domain —
    never a random sample (§C4.3, §21.4).
    """
    pairs: list[tuple[int, int, int]] = []
    for si, state in enumerate(table.states):
        for ci in range(len(table.combos)):
            if table.next_state[si][ci] != state:
                continue
            for d in range(len(table.input_names)):
                pairs.append((si, ci, d))
    return pairs


def run_functional_check(
    netlist: MappedNetlist,
    cell_functions: dict[str, str],
    table: FlowTable,
    assignment: Assignment,
    max_pairs: int = ASYNC_FUNC_ENUM_CAP,
) -> CheckResult:
    """Exhaustively simulate the mapped netlist against the flow table.

    For every stable total state ``(state, combo)`` and every single-input change
    ``d`` the netlist is evaluated to a fixed point with the state feedback held at
    the source state's code and the inputs at the post-change combination, then the
    settled next-state code and the outputs are compared against what the flow
    table says they must be.  A mismatch is a **failed** check naming the total
    state, the changing input, and the expected/actual values — never a warning.

    The function under test is the *cover* (stage 4) and its emission, not the
    assignment: the flow table is re-derived from the spec (its own semantics) and
    the single-variable-change assignment is re-derived deterministically (z3 runs
    with a fixed seed), exactly as the hazard probes already do.  A wrong cover is
    therefore caught; a hypothetical bug in the assignment would not be, but the
    assignment is not what this check exists to validate.
    """
    pairs = enumerate_functional_pairs(table)
    total = len(pairs)
    if total > max_pairs:
        return CheckResult(
            FUNCTIONAL_CHECK_NAME,
            CheckStatus.NOT_APPLICABLE,
            f"{total} total-state/input-change pairs exceed the enumeration cap "
            f"{max_pairs}; the netlist is not exhaustively simulated against the "
            "flow table, so 'the netlist implements the design' is not claimed "
            "(§7.3, §21.4)",
            kind="simulation",
        )

    combo_index = {combo: i for i, combo in enumerate(table.combos)}
    code_to_state = {code: state for state, code in assignment.codes.items()}
    state_nets = [f"s_{j}" for j in range(assignment.width)]

    mismatches: list[str] = []
    for si, ci, d in pairs:
        state = table.states[si]
        src_combo = table.combos[ci]
        dst_combo = _flip_combo(src_combo, d)
        dst_ci = combo_index[dst_combo]
        expected_next = table.next_state[si][dst_ci]
        expected_outputs = {name: (1 if b else 0) for name, b in table.outputs[si][dst_ci]}

        held = {net: assignment.bit(state, j) for j, net in enumerate(state_nets)}
        held.update(
            {name: (1 if b else 0) for name, b in zip(table.input_names, dst_combo)}
        )

        settled = hazard.evaluate_fixed_point(netlist, cell_functions, held, ternary=False)
        driven = hazard.driven_values(netlist, cell_functions, settled, state_nets)
        actual_next_code = [driven[net] for net in state_nets]
        expected_next_code = [
            assignment.bit(expected_next, j) for j in range(assignment.width)
        ]
        actual_outputs = {
            name: settled.get(name, hazard._X) for name in table.output_names
        }

        if actual_next_code == expected_next_code and actual_outputs == expected_outputs:
            continue

        actual_next = code_to_state.get(_bits_to_code(actual_next_code), "<no valid state>")
        mismatches.append(
            f"stable total state ({state}, {_render_combo(table.input_names, src_combo)}) "
            f"changing {table.input_names[d]}: expected next {expected_next} "
            f"outputs {_render_outputs(expected_outputs)}, got next {actual_next} "
            f"outputs {_render_outputs(actual_outputs)}"
        )

    if mismatches:
        shown = mismatches[:10]
        tail = f" (+{len(mismatches) - len(shown)} more)" if len(mismatches) > len(shown) else ""
        return CheckResult(
            FUNCTIONAL_CHECK_NAME,
            CheckStatus.FAILED,
            "netlist does not implement the flow table: " + "; ".join(shown) + tail,
            kind="simulation",
        )
    return CheckResult(
        FUNCTIONAL_CHECK_NAME,
        CheckStatus.PASSED,
        f"{total} total-state/input-change pairs checked; netlist matches the "
        "flow table",
        kind="simulation",
    )


def _flip_combo(combo: tuple[bool, ...], index: int) -> tuple[bool, ...]:
    out = list(combo)
    out[index] = not out[index]
    return tuple(out)


def _bits_to_code(bits: Sequence[int]) -> int:
    return sum(bit << j for j, bit in enumerate(bits))


def _render_combo(input_names: Sequence[str], combo: tuple[bool, ...]) -> str:
    return ", ".join(f"{n}={1 if b else 0}" for n, b in zip(input_names, combo))


def _render_outputs(outputs: Mapping[str, int]) -> str:
    return ", ".join(f"{n}={v}" for n, v in sorted(outputs.items()))


def build_transition_probes(
    table: FlowTable, assignment: Assignment
) -> list[hazard.TransitionProbe]:
    """The fundamental-mode transition probes: every single-input change from a
    stable total state, with the state bits held at their source values."""
    probes: list[hazard.TransitionProbe] = []
    for si, state in enumerate(table.states):
        for ci, combo in enumerate(table.combos):
            if table.next_state[si][ci] != state:
                continue  # only a settled (stable) total state starts a transition
            for d in range(len(table.input_names)):
                stable = {
                    name: combo[k]
                    for k, name in enumerate(table.input_names)
                    if k != d
                }
                fixed = {
                    f"s_{j}": assignment.bit(state, j) for j in range(assignment.width)
                }
                probes.append(
                    hazard.TransitionProbe(
                        changing_input=table.input_names[d],
                        stable_inputs=stable,
                        fixed_nets=fixed,
                        from_value=combo[d],
                    )
                )
    return probes


class AsynchronousVerify(VerificationStrategy):
    """Runs stage 5a (ternary) and stage 5b (Icarus glitch) over the mapped netlist."""

    def verify(
        self,
        config: VerifyConfig,
        compiled: CompiledDesign,
        runner: ToolRunner,
        lib_text: str,
        sim_text: str,
    ) -> VerificationReport:
        mapped_path = Path(config.mapped_json)
        if not mapped_path.exists():
            return VerificationReport(
                checks=[
                    CheckResult(
                        "hazard (ternary)",
                        CheckStatus.NOT_RUN,
                        f"no mapped netlist at {mapped_path} (synthesis not run)",
                        kind="hazard",
                    )
                ]
            )

        netlist = parse_mapped_json(mapped_path.read_text())
        cell_functions = cell_functions_from_liberty(lib_text)
        return self.verify_netlist(netlist, cell_functions, compiled, runner, config)

    def verify_netlist(
        self,
        netlist: MappedNetlist,
        cell_functions: dict[str, str],
        compiled: CompiledDesign,
        runner: ToolRunner,
        config: VerifyConfig,
    ) -> VerificationReport:
        """Run both hazard checks against a parsed mapped netlist."""
        from gatepack.synth.async_ import assign_state_codes, build_flow_table

        table = build_flow_table(compiled)
        assignment = assign_state_codes(
            table,
            runner,
            workdir=str(Path(config.mapped_json).parent),
            design_name=compiled.design.name,
        )
        probes = build_transition_probes(table, assignment)
        checks = [
            self._ternary_check(netlist, cell_functions, probes),
            self._glitch_check(
                netlist, cell_functions, probes, runner, config
            ),
            run_functional_check(netlist, cell_functions, table, assignment),
        ]
        return VerificationReport(checks=checks)

    def _ternary_check(
        self,
        netlist: MappedNetlist,
        cell_functions: dict[str, str],
        probes: list[hazard.TransitionProbe],
    ) -> CheckResult:
        findings = hazard.check_static_hazards(netlist, cell_functions, probes)
        if findings:
            detail = "; ".join(
                f"{f.output} ({f.kind}, changing {f.changing_input})" for f in findings
            )
            return CheckResult(
                "hazard (ternary)",
                CheckStatus.FAILED,
                "potential static hazard: " + detail,
                kind="hazard",
            )
        return CheckResult(
            "hazard (ternary)",
            CheckStatus.PASSED,
            f"{len(probes)} fundamental-mode transition(s) checked, no potential "
            "static hazard",
            kind="hazard",
        )

    def _glitch_check(
        self,
        netlist: MappedNetlist,
        cell_functions: dict[str, str],
        probes: list[hazard.TransitionProbe],
        runner: ToolRunner,
        config: VerifyConfig,
    ) -> CheckResult:
        if not runner.available("iverilog"):
            return CheckResult(
                "hazard (glitch sim)",
                CheckStatus.NOT_RUN,
                "iverilog not installed (Icarus — glitch simulation)",
                kind="hazard",
            )
        top = netlist.top
        inputs = list(netlist.inputs)
        outputs = list(netlist.outputs)

        scratch = Path(config.mapped_v).parent
        scratch.mkdir(parents=True, exist_ok=True)
        cells_path = scratch / "async_unit_delay_cells.v"
        tb_path = scratch / "async_glitch_tb.v"
        vvp = str(scratch / "async_glitch.vvp")

        failures: list[str] = []
        for seed in range(3):
            cells_path.write_text(hazard.unit_delay_cells(cell_functions, seed=seed))
            tb_path.write_text(
                hazard.build_glitch_testbench(top, inputs, outputs, probes)
            )
            compile_result = runner.run(
                iverilog_command(
                    vvp, [config.mapped_v, str(cells_path), str(tb_path)]
                ),
                cwd=config.cwd,
            )
            if compile_result.returncode != 0:
                return CheckResult(
                    "hazard (glitch sim)",
                    CheckStatus.NOT_RUN,
                    "iverilog compile failed: "
                    + (compile_result.stderr or "").strip(),
                    kind="hazard",
                )
            run_result = runner.run(vvp_command(vvp), cwd=config.cwd)
            if "GLITCH_FAIL" in run_result.stdout or "STABLE_FAIL" in run_result.stdout:
                failures.append(f"seed {seed}: " + _glitch_detail(run_result.stdout))
            elif "GLITCH_PASS" not in run_result.stdout:
                return CheckResult(
                    "hazard (glitch sim)",
                    CheckStatus.NOT_RUN,
                    "unrecognized glitch-simulation output",
                    kind="hazard",
                )

        if failures:
            return CheckResult(
                "hazard (glitch sim)",
                CheckStatus.FAILED,
                "; ".join(failures),
                kind="hazard",
            )
        return CheckResult(
            "hazard (glitch sim)",
            CheckStatus.PASSED,
            "no output glitch observed across 3 delay-perturbation seeds",
            kind="hazard",
        )


def _glitch_detail(stdout: str) -> str:
    for line in stdout.splitlines():
        if "GLITCH" in line or "STABLE_FAIL" in line:
            return line.strip()
    return "glitch observed"
