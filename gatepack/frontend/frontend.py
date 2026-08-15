"""C1 front-end orchestration: ``design.yaml`` -> Verilog + properties.

Public entry points:

* :func:`compile_design_file` — the CLI path (reads a file, uses its basename in
  ``gp_src`` attributes).
* :func:`compile_design_text` — test path (explicit source name).
* :func:`compile_design` — compile an already-parsed :class:`Design`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from pydantic import ValidationError

from gatepack.frontend import model as model_mod
from gatepack.frontend import verilog as verilog_mod
from gatepack.frontend import yaml_subset as yaml_mod
from gatepack.frontend.errors import AsyncRefused, CompileError
from gatepack.frontend.model import CompiledDesign
from gatepack.frontend.schema import Design


@dataclass(frozen=True)
class CompileResult:
    compiled: CompiledDesign
    verilog: str
    properties: str


def compile_design_file(path: str | Path) -> CompileResult:
    path = Path(path)
    text = path.read_text()
    return compile_design_text(text, source_name=path.name)


def compile_design_text(text: str, source_name: str = "design.yaml") -> CompileResult:
    try:
        node = yaml_mod.parse(text)
    except yaml_mod.ParseError as exc:
        raise CompileError(str(exc)) from exc

    data = yaml_mod.to_python(node)
    provenance = yaml_mod.provenance(node)
    return compile_design(data, source_name=source_name, provenance=provenance)


def compile_design(
    data: object,
    source_name: str = "design.yaml",
    provenance: Mapping[str, int] | None = None,
) -> CompileResult:
    try:
        design = Design.model_validate(data)
    except ValidationError as exc:
        raise CompileError(_format_validation_error(exc)) from exc

    if design.timing_model == "asynchronous":
        raise AsyncRefused(_async_refusal(design.name))

    compiled = model_mod.compile_design(design, source_name, provenance or {})
    verilog = verilog_mod.emit_verilog(compiled)
    properties = verilog_mod.emit_properties(compiled)
    return CompileResult(compiled=compiled, verilog=verilog, properties=properties)


def _async_refusal(name: str) -> str:
    return (
        f"refusing to synthesise asynchronous design {name!r}: v0.1.0 does not "
        f"ship asynchronous synthesis (§7.3). Three problems are unsolved in "
        f"general, not merely deferred: (1) factoring a hazard-free two-level "
        f"cover into fan-in-3 gates is not hazard-preserving; (2) "
        f"single-variable-change state assignment needs a distinct STT method "
        f"and race-freedom validation; (3) Espresso does not emit hazard-free "
        f"covers by default. Emitting a netlist that is formally equivalent yet "
        f"hazardous on the bench is the worst possible output (§7.3). Real async "
        f"synthesis is a v0.2 research task (§23.3)."
    )


def _format_validation_error(exc: ValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "invalid design.yaml"
    parts: list[str] = []
    for err in errors:
        loc = ".".join(str(p) for p in err.get("loc", ())) or "<root>"
        msg = err.get("msg", "validation error")
        parts.append(f"{loc}: {msg}")
    return "invalid design.yaml: " + "; ".join(parts)


__all__ = [
    "AsyncRefused",
    "CompileError",
    "CompileResult",
    "CompiledDesign",
    "compile_design",
    "compile_design_file",
    "compile_design_text",
]
