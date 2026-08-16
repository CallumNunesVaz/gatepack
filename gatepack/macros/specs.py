"""M-cell *specification* models (§9.4, M8).

The behavioural model under ``gatepack/macros/models/CNT4.v`` is the
**implementation** model: what the mapped netlist's ``CNT4`` cell means, and the
file both exhaustive simulation and the *gate* side of C4 equivalence read
(§19 R25).  It is hand-written and is exactly the file a human can get wrong.

This module holds the independent **specification** side: what a 4-bit counter
is *required* to do, written from the cell's declared semantics (width/period,
enable, reset) in :data:`MCellSpec`, not copied from the implementation model.
C1 emits it as ``cells_spec.v``; the *golden* side of C4 equivalence reads it
while the gate side keeps reading ``cells_sim.v``.  Because the two files are
produced by different paths, mutating ``models/CNT4.v`` changes only the gate
side and the equivalence check fails — the acceptance criterion of the M-cell
mutation test.

Both the specification model and the ``(* blackbox *)`` declaration C1 puts in
``generated.v`` (so ``hierarchy -check`` accepts the instantiation while leaving
the physical part a black box for synthesis) derive from the *same* port list
here, so the two cannot drift from each other or from the implementation model's
port signature.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MCellPort:
    """One logical port of an M-cell, as the behavioural model exposes it."""

    name: str
    direction: str  # "input" | "output"
    width: int = 1


@dataclass(frozen=True)
class MCellSpec:
    """The *required* behaviour of an M-cell, expressed as data.

    ``width``/``step`` describe the counter/sequencer semantics (period is
    ``1 << width``); ``reset_pin``/``reset_active``/``reset_value`` describe the
    reset contract; ``enable_pin`` the count-enable contract.  Nothing here is
    read from the implementation model file — it is the specification that file
    must implement.
    """

    cell: str
    ports: tuple[MCellPort, ...]
    clock_pin: str
    reset_pin: str
    reset_active: str  # "low" | "high"
    enable_pin: str | None
    q_pin: str
    width: int
    kind: str = "counter"  # "counter" | "shift_register"
    step: int = 1
    reset_value: int = 0
    serial_in_pin: str | None = None
    description: str = ""

    @property
    def period(self) -> int:
        return 1 << self.width

    @property
    def flops(self) -> int:
        """Internal flop count, used by the §6 flop-count / clock-fanout metrics."""
        return self.width

    def port(self, name: str) -> MCellPort:
        for p in self.ports:
            if p.name == name:
                return p
        raise KeyError(f"{self.cell}: no port {name!r}")


CNT4_SPEC = MCellSpec(
    cell="CNT4",
    ports=(
        MCellPort("CLK", "input", 1),
        MCellPort("RST_N", "input", 1),
        MCellPort("EN", "input", 1),
        MCellPort("Q", "output", 4),
    ),
    clock_pin="CLK",
    reset_pin="RST_N",
    reset_active="low",
    enable_pin="EN",
    q_pin="Q",
    width=4,
    step=1,
    reset_value=0,
    description=(
        "4-bit synchronous binary counter: counts 0..15 by 1 while enabled, "
        "holds otherwise, asynchronous active-low reset to 0."
    ),
)

SR4_SPEC = MCellSpec(
    cell="SR4",
    kind="shift_register",
    ports=(
        MCellPort("CLK", "input", 1),
        MCellPort("RST_N", "input", 1),
        MCellPort("EN", "input", 1),
        MCellPort("SI", "input", 1),
        MCellPort("Q", "output", 4),
    ),
    clock_pin="CLK",
    reset_pin="RST_N",
    reset_active="low",
    enable_pin="EN",
    q_pin="Q",
    serial_in_pin="SI",
    width=4,
    reset_value=0,
    description=(
        "4-bit serial-in parallel-out shift register: shifts SI into the least "
        "significant bit while enabled, asynchronous active-low reset to 0."
    ),
)

_SPECS: dict[str, MCellSpec] = {s.cell: s for s in (CNT4_SPEC, SR4_SPEC)}


def known_spec_cells() -> tuple[str, ...]:
    """Every M-cell with a specification model (sorted)."""
    return tuple(sorted(_SPECS))


def get_spec(cell: str) -> MCellSpec:
    if cell not in _SPECS:
        raise KeyError(
            f"no specification model for M-cell {cell!r} (known: {sorted(_SPECS)})"
        )
    return _SPECS[cell]


def _port_decl(spec: MCellSpec, port: MCellPort, reg_output: bool) -> str:
    width = f"[{port.width - 1}:0] " if port.width > 1 else ""
    if port.direction == "input":
        return f"  input  wire {width}{port.name}"
    out_kind = "reg " if reg_output else "wire "
    return f"  output {out_kind}{width}{port.name}"


def spec_model(cell: str) -> str:
    """The independent specification model for ``cell`` (Verilog text)."""
    spec = get_spec(cell)
    reset_edge = "negedge" if spec.reset_active == "low" else "posedge"
    reset_cond = f"!{spec.reset_pin}" if spec.reset_active == "low" else spec.reset_pin
    q = spec.q_pin
    width = spec.width

    ports = ",\n".join(_port_decl(spec, p, reg_output=True) for p in spec.ports)

    advance = _advance_expression(spec)
    return "\n".join(
        [
            f"// {spec.cell} — specification model (§9.4 M8).",
            f"// {spec.description}",
            "//",
            "// Generated from gatepack/macros/specs.py, NOT copied from "
            f"gatepack/macros/models/{spec.cell}.v.  The two files are independent: "
            "C4 equivalence reads THIS file on the golden side and the "
            "implementation model on the gate side, so mutating the "
            "implementation model is caught.",
            "",
            f"module {spec.cell} (",
            ports,
            ");",
            f"  always @(posedge {spec.clock_pin} or {reset_edge} {spec.reset_pin}) begin",
            f"    if ({reset_cond})",
            f"      {q} <= {width}'d{spec.reset_value};",
            advance,
            "  end",
            "endmodule",
            "",
        ]
    )


def _advance_expression(spec: MCellSpec) -> str:
    """The ``else`` advance line(s) for ``spec``, keyed by its ``kind``.

    A counter adds ``step``; a shift register shifts the serial input into the
    low bit.  The two are written from different semantics so the spec side does
    not accidentally reproduce a defect shared with the implementation model.
    """
    q = spec.q_pin
    width = spec.width
    if spec.enable_pin is not None:
        guard = f"    else if ({spec.enable_pin})\n"
    else:
        guard = "    else\n"
    if spec.kind == "shift_register":
        body = f"      {q} <= {{{q}[{width - 2}:0], {spec.serial_in_pin}}};"
    else:
        body = f"      {q} <= {q} + {width}'d{spec.step};"
    return guard + body


def blackbox_module(cell: str) -> str:
    """The ``(* blackbox *)`` declaration C1 emits into ``generated.v``.

    Without it, ``hierarchy -check`` rejects the instantiation as referencing an
    undefined module.  Marking it blackbox keeps the physical part out of the
    ``dfflibmap``/``abc`` mapping while still elaborating.  ``write_verilog``
    drops this declaration (only the instantiation survives into ``mapped.v``),
    so reading the spec/impl model on the respective equivalence side does not
    collide with it.
    """
    spec = get_spec(cell)
    ports = ",\n".join(_port_decl(spec, p, reg_output=False) for p in spec.ports)
    return "\n".join(
        [
            "(* blackbox *)",
            f"module {spec.cell} (",
            ports,
            ");",
            "endmodule",
            "",
        ]
    )


def load_spec_models() -> str:
    """Concatenate the specification model of every known M-cell."""
    return "\n".join(spec_model(cell) for cell in known_spec_cells())


__all__ = [
    "MCellPort",
    "MCellSpec",
    "CNT4_SPEC",
    "SR4_SPEC",
    "blackbox_module",
    "get_spec",
    "known_spec_cells",
    "load_spec_models",
    "spec_model",
]
