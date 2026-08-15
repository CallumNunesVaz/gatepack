"""Bundled example projects (§18.1).

The application opens the showcase on first launch, but the GUI must not be the
only way to reach these — a user who has just installed the CLI should be able
to get a working project without cloning the repository.

Examples live in ``examples/`` as exploded directories. The showcase also ships
as a ``.gpk`` alongside its directory: §10.4's single-file form currently loses
comments and key order when it round-trips, and the showcase's comments are
half of what it teaches, so the directory is the authoritative copy until that
is fixed.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent / "examples"

#: The project opened on first launch when there is no prior session (§18.1).
SHOWCASE = "pelican"


class ExampleError(Exception):
    """Raised when a named example does not exist."""


@dataclass(frozen=True)
class Example:
    name: str
    path: Path
    summary: str
    is_showcase: bool


def _summary(directory: Path) -> str:
    """First non-empty comment line of ``design.yaml``, as a one-line summary."""
    design = directory / "design.yaml"
    if not design.exists():
        return ""
    for line in design.read_text().splitlines():
        text = line.strip()
        if text.startswith("#") and text.strip("# -").strip():
            return text.lstrip("# ").strip().rstrip(".")
    return ""


def examples_root() -> Path:
    return _ROOT


def list_examples() -> list[Example]:
    """Every bundled example, showcase first."""
    if not _ROOT.is_dir():
        return []
    found = [
        Example(
            name=entry.name,
            path=entry,
            summary=_summary(entry),
            is_showcase=entry.name == SHOWCASE,
        )
        for entry in sorted(_ROOT.iterdir())
        if entry.is_dir() and (entry / "design.yaml").exists()
    ]
    return sorted(found, key=lambda e: (not e.is_showcase, e.name))


def get_example(name: str) -> Example:
    for example in list_examples():
        if example.name == name:
            return example
    available = ", ".join(e.name for e in list_examples()) or "none"
    raise ExampleError(f"no bundled example named {name!r} (available: {available})")


def extract(name: str, target: str | Path) -> list[Path]:
    """Copy a bundled example into ``target``; return the written paths.

    Refuses to overwrite a non-empty directory: the caller is more likely to
    have mistyped a path than to want an example merged into existing work.
    """
    example = get_example(name)
    target = Path(target)
    if target.exists() and any(target.iterdir()):
        raise ExampleError(f"{target} is not empty; refusing to overwrite")
    target.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for source in sorted(example.path.iterdir()):
        if source.is_file():
            destination = target / source.name
            shutil.copyfile(source, destination)
            written.append(destination)
    return written


def showcase_path() -> Path | None:
    """The showcase project directory, or ``None`` if it is not bundled."""
    try:
        return get_example(SHOWCASE).path
    except ExampleError:
        return None


__all__ = [
    "Example",
    "ExampleError",
    "SHOWCASE",
    "examples_root",
    "extract",
    "get_example",
    "list_examples",
    "showcase_path",
]
