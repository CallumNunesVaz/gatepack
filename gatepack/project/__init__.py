"""The single-file project format (§10.4).

A whole project — specification, truth table and (optionally) its cell library —
lives in one plain multi-document YAML file (``.gpk``) or in the exploded
``design.yaml`` + ``truth_table.csv`` + ``parts.csv`` directory.  Neither form is
privileged; C1 asks this module for a loaded :class:`Project` and never cares
which it came from.

Public entry points:

* :func:`load_project` — a directory or a ``.gpk`` file -> :class:`Project`.
* :func:`bundle` — exploded directory -> canonical ``.gpk`` text.
* :func:`explode` — ``.gpk`` text -> :class:`Project` (in memory).
* :func:`gpk_text` — :class:`Project` -> canonical ``.gpk`` text.
* :func:`explode_to_dir` — ``.gpk`` text -> exploded files on disk.
"""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from gatepack.frontend import yaml_subset as yaml_mod
from gatepack.parts import (
    REQUIRED_COLUMNS,
    PartError,
    dict_to_row,
    load_parts,
    part_to_dict,
    parts_to_csv,
    rows_to_csv,
)
from gatepack.project import serialize

FORMAT_VERSION = 1
KINDS = ("design", "truth_table", "library")


class ProjectError(ValueError):
    """A project could not be read, or is not a valid ``.gpk``/exploded form.

    The message names the file, the (1-based) document index and the line where
    that information is known; ``document``/``line`` are ``None`` for file-level
    failures.
    """

    def __init__(
        self,
        filename: str,
        message: str,
        document: int | None = None,
        line: int | None = None,
    ) -> None:
        self.filename = filename
        self.document = document
        self.line = line
        location = filename
        if document is not None:
            location = f"{filename}: document {document}"
        if line is not None:
            location = f"{location}, line {line}"
        super().__init__(f"{location}: {message}")


@dataclass(frozen=True)
class DesignDocument:
    data: dict[str, Any]
    provenance: Mapping[str, int]
    #: The verbatim ``design.yaml`` text, when the document was read from a file
    #: or recovered from a ``.gpk``. ``None`` for a project constructed in
    #: memory, which then falls back to canonical serialisation (§10.4).
    source: str | None = None


@dataclass(frozen=True)
class TruthTableDocument:
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]


@dataclass(frozen=True)
class LibraryDocument:
    source: str
    sha256: str
    parts: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class Project:
    design: DesignDocument
    truth_table: TruthTableDocument | None = None
    library: LibraryDocument | None = None


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_project(path: str | Path) -> Project:
    """Load a project from an exploded directory or a ``.gpk`` file."""
    path = Path(path)
    if path.is_dir():
        return _load_exploded(path)
    return _load_gpk(path)


def _load_exploded(directory: Path) -> Project:
    design_path = directory / "design.yaml"
    if not design_path.exists():
        raise ProjectError(str(design_path), "project directory has no design.yaml")
    try:
        text = design_path.read_text()
    except OSError as exc:
        raise ProjectError(str(design_path), f"cannot read: {exc}") from exc
    try:
        node = yaml_mod.parse(text)
    except yaml_mod.ParseError as exc:
        raise ProjectError(str(design_path), str(exc), line=exc.line) from exc
    if not isinstance(node, yaml_mod.Mapping):
        raise ProjectError(str(design_path), "design.yaml must be a mapping", line=node.line)
    design = DesignDocument(
        data=yaml_mod.to_python(node),
        provenance=yaml_mod.provenance(node),
        source=text,
    )
    return Project(
        design=design,
        truth_table=_load_truth_table_csv(directory / "truth_table.csv"),
        library=_load_library_csv(directory / "parts.csv"),
    )


def _load_gpk(path: Path) -> Project:
    try:
        text = path.read_text()
    except OSError as exc:
        raise ProjectError(str(path), f"cannot read: {exc}") from exc
    return parse_gpk(text, source_name=path.name)


