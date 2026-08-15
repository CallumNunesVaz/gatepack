"""Parts data model — the ``parts.csv`` schema of §10.1.

Column order::

    cell,tier,family,part_suffix,equivalents,function,inputs,\\
    gates_per_pkg,package,mfrs,vcc_min,vcc_max,area,tpd_ns,iq_ua

Second-sourcing (§10.1 [R4-9]): a cell is second-sourced when
``len(mfrs) + len(equivalents) >= 2``.  ``equivalents`` are alternate,
differently-numbered part numbers encoded ``PN:mfr;PN:mfr``.  ``mfrs`` are
manufacturers of *this* part number.

Every validation error names the offending cell.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping, Sequence

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic import ValidationError

TIERS = ("G", "F", "M", "S")

DEFAULT_VCC = 3.3

REQUIRED_COLUMNS = (
    "cell",
    "tier",
    "family",
    "part_suffix",
    "equivalents",
    "function",
    "inputs",
    "gates_per_pkg",
    "package",
    "mfrs",
    "vcc_min",
    "vcc_max",
    "area",
    "tpd_ns",
    "iq_ua",
)


class PartError(ValueError):
    """A ``parts.csv`` row failed validation.

    ``cell`` names the offending cell; ``message`` describes the failure.
    """

    def __init__(self, cell: str, message: str) -> None:
        self.cell = cell
        super().__init__(f"{cell}: {message}")


class Equivalent(BaseModel):
    """An alternate, functionally equivalent part number and its maker."""

    part_number: str
    mfr: str

    @classmethod
    def parse(cls, raw: str) -> "Equivalent":
        part_number, sep, mfr = raw.partition(":")
        if not sep or not part_number.strip() or not mfr.strip():
            raise ValueError(f"equivalents entry {raw!r} is not in 'PN:mfr' form")
        return cls(part_number=part_number.strip(), mfr=mfr.strip())

    def __str__(self) -> str:
        return f"{self.part_number}:{self.mfr}"


class Part(BaseModel):
    """One row of ``parts.csv``."""

    cell: str
    tier: str
    family: str
    part_suffix: str
    equivalents: list[Equivalent] = Field(default_factory=list)
    function: str | None = None
    inputs: int
    gates_per_pkg: int
    package: str
    mfrs: list[str] = Field(default_factory=list)
    vcc_min: float
    vcc_max: float
    area: float
    tpd_ns: float | None = None
    iq_ua: float | None = None

    @field_validator("tier")
    @classmethod
    def _validate_tier(cls, v: str) -> str:
        if v not in TIERS:
            raise ValueError(f"tier must be one of {TIERS}, got {v!r}")
        return v

    @field_validator("inputs", "gates_per_pkg")
    @classmethod
    def _validate_nonneg_int(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"must be non-negative, got {v}")
        return v

    @field_validator("area", "vcc_min", "vcc_max")
    @classmethod
    def _validate_nonneg_float(cls, v: float) -> float:
        if v < 0:
            raise ValueError(f"must be non-negative, got {v}")
        return v

    @model_validator(mode="after")
    def _validate_vcc_range(self) -> "Part":
        if self.vcc_min > self.vcc_max:
            raise ValueError(f"vcc_min ({self.vcc_min}) exceeds vcc_max ({self.vcc_max})")
        return self

    @classmethod
    def from_row(cls, row: Mapping[str, str]) -> "Part":
        cell = (row.get("cell") or "").strip()
        if not cell:
            raise PartError("<missing>", "cell name is empty")

        function = (row.get("function") or "").strip()
        try:
            return cls(
                cell=cell,
                tier=(row.get("tier") or "").strip(),
                family=(row.get("family") or "").strip(),
                part_suffix=(row.get("part_suffix") or "").strip(),
                equivalents=_parse_equivalents(row.get("equivalents"), cell),
                function=function or None,
                inputs=_to_int(row.get("inputs"), cell, "inputs"),
                gates_per_pkg=_to_int(row.get("gates_per_pkg"), cell, "gates_per_pkg"),
                package=(row.get("package") or "").strip(),
                mfrs=_split_semicolon(row.get("mfrs")),
                vcc_min=_to_float(row.get("vcc_min"), cell, "vcc_min"),
                vcc_max=_to_float(row.get("vcc_max"), cell, "vcc_max"),
                area=_to_float(row.get("area"), cell, "area"),
                tpd_ns=_to_optional_float(row.get("tpd_ns"), cell, "tpd_ns"),
                iq_ua=_to_optional_float(row.get("iq_ua"), cell, "iq_ua"),
            )
        except ValidationError as exc:
            raise PartError(cell, _format_validation_error(exc)) from exc

    @property
    def second_source_count(self) -> int:
        return len(self.mfrs) + len(self.equivalents)

    @property
    def is_second_sourced(self) -> bool:
        return self.second_source_count >= 2

    def vcc_compatible(self, project_vcc: float) -> bool:
        return self.vcc_min <= project_vcc <= self.vcc_max


class DropReason(str, Enum):
    SINGLE_SOURCE = "single-sourced"
    VCC = "vcc-incompatible"
    TIER = "tier"


@dataclass(frozen=True)
class Exclusion:
    """A cell that was dropped from the Liberty file, and why."""

    cell: str
    reason: DropReason
    detail: str = ""

    def __str__(self) -> str:
        suffix = f" — {self.detail}" if self.detail else ""
        return f"{self.cell}: {self.reason.value}{suffix}"


def select_for_liberty(
    parts: Sequence[Part],
    project_vcc: float = DEFAULT_VCC,
    allow_single_source: bool = False,
) -> tuple[list[Part], list[Exclusion]]:
    """Split parts into Liberty-eligible and dropped cells.

    Rules (§10.1, §9.4 [R4-8]): M- and S-cells are never written; single-sourced
    cells are excluded unless ``allow_single_source``; cells whose supply range
    does not bracket ``project_vcc`` are excluded with the reason stated.
    """
    included: list[Part] = []
    excluded: list[Exclusion] = []
    for part in parts:
        if part.tier not in ("G", "F"):
            excluded.append(
                Exclusion(
                    part.cell,
                    DropReason.TIER,
                    f"tier {part.tier!r} is never an inference target",
                )
            )
            continue
        if not part.is_second_sourced and not allow_single_source:
            excluded.append(
                Exclusion(
                    part.cell,
                    DropReason.SINGLE_SOURCE,
                    f"{part.second_source_count} source(s); need >= 2 (use --allow-single-source)",
                )
            )
            continue
        if not part.vcc_compatible(project_vcc):
            excluded.append(
                Exclusion(
                    part.cell,
                    DropReason.VCC,
                    f"supply {part.vcc_min}..{part.vcc_max} V does not include {project_vcc} V",
                )
            )
            continue
        included.append(part)
    return included, excluded


def _split_semicolon(raw: str | None) -> list[str]:
    if raw is None:
        return []
    return [p.strip() for p in raw.split(";") if p.strip()]


def _parse_equivalents(raw: str | None, cell: str) -> list[Equivalent]:
    if raw is None or not raw.strip():
        return []
    out: list[Equivalent] = []
    for chunk in raw.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            out.append(Equivalent.parse(chunk))
        except ValueError as exc:
            raise PartError(cell, str(exc)) from exc
    return out


def _to_int(raw: str | None, cell: str, field: str) -> int:
    try:
        return int((raw or "").strip())
    except ValueError as exc:
        raise PartError(cell, f"{field} must be an integer, got {raw!r}") from exc


def _to_float(raw: str | None, cell: str, field: str) -> float:
    try:
        return float((raw or "").strip())
    except ValueError as exc:
        raise PartError(cell, f"{field} must be a number, got {raw!r}") from exc


def _to_optional_float(raw: str | None, cell: str, field: str) -> float | None:
    if raw is None or not raw.strip():
        return None
    return _to_float(raw, cell, field)


def _format_validation_error(exc: ValidationError) -> str:
    errors = exc.errors()
    if errors:
        first = errors[0]
        loc = ".".join(str(p) for p in first.get("loc", ()))
        msg = first.get("msg", "validation error")
        return f"{loc}: {msg}" if loc else msg
    return str(exc)


def load_parts(path: str | Path) -> list[Part]:
    """Load and validate a ``parts.csv`` file."""
    path = Path(path)
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        missing = [c for c in REQUIRED_COLUMNS if c not in fieldnames]
        if missing:
            raise PartError("<header>", f"missing columns: {missing}")
        return [Part.from_row(row) for row in reader]
