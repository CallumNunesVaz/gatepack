"""`gatepack simulate` — the C11 divergence table, computed from the core.

Produces the ``SimulationTable`` shape from ``app/shared/api.ts``: per-row input
assignment, optional state, ``expected`` from the specification, ``actual`` from
the mapped netlist, and a ``diverges`` flag.

The ``expected`` side **reuses C4's spec evaluation**
(:func:`gatepack.verify.simulation._expected_outputs`), so the divergence column
cannot disagree with the verified exhaustive check — the whole point of moving it
out of the renderer (a renderer-side "simulated" column compares the spec against
itself and can never disagree).  The ``actual`` side evaluates the combinational
cone of the mapped netlist in the *same* function table the C2 behavioural models
use (``parts.csv`` functions via :mod:`gatepack.liberty.boolean`), so for the
combinational case it cannot drift from what Icarus would compute against
``cells_sim.v``.

Sequential (F/M/S) cell outputs are unknown: the combinational cone is evaluated
and state is not clocked.  Divergence is therefore only asserted where both sides
are known, which is exactly the combinational case where "which minterm
disagrees" is meaningful.  That limitation is honest, not silent: a state-held
output appears as ``'x'`` in ``actual``, and a ``'x'`` never counts as a
divergence.

Above the row cap the result is ``exhaustive: false`` and truncated to the cap
rather than hanging; the truncation is carried in the ``exhaustive`` flag, never
left implicit (§21.4's no-coverage-number principle applied to the interactive
table).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

from gatepack.frontend.model import CompiledDesign
from gatepack.liberty import boolean
from gatepack.netlist import MappedNetlist
from gatepack.parts import Part
from gatepack.provenance.match import _PREMAP_PRIMITIVES
from gatepack.verify import simulation as sim_mod

# The interactive table is capped well below the verification exhaustive cap
# (``VerifyConfig.exhaustive_cap`` is 2^24): this table is meant to be rendered,
# not proven.  The cap is what makes ``exhaustive`` go false.
DEFAULT_MAX_ROWS = 4096

_CONSTANT_BITS: dict[str, bool] = {"0": False, "1": True}
_UNKNOWN = {"x", "z"}


@dataclass(frozen=True)
class SimulateConfig:
    """Configuration for :func:`build_simulation_table`."""

    max_rows: int = DEFAULT_MAX_ROWS


def _bit_str(value: bool) -> str:
    return "1" if value else "0"


def _value_str(value: bool | None) -> str:
    return "x" if value is None else _bit_str(value)


def _assignment(inputs: Sequence[str], code: int) -> dict[str, bool]:
    """The input assignment for ``code``, MSB-first — identical to C4's ``_all_assignments``."""
    n = len(inputs)
    return {name: bool(code & (1 << (n - 1 - i))) for i, name in enumerate(inputs)}


def _total_rows(compiled: CompiledDesign) -> int:
    return len(compiled.state_order) * (1 << len(compiled.input_names))


# ---------------------------------------------------------------------------
# Mapped-netlist combinational evaluation
# ---------------------------------------------------------------------------


def _g_evaluator(part: Part) -> Callable[[Mapping[str, bool]], bool]:
    """A G-cell evaluator over the *same* function string ``cells_sim.v`` uses."""
    function = part.function or ""
    inputs = part.inputs

    def evaluate(env: Mapping[str, bool]) -> bool:
        return boolean.evaluate(function, inputs, dict(env))

    return evaluate


def _functions(parts: Sequence[Part]) -> dict[str, Callable[[Mapping[str, bool]], bool]]:
    """Cell-type -> boolean evaluator: library G-cells + Yosys ``$_*`` primitives.

    The ``$_*`` primitives come from the same table
    :mod:`gatepack.provenance.match` uses for cone signatures, so a residual
    un-mapped primitive is evaluated identically everywhere.
    """
    functions: dict[str, Callable[[Mapping[str, bool]], bool]] = dict(_PREMAP_PRIMITIVES)
    for part in parts:
        if part.tier == "G" and part.function:
            functions[part.cell] = _g_evaluator(part)
    return functions