def _load_truth_table_csv(path: Path) -> TruthTableDocument | None:
    if not path.exists():
        return None
    with path.open(newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        return TruthTableDocument(columns=(), rows=())
    columns = tuple(rows[0])
    data_rows = tuple(tuple(_coerce_cell(cell) for cell in row) for row in rows[1:])
    return TruthTableDocument(columns=columns, rows=data_rows)


def _load_library_csv(path: Path) -> LibraryDocument | None:
    if not path.exists():
        return None
    parts = load_parts(path)
    canonical = parts_to_csv(parts)
    return LibraryDocument(
        source=path.name,
        sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        parts=tuple(part_to_dict(part) for part in parts),
    )


def _coerce_cell(cell: str) -> Any:
    try:
        return int(cell)
    except ValueError:
        return cell


def _design_source_from_stream(text: str) -> str | None:
    """Recover the verbatim ``design.yaml`` text carried by a ``.gpk`` stream.

    Only a ``.gpk`` produced by :func:`bundle` (or a re-bundle of one) embeds
    its source verbatim; for a hand-written file the design body is still
    recovered as-is, so re-bundling it is byte-faithful to *that* body.
    """
    for body in serialize.split_documents(text):
        if _document_kind(body) == "design":
            return serialize.design_source(body)
    return None


def _document_kind(body: str) -> str | None:
    """The ``kind`` header value of a raw document body, or ``None``."""
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("kind:"):
            return stripped[len("kind:"):].strip()
    return None


def parse_gpk(text: str, source_name: str = "<gpk>") -> Project:
    """Parse ``.gpk`` text into a :class:`Project`."""
    try:
        nodes = yaml_mod.parse_documents(text)
    except yaml_mod.ParseError as exc:
        raise ProjectError(source_name, str(exc), line=exc.line) from exc
    if not nodes:
        raise ProjectError(source_name, "no documents", line=1)

    design_source = _design_source_from_stream(text)

    design: DesignDocument | None = None
    truth_table: TruthTableDocument | None = None
    library: LibraryDocument | None = None
    for index, node in enumerate(nodes, start=1):
        kind, data, line, provenance = _parse_document(node, source_name, index)
        if kind == "design":
            if design is not None:
                raise ProjectError(source_name, "duplicate 'design' document", index, line)
            design = DesignDocument(data=data, provenance=provenance, source=design_source)
        elif kind == "truth_table":
            if truth_table is not None:
                raise ProjectError(source_name, "duplicate 'truth_table' document", index, line)
            truth_table = _build_truth_table(data, source_name, index, line, provenance)
        else:
            if library is not None:
                raise ProjectError(source_name, "duplicate 'library' document", index, line)
            library = _build_library(data, source_name, index, line, provenance)
    if design is None:
        raise ProjectError(source_name, "missing 'design' document", line=1)
    return Project(design=design, truth_table=truth_table, library=library)


def _parse_document(
    node: yaml_mod.Node, filename: str, index: int
) -> tuple[str, dict[str, Any], int, Mapping[str, int]]:
    if not isinstance(node, yaml_mod.Mapping):
        raise ProjectError(filename, "document must be a mapping", index, node.line)
    items = node.items
    if not items:
        raise ProjectError(filename, "empty document", index, node.line)

    first_key, first_value = items[0]
    if first_key != "gatepack":
        raise ProjectError(
            filename,
            "missing 'gatepack' version key (it must be the first key)",
            index,
            node.line,
        )
    version = yaml_mod.scalar_value(first_value)
    if version != FORMAT_VERSION:
        raise ProjectError(
            filename,
            f"unsupported gatepack version {version!r} (expected {FORMAT_VERSION})",
            index,
            first_value.line,
        )

    kind_item = next((it for it in items if it[0] == "kind"), None)
    if kind_item is None:
        raise ProjectError(filename, "missing 'kind' key", index, node.line)
    kind = yaml_mod.scalar_value(kind_item[1])
    if kind not in KINDS:
        raise ProjectError(
            filename,
            f"unknown kind {kind!r} (expected one of {', '.join(KINDS)})",
            index,
            kind_item[1].line,
        )

    data: dict[str, Any] = {}
    for key, value in items:
        if key in ("gatepack", "kind"):
            continue
        data[key] = yaml_mod.to_python(value)
    return kind, data, node.line, yaml_mod.provenance(node)


def _build_truth_table(
    data: dict[str, Any],
    filename: str,
    index: int,
    line: int,
    provenance: Mapping[str, int],
) -> TruthTableDocument:
    columns = data.get("columns")
    if not isinstance(columns, list) or not all(isinstance(c, str) for c in columns):
        raise ProjectError(
            filename, "'columns' must be a list of names", index, provenance.get("columns", line)
        )
    rows = data.get("rows", [])
    if not isinstance(rows, list):
        raise ProjectError(filename, "'rows' must be a list", index, provenance.get("rows", line))

    parsed: list[tuple[Any, ...]] = []
    for i, row in enumerate(rows):
        if not isinstance(row, list):
            raise ProjectError(
                filename, f"row {i} must be a list", index, provenance.get(f"rows[{i}]", line)
            )
        if len(row) != len(columns):
            raise ProjectError(
                filename,
                f"row {i} has {len(row)} value(s), expected {len(columns)}",
                index,
                provenance.get(f"rows[{i}]", line),
            )
        parsed.append(tuple(row))
    return TruthTableDocument(columns=tuple(columns), rows=tuple(parsed))


def _build_library(
    data: dict[str, Any],
    filename: str,
    index: int,
    line: int,
    provenance: Mapping[str, int],
) -> LibraryDocument:
    source = data.get("source")
    if not isinstance(source, str) or not source:
        raise ProjectError(
            filename, "'source' must be a non-empty filename", index, provenance.get("source", line)
        )
    sha256 = data.get("sha256")
    if not isinstance(sha256, str) or not sha256:
        raise ProjectError(
            filename, "'sha256' must be a non-empty string", index, provenance.get("sha256", line)
        )
    parts = data.get("parts", [])
    if not isinstance(parts, list):
        raise ProjectError(filename, "'parts' must be a list", index, provenance.get("parts", line))

    parsed: list[dict[str, Any]] = []
    for i, part in enumerate(parts):
        if not isinstance(part, dict):
            raise ProjectError(
                filename, f"part {i} must be a mapping", index, provenance.get(f"parts[{i}]", line)
            )
        missing = [c for c in REQUIRED_COLUMNS if c not in part]
        if missing:
            raise ProjectError(
                filename,
                f"part {i} is missing column(s): {missing}",
                index,
                provenance.get(f"parts[{i}]", line),
            )
        parsed.append(dict(part))
    return LibraryDocument(source=source, sha256=sha256, parts=tuple(parsed))


# ---------------------------------------------------------------------------
# Emitting
# ---------------------------------------------------------------------------


def gpk_text(project: Project) -> str:
    """Return the canonical ``.gpk`` text for ``project``."""
    documents: list[dict[str, Any]] = []
    if project.truth_table is not None:
        documents.append(
            serialize.document_dict(
                {
                    "columns": list(project.truth_table.columns),
                    "rows": [list(row) for row in project.truth_table.rows],
                },
                "truth_table",
            )
        )
    if project.library is not None:
        documents.append(
            serialize.document_dict(
                {
                    "source": project.library.source,
                    "sha256": project.library.sha256,
                    "parts": [dict(part) for part in project.library.parts],
                },
                "library",
            )
        )
    if project.design.source is not None:
        return serialize.dumps_documents_with_design_source(project.design.source, documents)
    return serialize.dumps_documents([serialize.document_dict(project.design.data, "design"), *documents])


def design_text(project: Project) -> str:
    """Return the exploded ``design.yaml`` text for ``project``.

    The verbatim source is preferred when the document was read from a file
    (§10.4 faithful source); canonical serialisation is the fallback for a
    project constructed in memory.
    """
    if project.design.source is not None:
        return project.design.source
    return serialize.dumps_mapping(project.design.data)


def truth_table_text(project: Project) -> str | None:
    """Return the canonical exploded ``truth_table.csv`` text, or ``None``."""
    if project.truth_table is None:
        return None
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(list(project.truth_table.columns))
    for row in project.truth_table.rows:
        writer.writerow([str(cell) for cell in row])
    return buf.getvalue()


def library_text(project: Project) -> str | None:
    """Return the canonical exploded ``parts.csv`` text, or ``None``."""
    if project.library is None:
        return None
    return rows_to_csv([dict_to_row(part) for part in project.library.parts])


def bundle(source_dir: str | Path) -> str:
    """Return the canonical ``.gpk`` text for the exploded project directory."""
    return gpk_text(load_project(source_dir))


def explode(gpk_text: str, source_name: str = "<gpk>") -> Project:
    """Parse ``.gpk`` text into a :class:`Project` (alias for :func:`parse_gpk`)."""
    return parse_gpk(gpk_text, source_name=source_name)


def explode_to_dir(gpk_text: str, target_dir: str | Path) -> list[Path]:
    """Write the exploded files for ``gpk_text``; return the written paths."""
    project = parse_gpk(gpk_text)
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    design_path = target_dir / "design.yaml"
    design_path.write_text(design_text(project))
    written.append(design_path)
    if project.truth_table is not None:
        path = target_dir / "truth_table.csv"
        path.write_text(truth_table_text(project) or "")
        written.append(path)
    if project.library is not None:
        path = target_dir / "parts.csv"
        path.write_text(library_text(project) or "")
        written.append(path)
    return written


# ---------------------------------------------------------------------------
# Library divergence (§10.4: "detectable rather than silent")
# ---------------------------------------------------------------------------


def library_sha256(csv_path: str | Path) -> str:
    """Return the canonical ``parts.csv`` sha256 (what a bundle would record)."""
    parts = load_parts(csv_path)
    return hashlib.sha256(parts_to_csv(parts).encode("utf-8")).hexdigest()


def library_divergence(project: Project, base_dir: str | Path) -> tuple[str, str]:
    """Compare an embedded library against its on-disk source.

    Returns ``(status, detail)`` where ``status`` is ``"none"`` (no embedded
    library), ``"match"``, ``"mismatch"`` or ``"missing"`` (source not on disk).
    """
    library = project.library
    if library is None:
        return ("none", "")
    source = Path(library.source)
    if not source.is_absolute():
        source = Path(base_dir) / source
    if not source.exists():
        return ("missing", f"embedded library source {library.source!r} not found on disk")
    try:
        on_disk = library_sha256(source)
    except PartError as exc:
        return ("missing", f"cannot hash on-disk library {library.source!r}: {exc}")
    if on_disk != library.sha256:
        return (
            "mismatch",
            f"embedded library {library.source!r} sha256 {library.sha256} "
            f"does not match on-disk {on_disk}",
        )
    return ("match", f"embedded library {library.source!r} sha256 matches on-disk")
