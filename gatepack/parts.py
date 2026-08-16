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
import io
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping, Sequence

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic import ValidationError

TIERS = ("G", "F", "M", "S")

DEFAULT_VCC = 3.3


class Verification(str, Enum):
    """Whether a part's electrical values are verified or placeholders (§1.3, §23).

    A *placeholder* value is a different thing from a *verified* one, so a code
    path that consumes an electrical quantity has to acknowledge which it has.
    Every part defaults to :data:`PLACEHOLDER` — the fail-closed choice — and is
    promoted to :data:`VERIFIED` only when a real, pinned datasheet citation
    backs its values (see ``<name>.refs.md``).
    """

    VERIFIED = "verified"
    PLACEHOLDER = "placeholder"


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
    #: Whether this row's electrical values (vcc/tpd/iq/area/gates_per_pkg) are
    #: cited in a real datasheet or are placeholders.  Defaults to placeholder —
    #: a value without a citation must never read as verified.
    verification: Verification = Verification.PLACEHOLDER

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
    def part_number(self) -> str:
        """Full part number for the BOM.

        ``family`` + ``part_suffix`` are composed as ``74<FAMILY><SUFFIX>`` for
        the 74-logic families (``74AUP1G00``), except when the suffix already
        carries the family (``HC4017`` -> ``74HC4017``).  S-cells with no family
        (``-``) use the suffix verbatim (``TPS3839``).
        """
        suffix = self.part_suffix
        if not suffix:
            return ""
        family = self.family
        if family in ("", "-"):
            return suffix
        if suffix.startswith(family):
            return "74" + suffix
        return "74" + family + suffix

    @property
    def second_source_count(self) -> int:
        return len(self.mfrs) + len(self.equivalents)

    @property
    def is_second_sourced(self) -> bool:
        return self.second_source_count >= 2

    @property
    def is_verified(self) -> bool:
        """True when this row's electrical values are backed by a citation."""
        return self.verification is Verification.VERIFIED

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


def representative_parts(parts: Sequence[Part]) -> list[Part]:
    """One part per distinct cell — the representative of that logic function.

    A function can be offered by several packages (74AUP1G00 holds one NAND2,
    74AUP2G00 holds two). Liberty and ``cells_sim.v`` describe *functions*, so
    each must appear exactly once in both; which physical package provides it
    is the packer's decision, made later and separately.

    Emitting one entry per part instead produces a Liberty file with two
    `cell (NAND2)` groups — malformed in the way R1 warns about, since it
    parses and silently keeps the last — and a `cells_sim.v` with duplicate
    module definitions, which Icarus rejects outright.

    The representative is the fewest gates per package, then the lowest part
    suffix, so it does not depend on CSV row order. Order of the result is
    first appearance: sorting would change the emitted library for every
    existing design and perturb both ABC's mapping and the §5.5
    byte-reproducibility check, for no benefit.
    """
    chosen: dict[str, Part] = {}
    order: list[str] = []
    for part in parts:
        current = chosen.get(part.cell)
        if current is None:
            chosen[part.cell] = part
            order.append(part.cell)
        elif (part.gates_per_pkg, part.part_suffix) < (
            current.gates_per_pkg,
            current.part_suffix,
        ):
            chosen[part.cell] = part
    return [chosen[name] for name in order]


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


def verification_from_citation(status: str | None) -> Verification:
    """Map a ``<name>.refs.md`` electrical-status text to a :class:`Verification`.

    ``None`` (no citation at all) and any text carrying ``unverified`` or
    ``placeholder`` are placeholders; a citation that names a real document is
    verified.  This is the *only* place the status words are interpreted.
    """
    if status is None:
        return Verification.PLACEHOLDER
    lowered = status.lower()
    if "unverified" in lowered or "placeholder" in lowered:
        return Verification.PLACEHOLDER
    return Verification.VERIFIED


def mark_verification(parts: Sequence[Part], citations: Mapping[str, str]) -> None:
    """Attach each part's verification status from its refs citation (in place)."""
    for part in parts:
        part.verification = verification_from_citation(citations.get(part.cell))


class UnverifiedGatesPerPackageError(PartError):
    """The build refuses to ship parts whose ``gates_per_pkg`` is unverified.

    ``gates_per_pkg`` decides how many physical packages the board needs and
    which gates share a die; a wrong value produces a netlist that physically
    cannot be built — worse than a wrong propagation delay.  Subclasses
    :class:`PartError` so the CLI maps it to the library error code.
    """

    def __init__(self, cells: Sequence[str], message: str) -> None:
        self.cells = list(cells)
        super().__init__(", ".join(self.cells), message)


