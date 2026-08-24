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


def script_path(path: str) -> str:
    """A filesystem path, safe to interpolate into a Yosys script.

    Yosys splits script command arguments on whitespace, so a path containing a
    space silently becomes two arguments: a project at ``/home/me/My Board``
    produced ``Can't open input file '/home/me/My'`` and a verification that
    reported *failed* for a reason that had nothing to do with the design. That
    is not exotic -- it is the default shape of a directory on macOS and
    Windows, and a GUI's New Project dialog invites exactly such names.

    Quoting is conditional so a path that needs none is emitted unchanged: §5.5
    requires two clean builds to produce a byte-identical ``yosys.ys``, and
    every existing build uses whitespace-free relative paths whose scripts must
    not change.

    A path containing a double quote is refused rather than escaped. Yosys has
    no portable escape inside a quoted argument, so the alternative is emitting
    a script that is broken in a new way -- and a wrong answer that looks like a
    verification result is the one outcome this project will not produce.
    """
    if '"' in path:
        raise ValueError(
            f"path contains a double quote and cannot be embedded in a Yosys "
            f"script: {path!r}. Rename the directory or move the project."
        )
    return f'"{path}"' if any(c.isspace() for c in path) else path


def common_frontend(top: str, generated_v: str, premap_json: str) -> str:
    """Render the common front end for a specific build.

    ``top`` is the design's top module name; ``generated_v`` the C1 behavioural
    Verilog path; ``premap_json`` the pre-ABC provenance capture point (§15.1).
    """
    text = load_common_frontend()
    return (
        text.replace("__TOP__", top)
        .replace("__GENERATED_V__", script_path(generated_v))
        .replace("__PREMAP_JSON__", script_path(premap_json))
    )
