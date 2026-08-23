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
    if path.suffix == ".gpk":
        # Single-file project (§10.4): extract the embedded design document and
        # compile it with provenance pointing at the .gpk's own line numbers.
        from gatepack.project import ProjectError, load_project

        try:
            project = load_project(path)
        except ProjectError as exc:
            raise CompileError(str(exc)) from exc
        return compile_design(
            project.design.data,
            source_name=path.name,
            provenance=project.design.provenance,
        )
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
        # Admission (stage 1) declines a design that cannot even be attempted,
        # naming the specific construct at fault.  An *admitted* asynchronous
        # design now compiles: the asynchronous backend synthesises in pure
        # Python (§7.3), not through the synchronous, clocked Verilog emitter,
        # so there is no behavioural Verilog or §11 property text for it and the
        # CompileResult carries an empty ``verilog``/``properties``.
        from gatepack.synth.async_.admit import admit

        admit(design)
        compiled = model_mod.compile_design(design, source_name, provenance or {})
        return CompileResult(compiled=compiled, verilog="", properties="")

    compiled = model_mod.compile_design(design, source_name, provenance or {})
    verilog = verilog_mod.emit_verilog(compiled)
    properties = verilog_mod.emit_properties(compiled)
    return CompileResult(compiled=compiled, verilog=verilog, properties=properties)


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
