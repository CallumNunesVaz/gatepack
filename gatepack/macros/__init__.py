"""M-cell library (§9.4) — behavioural models + physical bindings.

The M-cell behavioural models live as ``.v`` files under
``gatepack/macros/models/`` and are the *same files* C4 uses for equivalence and
exhaustive simulation (§19 R25).  They are appended onto the C2-generated
``cells_sim.v`` by the build.
"""

from __future__ import annotations

import importlib.resources

from gatepack.macros.bindings import MCellBinding, get_binding
from gatepack.macros.specs import (
    MCellPort,
    MCellSpec,
    blackbox_module,
    get_spec,
    known_spec_cells,
    load_spec_models,
    spec_model,
)

_MODEL_DIR = importlib.resources.files("gatepack.macros") / "models"


def known_m_cells() -> tuple[str, ...]:
    """Every M-cell in the library (sorted).

    The specification model is the source of truth (§9.4 M8): a macro without an
    independent specification model cannot be verified, so a cell does not exist
    as an M-cell until it has one.  A physical binding is optional and separate.
    """
    return known_spec_cells()


class MacroLibraryError(RuntimeError):
    """The bundled M-cell library is structurally inconsistent (§9.4 M8)."""


def _model_file_cells() -> set[str]:
    """Cell names with an implementation ``.v`` model under ``models/``."""
    return {p.stem for p in _MODEL_DIR.glob("*.v")}


def validate_m_cell_library() -> None:
    """Fail when an M-cell lacks a specification model or an implementation model.

    §9.4 M8: a macro without an independent specification model cannot be
    verified, and a macro without an implementation model cannot be simulated or
    placed on the gate side of equivalence.  This is a *gate*, not a guard: it
    runs at library load (``load_models``/``load_spec_models``) so a dangling
    M-cell fails immediately rather than when someone happens to run
    equivalence.
    """
    specs = set(known_spec_cells())
    models = _model_file_cells()
    for cell in sorted(specs | models):
        if cell not in specs:
            raise MacroLibraryError(
                f"M-cell {cell!r} has an implementation model but no independent "
                "specification model in gatepack/macros/specs.py; a macro without "
                "a specification model cannot be verified (§9.4 M8)."
            )
        if cell not in models:
            raise MacroLibraryError(
                f"M-cell {cell!r} has a specification model but no implementation "
                f"model at gatepack/macros/models/{cell}.v."
            )


def model_files() -> list[str]:
    """Return the ``.v`` model file paths for every known M-cell (sorted)."""
    validate_m_cell_library()
    return [str(_MODEL_DIR / f"{cell}.v") for cell in known_m_cells()]


def load_models() -> str:
    """Concatenate every M-cell model into one Verilog text (for ``cells_sim.v``)."""
    validate_m_cell_library()
    chunks = [(_MODEL_DIR / f"{cell}.v").read_text() for cell in known_m_cells()]
    return "\n".join(chunks)


__all__ = [
    "MCellBinding",
    "MCellPort",
    "MCellSpec",
    "MacroLibraryError",
    "blackbox_module",
    "get_binding",
    "get_spec",
    "known_m_cells",
    "known_spec_cells",
    "load_models",
    "load_spec_models",
    "model_files",
    "spec_model",
    "validate_m_cell_library",
]