def unverified_multi_gate_parts(parts: Sequence[Part]) -> list[Part]:
    """Parts whose ``gates_per_pkg > 1`` rests on unverified electrical data.

    A multi-gate package claim is the sharp case of §10.1: it determines package
    count and die-sharing, so a wrong one yields an unbuildable netlist.  A
    single-gate claim (``gates_per_pkg == 1``) is still a placeholder but is
    surfaced (marked) rather than gated — its failure mode is a wrong count, not
    a physically impossible netlist.
    """
    return [p for p in parts if p.gates_per_pkg > 1 and not p.is_verified]


def unverified_placeholder_cells(parts: Sequence[Part]) -> list[str]:
    """Sorted cell names whose electrical values are placeholders (for `doctor`)."""
    return sorted({p.cell for p in parts if not p.is_verified})


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


# ---------------------------------------------------------------------------
# Canonical CSV serialisation (§10.4: byte-deterministic round-tripping)
# ---------------------------------------------------------------------------


def part_to_row(part: Part) -> list[str]:
    """Return ``part`` as a CSV row in ``REQUIRED_COLUMNS`` order."""
    return [
        part.cell,
        part.tier,
        part.family,
        part.part_suffix,
        ";".join(f"{e.part_number}:{e.mfr}" for e in part.equivalents),
        part.function or "",
        str(part.inputs),
        str(part.gates_per_pkg),
        part.package,
        ";".join(part.mfrs),
        _fmt_float(part.vcc_min),
        _fmt_float(part.vcc_max),
        _fmt_float(part.area),
        _fmt_optional_float(part.tpd_ns),
        _fmt_optional_float(part.iq_ua),
    ]


def part_to_dict(part: Part) -> dict:
    """Return ``part`` as a canonical mapping (for the ``.gpk`` library document).

    ``equivalents`` and ``mfrs`` are kept as their ``;``-joined CSV form, and
    empty optional fields are ``None`` so the YAML is compact and round-trips.
    """
    return {
        "cell": part.cell,
        "tier": part.tier,
        "family": part.family,
        "part_suffix": part.part_suffix,
        "equivalents": ";".join(f"{e.part_number}:{e.mfr}" for e in part.equivalents) or None,
        "function": part.function,
        "inputs": part.inputs,
        "gates_per_pkg": part.gates_per_pkg,
        "package": part.package,
        "mfrs": ";".join(part.mfrs) or None,
        "vcc_min": part.vcc_min,
        "vcc_max": part.vcc_max,
        "area": part.area,
        "tpd_ns": part.tpd_ns,
        "iq_ua": part.iq_ua,
    }


def dict_to_row(d: Mapping[str, object]) -> list[str]:
    """Return a canonical mapping (from a ``.gpk`` library document) as a CSV row."""
    return [
        str(d["cell"]),
        str(d["tier"]),
        str(d["family"]),
        str(d["part_suffix"]),
        _str_or_empty(d.get("equivalents")),
        _str_or_empty(d.get("function")),
        str(d["inputs"]),
        str(d["gates_per_pkg"]),
        str(d["package"]),
        _str_or_empty(d.get("mfrs")),
        _fmt_float(d["vcc_min"]),
        _fmt_float(d["vcc_max"]),
        _fmt_float(d["area"]),
        _fmt_optional_float(d.get("tpd_ns")),
        _fmt_optional_float(d.get("iq_ua")),
    ]


def rows_to_csv(rows: Sequence[Sequence[str]]) -> str:
    """Canonical ``parts.csv`` text: header + ``rows``, minimal quoting."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(REQUIRED_COLUMNS)
    for row in rows:
        writer.writerow(list(row))
    return buf.getvalue()


def parts_to_csv(parts: Sequence[Part]) -> str:
    """Canonical ``parts.csv`` text for ``parts``."""
    return rows_to_csv([part_to_row(p) for p in parts])


def _fmt_float(v: object) -> str:
    if isinstance(v, bool):
        v = 1.0 if v else 0.0
    return repr(float(v))


def _fmt_optional_float(v: object) -> str:
    if v is None or v == "":
        return ""
    return _fmt_float(v)


def _str_or_empty(v: object) -> str:
    return "" if v is None else str(v)
