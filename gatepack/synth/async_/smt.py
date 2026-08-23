"""SMT-LIB2 bridge — the one place gatepack shells out to ``z3``.

The asynchronous backend needs a solver for two problems (stage 3's
single-variable-change assignment and stage 4's cover selection).  ``z3`` ships
in the pinned toolchain as a *binary*, not as a Python module — the ``z3``
Python package is not a dependency and is not installed — so the backend talks
SMT-LIB2 over the injected runner (:class:`~gatepack.toolchain.ToolchainRunner`
or a test fake), exactly like Yosys/Icarus/sby are driven.  A missing ``z3`` is
reported, never substituted (§7.3: never fake a tool result).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol, Sequence


class SolverError(Exception):
    """The SMT solver is unavailable, failed, or returned an unparsable result."""


class _Runner(Protocol):
    def available(self, name: str) -> bool: ...

    def run(self, argv: Sequence[str], cwd: str, timeout: int = 600): ...


@dataclass(frozen=True)
class SmtResult:
    """The outcome of a ``check-sat``: satisfiability plus any model values."""

    sat: bool
    #: ``name -> integer`` decoded from the ``(get-value ...)`` model (bit-vectors
    #: are decoded MSB-first so ``#b101`` -> ``5``, i.e. bit 0 is the LSB).
    values: Mapping[str, int]


#: The seed passed to z3 so two runs of the same script return the same model.
#: The old ``random_seed`` spelling is rejected by z3 4.8.12; ``:smt.random_seed``
#: is the current parameter name and is what the pinned toolchain accepts.
RANDOM_SEED = 0


def script_header(logic: str = "QF_BV") -> str:
    """The fixed SMT-LIB2 preamble: models on, a fixed random seed, a logic.

    Stage 3 (bit-vector Hamming distance) uses ``QF_BV``; stage 4 (cover
    selection over Booleans with a cardinality bound) uses ``ALL`` because it
    mixes ``Bool`` variables with ``ite``/integer sums.
    """
    return "\n".join(
        [
            "(set-option :produce-models true)",
            f"(set-option :smt.random_seed {RANDOM_SEED})",
            f"(set-logic {logic})",
        ]
    )


def solve(script: str, runner: _Runner, workdir: str, name: str) -> SmtResult:
    """Write ``script`` to ``workdir/<name>.smt2`` and run ``z3 -smt2`` on it.

    The script path is passed relative to the invocation directory (``cwd="."``),
    matching the rest of the pipeline, so the SMT file is reproducible and never
    embeds an absolute path (§5.5).
    """
    directory = Path(workdir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.smt2"
    path.write_text(script)

    if not runner.available("z3"):
        raise SolverError(
            "z3 not found: the asynchronous backend needs an SMT solver for "
            "state assignment and cover selection; refusing rather than "
            "substituting a heuristic (§7.3)"
        )
    result = runner.run(["z3", "-smt2", str(path)], cwd=".")
    try:
        return parse_output(result.stdout)
    except SolverError as exc:
        detail = (result.stderr or result.stdout or "").strip()
        raise SolverError(f"{exc} ({detail})") from exc


def parse_output(stdout: str) -> SmtResult:
    """Parse z3's ``sat``/``unsat`` plus ``(get-value ...)`` model text.

    ``unsat`` wins over ``sat`` (a substring of ``unsat``), and an ``unsat``
    result may carry a trailing "model is not available" error from a stray
    ``(get-value ...)`` — that is expected and is treated as plain UNSAT.
    """
    lines = [line.strip() for line in (stdout or "").splitlines() if line.strip()]
    if not lines:
        raise SolverError("z3 produced no output")
    first = lines[0]
    if first == "unsat":
        return SmtResult(sat=False, values={})
    if first == "unknown":
        raise SolverError("z3 returned 'unknown' (unexpected for QF_BV)")
    if first != "sat":
        raise SolverError(f"unrecognized z3 output: {first!r}")
    return SmtResult(sat=True, values=parse_model(stdout))


def parse_model(text: str) -> dict[str, int]:
    """Decode a model (bit-vectors ``#b101``/``#x05`` and Booleans ``true``/``false``)
    into ``name -> int`` (Booleans become 0/1)."""
    values: dict[str, int] = {}
    pattern = re.compile(
        r"\(\s*([A-Za-z_][A-Za-z0-9_]*)\s+(#b[01]+|#x[0-9a-fA-F]+|true|false)\s*\)"
    )
    for match in pattern.finditer(text):
        name, raw = match.groups()
        values[name] = _decode(raw)
    return values


def _decode(raw: str) -> int:
    if raw.startswith("#b"):
        return int(raw[2:], 2)
    if raw.startswith("#x"):
        return int(raw[2:], 16)
    return 1 if raw == "true" else 0
