"""Pydantic schema for ``design.yaml`` (§10.2).

The model mirrors the §10.2 example field-for-field.  Structural rules live
here (types, enums, identifier validity, uniqueness, ``initial`` membership);
semantic rules that need the whole compiled design (transition reachability,
guard overlap, exhaustiveness, expression references) live in ``model.py``.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

VERILOG_KEYWORDS = frozenset({
    "module", "endmodule", "input", "output", "inout", "wire", "reg", "assign",
    "always", "initial", "begin", "end", "if", "else", "case", "endcase",
    "default", "parameter", "localparam", "posedge", "negedge", "or", "and",
    "not", "nand", "nor", "xor", "xnor", "buf", "genvar", "generate",
    "endgenerate", "function", "endfunction", "task", "endtask", "integer",
    "real", "signed", "unsigned", "supply0", "supply1", "tri", "wand", "wor",
    "for", "while", "repeat", "forever", "wait", "event", "struct", "union",
    "typedef", "enum", "logic", "bit", "byte", "shortint", "int", "longint",
    "time", "generate", "specify", "endspecify",
})

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class DesignError(ValueError):
    """A ``design.yaml`` value failed structural validation."""


def is_valid_identifier(name: str) -> bool:
    return bool(_IDENTIFIER.match(name)) and name not in VERILOG_KEYWORDS


class Clock(BaseModel):
    signal: str
    freq_hz: int
    source: str


class Reset(BaseModel):
    signal: str
    active: Literal["low", "high"] = "low"
    async_assert: bool = True
    sync_deassert: bool = True
    source: str = ""

    @field_validator("signal")
    @classmethod
    def _signal_identifier(cls, v: str) -> str:
        if not is_valid_identifier(v):
            raise ValueError(f"reset signal {v!r} is not a valid Verilog identifier")
        return v


class InputPort(BaseModel):
    name: str
    sync: bool = False

    @field_validator("name")
    @classmethod
    def _name_identifier(cls, v: str) -> str:
        if not is_valid_identifier(v):
            raise ValueError(f"input name {v!r} is not a valid Verilog identifier")
        return v


class OutputPort(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def _name_identifier(cls, v: str) -> str:
        if not is_valid_identifier(v):
            raise ValueError(f"output name {v!r} is not a valid Verilog identifier")
        return v


class Transition(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    to: str
    when: str


class PropertySpec(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    kind: Literal["invariant", "reachability", "liveness", "mutex"]
    expr: str | None = None
    from_: str | None = Field(alias="from", default=None)
    to: str | None = None


class TestPoint(BaseModel):
    net: str


class MacroSpec(BaseModel):
    instance: str
    cell: str
    clock: str
    enable: str | None = None


class FundamentalMode(BaseModel):
    mutually_exclusive: list[list[str]] = Field(default_factory=list)


class Constraints(BaseModel):
    max_flops: int | None = None
    max_packages: int | None = None
    vcc: float = 3.3
    max_static_ua: float | None = None

    @field_validator("vcc")
    @classmethod
    def _vcc_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"vcc must be positive, got {v}")
        return v


class Packing(BaseModel):
    """§12 C5 packing overrides, persisted in ``design.yaml``.

    The packer has always accepted ``force_groups``; there was no way to
    *record* one, so an override made in the application died with the session.
    §C13 requires the opposite: "overrides persist in design.yaml", because a
    packing decision is a physical-adjacency judgement the engineer made and
    must be able to defend at review.

    Each group names mapped cells that must share a package. The packer still
    refuses a group whose cells are not the same function — an override may
    express a preference, never an impossibility.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    force_groups: list[list[str]] = Field(default_factory=list)


class Design(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    name: str
    timing_model: Literal["synchronous", "asynchronous"]
    clock: Clock | None = None
    reset: Reset
    encoding: Literal["one_hot", "binary", "gray"] = "one_hot"
    inputs: list[InputPort] = Field(default_factory=list)
    outputs: list[OutputPort] = Field(default_factory=list)
    expressions: dict[str, str] = Field(default_factory=dict)
    states: list[str]
    initial: str
    transitions: list[Transition] = Field(default_factory=list)
    output_logic: dict[str, str] = Field(default_factory=dict)
    properties: list[PropertySpec] = Field(default_factory=list)
    safe_state: dict[str, str] = Field(default_factory=dict)
    test_points: list[TestPoint] = Field(default_factory=list)
    macros: list[MacroSpec] = Field(default_factory=list)
    fundamental_mode: FundamentalMode | None = None
    constraints: Constraints = Field(default_factory=Constraints)
    packing: Packing = Field(default_factory=Packing)

    @field_validator("name")
    @classmethod
    def _name_identifier(cls, v: str) -> str:
        if not is_valid_identifier(v):
            raise ValueError(f"design name {v!r} is not a valid Verilog identifier")
        return v

    @field_validator("states")
    @classmethod
    def _state_names(cls, v: list[str]) -> list[str]:
        for s in v:
            if not is_valid_identifier(s):
                raise ValueError(f"state {s!r} is not a valid Verilog identifier")
        return v

    @field_validator("safe_state", mode="before")
    @classmethod
    def _coerce_safe_state(cls, v: object) -> object:
        if isinstance(v, dict):
            return {k: _safe_state_str(val) for k, val in v.items()}
        return v

    @field_validator("safe_state")
    @classmethod
    def _safe_state_values(cls, v: dict[str, str]) -> dict[str, str]:
        for key, value in v.items():
            if value not in ("0", "1", "any"):
                raise ValueError(
                    f"safe_state[{key!r}] must be 0, 1 or 'any', got {value!r}"
                )
        return v

    @model_validator(mode="after")
    def _structural_checks(self) -> "Design":
        _unique(self, "input", [p.name for p in self.inputs])
        _unique(self, "output", [p.name for p in self.outputs])
        _unique(self, "state", self.states)
        _unique(self, "expression", list(self.expressions))
        if self.initial not in self.states:
            raise ValueError(f"initial state {self.initial!r} is not in states {self.states}")
        if self.timing_model == "synchronous" and self.clock is None:
            raise ValueError("synchronous design requires a 'clock' block")
        output_names = {p.name for p in self.outputs}
        for name in self.output_logic:
            if name not in output_names:
                raise ValueError(f"output_logic[{name!r}] is not a declared output")
        for name in self.safe_state:
            if name not in output_names:
                raise ValueError(f"safe_state[{name!r}] is not a declared output")
        return self


def _unique(design: Design, kind: str, names: list[str]) -> None:
    seen: set[str] = set()
    for name in names:
        if name in seen:
            raise ValueError(f"duplicate {kind} name {name!r}")
        seen.add(name)


def _safe_state_str(value: object) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    return str(value)