def evaluate_mapped_netlist(
    mapped: MappedNetlist,
    functions: Mapping[str, Callable[[Mapping[str, bool]], bool]],
    inputs: Mapping[str, bool],
) -> dict[str, bool | None]:
    """Evaluate the combinational cone of ``mapped`` under ``inputs``.

    Returns ``output port name -> bool`` for every output port; an output that
    depends on an unclocked sequential cell (or an unknown cell type) is ``None``
    (unknown).  Iterates to a fixpoint exactly like the renderer's
    ``simulateCombinational``, but over the core's function table.
    """
    values: dict[str, bool | None] = {name: inputs.get(name) for name in mapped.inputs}
    cells = mapped.cells

    def bit_value(net: str | None) -> bool | None:
        if net is None or net in _UNKNOWN:
            return None
        if net in _CONSTANT_BITS:
            return _CONSTANT_BITS[net]
        return values.get(net)

    for _ in range(len(cells) + 1):
        changed = False
        for cell in cells:
            output_pins = cell.output_pins
            if not output_pins:
                continue
            fn = functions.get(cell.cell)
            if fn is None:
                result: bool | None = None
            else:
                env: dict[str, bool] = {}
                unknown = False
                for pin in cell.input_pins:
                    v = bit_value(cell.connections.get(pin))
                    if v is None:
                        unknown = True
                        break
                    env[pin] = v
                result = None if unknown else fn(env)
            for pin in output_pins:
                net = cell.connections.get(pin)
                if net is None or net in _CONSTANT_BITS or net in _UNKNOWN:
                    continue
                if values.get(net) is not result:
                    values[net] = result
                    changed = True
        if not changed:
            break

    return {name: values.get(name) for name in mapped.outputs}


# ---------------------------------------------------------------------------
# The table
# ---------------------------------------------------------------------------


def _diverges(expected: Mapping[str, bool], actual: Mapping[str, bool | None]) -> bool:
    """True when expected and actual disagree on any output where both are known."""
    for name, want in expected.items():
        got = actual.get(name)
        if got is not None and got != want:
            return True
    return False


def build_simulation_table(
    compiled: CompiledDesign,
    mapped: MappedNetlist | None,
    parts: Sequence[Part] | None = None,
    config: SimulateConfig | None = None,
) -> dict:
    """Build the ``SimulationTable`` payload (``app/shared/api.ts``) for ``compiled``.

    ``mapped`` is ``None`` when synthesis has not run: ``actual`` is omitted from
    every row and ``diverges`` stays false — never fabricated.
    """
    cfg = config or SimulateConfig()
    parts = list(parts or ())

    input_names = list(compiled.input_names)
    output_names = list(compiled.output_names)
    states = list(compiled.state_order)
    multi_state = len(states) > 1

    total = _total_rows(compiled)
    exhaustive = total <= cfg.max_rows
    row_limit = total if exhaustive else cfg.max_rows

    functions = _functions(parts) if mapped is not None else {}

    rows: list[dict] = []
    produced = 0
    for state in states:
        if produced >= row_limit:
            break
        for code in range(1 << len(input_names)):
            if produced >= row_limit:
                break
            assignment = _assignment(input_names, code)
            expected_bits = sim_mod._expected_outputs(compiled, state, assignment)
            expected = {name: _bit_str(v) for name, v in expected_bits.items()}

            row: dict = {
                "inputs": {name: _bit_str(v) for name, v in assignment.items()},
                "expected": expected,
            }
            if multi_state:
                row["state"] = state
            if mapped is not None:
                actual = evaluate_mapped_netlist(mapped, functions, assignment)
                row["actual"] = {name: _value_str(v) for name, v in actual.items()}
                row["diverges"] = _diverges(expected_bits, actual)
            else:
                row["diverges"] = False
            rows.append(row)
            produced += 1

    return {
        "inputNames": input_names,
        "outputNames": output_names,
        "rows": rows,
        # The FSM design model has no don't-care syntax in ``output_logic``, and
        # the front-end rejects unreachable states outright, so both counts are
        # honest zeros for a compilable design (see BUILD-NOTES-M16).
        "dontCareCount": 0,
        "unreachableCount": 0,
        "exhaustive": exhaustive,
    }


def load_mapped(path: str | Path) -> MappedNetlist | None:
    """Read a ``mapped.json`` if it exists, else ``None`` (synthesis not run)."""
    mapped_path = Path(path)
    if not mapped_path.exists():
        return None
    from gatepack.netlist import load_mapped_json

    return load_mapped_json(mapped_path)


__all__ = [
    "DEFAULT_MAX_ROWS",
    "SimulateConfig",
    "build_simulation_table",
    "evaluate_mapped_netlist",
    "load_mapped",
]
