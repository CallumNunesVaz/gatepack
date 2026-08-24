"""Scaffolding a new project (§18.1).

The desktop application could open designs but never create one: there was no
*New Project* command, and opening a directory without a ``design.yaml`` is
refused, so every original design had to start outside the GUI.  Closing that
gap is what this module is for.

It lives in the core rather than in the application on purpose.  "What a valid
starting design looks like" and "which parts library it ships with" are core
knowledge, and the application is strictly a view over artefacts the CLI
produces -- if the template lived in the main process, the CLI would have no
way to make the same project and the two would drift.

The seeded library
------------------
``libraries/74aup.csv`` is deliberately *not* bundled into the frozen core: it
is repo fixture data, and the packaged application opens projects that carry
their own ``parts.csv`` (see ``scripts/bundle_core.py``).  So a new project
cannot copy it there.  What *is* bundled is ``examples/``, and ten of those
examples carry a ``parts.csv`` byte-identical to the shipped library.  The
template therefore seeds from the widest bundled example library, which gives
one code path that behaves identically from source and when frozen, rather than
a source-only path that quietly degrades in the installed application.

``test_scaffold.py`` pins that choice to ``libraries/74aup.csv`` in a source
checkout, so the day someone trims every example's library the drift is a test
failure rather than a narrower new project nobody notices.
"""

from __future__ import annotations

import re
from pathlib import Path

from gatepack.examples import examples_root

#: Header comment + spec.  Written with the same idioms as the bundled examples
#: (``state == NAME`` output logic, exhaustive transitions per state) so the
#: first thing a user edits reads like the examples they learn from.
_TEMPLATE = '''\
# ---------------------------------------------------------------------------
# {name} — a new gatepack design.
#
# This is a starting point, not a finished machine: two states and one input,
# small enough to verify and build immediately so you can confirm the toolchain
# works before you change anything.
#
# To make it yours:
#
#   states / transitions  add states to `states`, then give every state a
#                         transition for every input combination — an
#                         unreachable or uncovered state is a diagnostic, not a
#                         silent gap
#   inputs                `sync: true` inserts a two-flop synchroniser (§9.3);
#                         use it for anything not already on this clock
#   output_logic          `state == NAME` for a Moore output, or an expression
#                         over the inputs for a Mealy one
#
# Every electrical value comes from `parts.csv` beside this file, and every row
# there carries its own datasheet citation or is marked a placeholder. Nothing
# in this project invents one.
# ---------------------------------------------------------------------------
name: {name}
timing_model: synchronous

clock: {{signal: clk, freq_hz: 1000, source: OSC}}

reset:
  signal: rst_n
  active: low
  source: SUPERVISOR

encoding: one_hot

inputs:
  # Not already on this clock, so it gets a synchroniser (§9.3).
  - {{name: go, sync: true}}

outputs:
  - {{name: active}}

states: [IDLE, RUN]
initial: IDLE

transitions:
  # Every state covers every input value: no gaps, no implicit self-loops.
  - {{from: IDLE, to: RUN,  when: "go"}}
  - {{from: IDLE, to: IDLE, when: "!go"}}
  - {{from: RUN,  to: RUN,  when: "go"}}
  - {{from: RUN,  to: IDLE, when: "!go"}}

output_logic:
  active: "state == RUN"
'''


class ScaffoldError(Exception):
    """Raised when a new project cannot be created where it was asked for."""


def design_name_from(directory: Path | str) -> str:
    """A valid design name derived from the directory it will live in.

    Directory names are chosen by humans in a file dialog and can hold spaces,
    dashes and worse.  The design name is an identifier that reaches generated
    Verilog as a module name, so it is sanitised here rather than rejected: a
    user who types "My First Board" should get a working project, not an error
    about identifier syntax.
    """
    stem = Path(directory).name
    cleaned = re.sub(r"[^0-9A-Za-z_]+", "_", stem).strip("_").lower()
    if not cleaned or cleaned[0].isdigit():
        cleaned = f"design_{cleaned}" if cleaned else "design"
    return cleaned


def _widest_bundled_library() -> Path:
    """The bundled example ``parts.csv`` with the most part rows.

    Deterministic (ties break on the example's name) so two runs of
    ``project new`` seed byte-identical libraries.
    """
    root = examples_root()
    candidates: list[tuple[int, str, Path]] = []
    if root.is_dir():
        for entry in sorted(root.iterdir()):
            csv = entry / "parts.csv"
            if csv.is_file():
                rows = sum(1 for line in csv.read_text().splitlines() if line.strip())
                candidates.append((rows, entry.name, csv))
    if not candidates:
        raise ScaffoldError(
            "no bundled example carries a parts.csv, so a new project cannot be "
            "seeded with a parts library; this build is missing its examples/ data"
        )
    candidates.sort(key=lambda c: (-c[0], c[1]))
    return candidates[0][2]


def new_project(directory: Path | str, name: str | None = None) -> list[Path]:
    """Write ``design.yaml`` and ``parts.csv`` into ``directory``.

    The directory is created when absent.  An existing ``design.yaml`` is never
    overwritten -- scaffolding onto a real project would destroy work, and the
    caller (a File > New in a GUI) cannot always tell that the directory the
    user picked already holds a design.
    """
    target = Path(directory)
    design = target / "design.yaml"
    if design.exists():
        raise ScaffoldError(
            f"{design} already exists: `project new` will not overwrite a design. "
            "Open the directory instead, or choose an empty one."
        )

    library = _widest_bundled_library()
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ScaffoldError(f"cannot create {target}: {exc}") from exc

    written: list[Path] = []
    design.write_text(_TEMPLATE.format(name=name or design_name_from(target)))
    written.append(design)

    parts = target / "parts.csv"
    if not parts.exists():
        parts.write_text(library.read_text())
        written.append(parts)
    return written


__all__ = ["ScaffoldError", "design_name_from", "new_project"]
