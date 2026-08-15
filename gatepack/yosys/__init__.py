"""Shared Yosys front-end script (§17, §C3, §C4).

The common front end is stored as a single ``.ys`` file so C3's synthesis script
and C4's future ``golden_prep`` reference *the same text* and cannot drift.
That sameness is what makes equivalence checking close later (§C4, R20).
"""

from __future__ import annotations

import importlib.resources

_RESOURCE = importlib.resources.files("gatepack.yosys") / "common_frontend.ys"


def load_common_frontend() -> str:
    """Return the raw common-front-end script text."""
    return _RESOURCE.read_text()


def common_frontend(top: str, generated_v: str, premap_json: str) -> str:
    """Render the common front end for a specific build.

    ``top`` is the design's top module name; ``generated_v`` the C1 behavioural
    Verilog path; ``premap_json`` the pre-ABC provenance capture point (§15.1).
    """
    text = load_common_frontend()
    return (
        text.replace("__TOP__", top)
        .replace("__GENERATED_V__", generated_v)
        .replace("__PREMAP_JSON__", premap_json)
    )
