"""M-cell library (§9.4) — behavioural models + physical bindings.

The M-cell behavioural models live as ``.v`` files under
``gatepack/macros/models/`` and are the *same files* C4 uses for equivalence and
exhaustive simulation (§19 R25).  They are appended onto the C2-generated
``cells_sim.v`` by the build.
"""

from __future__ import annotations

import importlib.resources

from gatepack.macros.bindings import MCellBinding, get_binding, known_m_cells

_MODEL_DIR = importlib.resources.files("gatepack.macros") / "models"

# Every M-cell must have both a binding and a model file of the same name.
_M_CELLS = tuple(sorted(known_m_cells()))


def model_files() -> list[str]:
    """Return the ``.v`` model file paths for every known M-cell (sorted)."""
    return [str(_MODEL_DIR / f"{cell}.v") for cell in _M_CELLS]


def load_models() -> str:
    """Concatenate every M-cell model into one Verilog text (for ``cells_sim.v``)."""
    chunks = [(_MODEL_DIR / f"{cell}.v").read_text() for cell in _M_CELLS]
    return "\n".join(chunks)


__all__ = [
    "MCellBinding",
    "get_binding",
    "known_m_cells",
    "load_models",
    "model_files",
]
