"""Stage 4 — hazard-free two-level cover (§7.3) and the ≤3-literal limit.

Constructs, for each output and each next-state bit, a sum-of-products cover that
meets the standard static-1 hazard condition and enforces the ≤3-literal product
term limit.  The cover is *not* minimised by Espresso: Espresso's heuristics
(and ``-Dso``) do not guarantee the adjacency condition, so the cover is built
from enumerated product terms and the covering problem is solved with z3.

The conditions, per function ``f`` over the variables ``(state bits, inputs)``:

* **ON coverage** — every minterm where ``f`` is 1 is covered by some selected
  term (so the function is realised correctly).
* **required cubes** — for every specified single-input transition where ``f``
  is 1 at both ends, at least one selected term is a sub-cube of the transition
  cube.  This is exactly what prevents a static-1 hazard (Nowick–Dill).
* **≤3 literals** — the G-cell inventory tops out at fan-in 3 and multi-level
  factoring of a hazard-free cover is not hazard-preserving, so a product term
  with more than three literals is *refused* (naming the term and the function),
  never decomposed.  This is §7.3's first unsolved problem converted into a
  stated limit with an honest refusal.

The static-0 and dynamic-hazard conditions are **not** enforced here; the
independent ternary check (stage 5a) is the safety net that catches any hazard
in the *mapped* netlist, including ones this two-level construction does not
explicitly rule out.  That division is deliberate: stage 4 produces a candidate,
stage 5 verifies it, and stage 4 never emits without stage 5 passing.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Mapping, Sequence

from gatepack.frontend.errors import AsyncRefused
from gatepack.frontend.model import CompiledDesign
from gatepack.synth.async_ import smt
from gatepack.synth.async_.assign import Assignment
from gatepack.synth.async_.flowtable import FlowTable

#: The maximum number of literals in any product term.  The shipped G-cells top
#: out at fan-in 3 (AND3/NAND3/NOR3), and factoring a hazard-free cover into
#: smaller gates is not hazard-preserving (§7.3), so a larger term is refused.
MAX_TERM_LITERALS = 3

_DONTCARE = -1


@dataclass(frozen=True)
class FunctionCover:
    """The selected product terms for one function (an output or a state bit)."""

    name: str                 # output name, or "next_<j>" for a state bit
    kind: str                 # "output" | "next"
    index: int                # state-bit index when kind == "next"
    cubes: tuple[tuple[int, ...], ...]  # each cube over (state bits, inputs)

    @property
    def max_literals(self) -> int:
        if not self.cubes:
            return 0
        return max(_literal_count(c) for c in self.cubes)


@dataclass(frozen=True)
class CoverResult:
    """All covers for a design, with the variable layout they were built over."""

    width: int
    input_names: tuple[str, ...]
    state_names: tuple[str, ...]
    covers: tuple[FunctionCover, ...]

    @property
    def variables(self) -> tuple[str, ...]:
        return self.state_names + self.input_names

    @property
    def max_literals(self) -> int:
        return max((c.max_literals for c in self.covers), default=0)


def build_covers(
    compiled: CompiledDesign,
    table: FlowTable,
    assignment: Assignment,
    runner,
    workdir: str = ".",
) -> CoverResult:
    """Compute the hazard-free covers for every output and next-state bit.

    Raises :class:`AsyncRefused` when a function needs a product term with more
    than :data:`MAX_TERM_LITERALS` literals (naming the term and the function),
    or when z3 is unavailable.
    """
    width = assignment.width
    state_names = tuple(f"s_{j}" for j in range(width))
    input_names = table.input_names
    var_count = width + len(input_names)

    functions: list[tuple[str, str, int]] = [
        (name, "output", 0) for name in table.output_names
    ] + [(f"next_{j}", "next", j) for j in range(width)]

    covers: list[FunctionCover] = []
    for name, kind, index in functions:
        truth = _function_truth(compiled, table, assignment, width, kind, index, name)
        cubes = _cover_function(
            truth,
            var_count,
            table,
            assignment,
            width,
            runner,
            workdir,
            name,
            state_names + input_names,
            compiled.design.name,
        )
        covers.append(FunctionCover(name=name, kind=kind, index=index, cubes=cubes))

    return CoverResult(
        width=width,
        input_names=input_names,
        state_names=state_names,
        covers=tuple(covers),
    )


def _function_truth(
    compiled: CompiledDesign,
    table: FlowTable,
    assignment: Assignment,
    width: int,
    kind: str,
    index: int,
    name: str,
) -> dict[tuple[int, int], bool]:
    """Map ``(state_index, combo_index) -> f(state, combo)`` for one function."""
    truth: dict[tuple[int, int], bool] = {}
    for si in range(len(table.states)):
        for ci in range(len(table.combos)):
            if kind == "output":
                value = _output_value(table, si, ci, name)
            else:
                nxt = table.next_state[si][ci]
                value = bool(assignment.bit(nxt, index))
            truth[(si, ci)] = value
    return truth


def _output_value(table: FlowTable, si: int, ci: int, name: str) -> bool:
    for n, v in table.outputs[si][ci]:
        if n == name:
            return v
    raise KeyError(name)


def _cover_function(
    truth: Mapping[tuple[int, int], bool],
    var_count: int,
    table: FlowTable,
    assignment: Assignment,
    width: int,
    runner,
    workdir: str,
    name: str,
    names: tuple[str, ...],
    design_name: str,
) -> tuple[tuple[int, ...], ...]:
    """Build the hazard-free cover for one function; refuse a >3-literal term."""
    on: set[tuple[int, ...]] = set()
    off: set[tuple[int, ...]] = set()
    for (si, ci), value in truth.items():
        minterm = _minterm(assignment, width, table.states[si], table.combos[ci])
        (on if value else off).add(minterm)

    if not on:
        return ()

    candidates = _candidate_implicants(var_count, on, off)
    required = _required_cubes(table, assignment, width, truth)

    selected = _solve_cover(candidates, on, required, runner, workdir, name)
    if selected is None:
        culprit = _find_unsatisfied(on, required, candidates)
        term = _name_culprit(culprit, off, names)
        raise AsyncRefused(
            f"asynchronous design {design_name!r} refused: function {name!r} "
            f"needs product term {term} with more than {MAX_TERM_LITERALS} "
            "literals; the G-cell inventory tops out at fan-in 3 and factoring "
            "a hazard-free cover is not hazard-preserving (§7.3)"
        )
    return tuple(candidates[i] for i in selected)


def _minterm(
    assignment: Assignment, width: int, state: str, combo: tuple[bool, ...]
) -> tuple[int, ...]:
    bits = tuple(assignment.bit(state, j) for j in range(width))
    return bits + tuple(1 if b else 0 for b in combo)


def _candidate_implicants(
    var_count: int,
    on: set[tuple[int, ...]],
    off: set[tuple[int, ...]],
) -> list[tuple[int, ...]]:
    """Every product term (cube) with ≤ MAX_TERM_LITERALS literals that covers
    some ON minterm and no OFF minterm."""
    candidates: list[tuple[int, ...]] = []
    for cube in _all_cubes(var_count):
        if not any(_covers(cube, m) for m in on):
            continue
        if any(_covers(cube, o) for o in off):
            continue
        candidates.append(cube)
    return candidates


def _all_cubes(var_count: int) -> list[tuple[int, ...]]:
    """All cubes with at most MAX_TERM_LITERALS fixed literals, in a canonical order."""
    cubes: list[tuple[int, ...]] = [tuple([_DONTCARE] * var_count)]
    for k in range(1, MAX_TERM_LITERALS + 1):
        for positions in itertools.combinations(range(var_count), k):
            for values in itertools.product((0, 1), repeat=k):
                cube = [_DONTCARE] * var_count
                for pos, val in zip(positions, values):
                    cube[pos] = val
                cubes.append(tuple(cube))
    return cubes


def _required_cubes(
    table: FlowTable,
    assignment: Assignment,
    width: int,
    truth: Mapping[tuple[int, int], bool],
) -> set[tuple[int, ...]]:
    """The transition cubes where the function is 1 at both ends of a single-input change."""
    required: set[tuple[int, ...]] = set()
    combo_index = {combo: ci for ci, combo in enumerate(table.combos)}
    for si, state in enumerate(table.states):
        for ci, combo in enumerate(table.combos):
            if not truth[(si, ci)]:
                continue
            for d in range(len(table.input_names)):
                flipped = _flip(combo, d)
                other = combo_index[flipped]
                if truth[(si, other)]:
                    bits = tuple(assignment.bit(state, j) for j in range(width))
                    cube = list(bits + tuple(1 if b else 0 for b in combo))
                    cube[width + d] = _DONTCARE
                    required.add(tuple(cube))
    return required


def _flip(combo: tuple[bool, ...], index: int) -> tuple[bool, ...]:
    out = list(combo)
    out[index] = not out[index]
    return tuple(out)


def _solve_cover(
    candidates: Sequence[tuple[int, ...]],
    on: set[tuple[int, ...]],
    required: set[tuple[int, ...]],
    runner,
    workdir: str,
    name: str,
) -> tuple[int, ...] | None:
    """Minimise the selected-term count by iterating a cardinality bound.

    Returns the indices of the selected candidates, or ``None`` when the union of
    all candidates cannot satisfy the constraints (a >3-literal term is needed).
    """
    if not on:
        return ()
    # Every ON minterm and required cube must be coverable by *some* ≤3-literal
    # candidate; otherwise the problem is unsatisfiable by construction and no
    # solver call is needed (and none may silently drop the constraint).
    if any(not any(_covers(c, m) for c in candidates) for m in on):
        return None
    if any(not any(_subcube(c, t) for c in candidates) for t in required):
        return None
    for k in range(1, len(candidates) + 1):
        script = _cover_script(candidates, on, required, k)
        try:
            result = smt.solve(script, runner, workdir, f"cover_{name}_k{k}")
        except smt.SolverError as exc:
            raise AsyncRefused(
                f"asynchronous cover selection failed: {exc}"
            ) from exc
        if result.sat:
            return tuple(
                i for i in range(len(candidates)) if result.values.get(f"x_{i}") == 1
            )
    return None


def _cover_script(
    candidates: Sequence[tuple[int, ...]],
    on: set[tuple[int, ...]],
    required: set[tuple[int, ...]],
    k: int,
) -> str:
    lines = [smt.script_header(logic="ALL")]
    for i in range(len(candidates)):
        lines.append(f"(declare-const x_{i} Bool)")
    for m in sorted(on):
        coverers = [i for i, c in enumerate(candidates) if _covers(c, m)]
        if coverers:
            lines.append(f"(assert (or {' '.join(f'x_{i}' for i in coverers)}))")
    for t in sorted(required):
        coverers = [i for i, c in enumerate(candidates) if _subcube(c, t)]
        if coverers:
            lines.append(f"(assert (or {' '.join(f'x_{i}' for i in coverers)}))")
    terms = " ".join(f"(ite x_{i} 1 0)" for i in range(len(candidates))) or "0"
    lines.append(f"(assert (<= (+ {terms}) {k}))")
    lines.append("(check-sat)")
    lines.append(f"(get-value ({' '.join(f'x_{i}' for i in range(len(candidates)))}))")
    return "\n".join(lines) + "\n"


def _find_unsatisfied(on, required, candidates):
    """The first requirement no ≤3-literal candidate can satisfy."""
    for m in sorted(on):
        if not any(_covers(c, m) for c in candidates):
            return ("minterm", m)
    for t in sorted(required):
        if not any(_subcube(c, t) for c in candidates):
            return ("required", t)
    return None


def _name_culprit(culprit, off, names) -> str:
    """A human-readable product term naming the >3-literal requirement."""
    if culprit is None:
        return "?"
    kind, cube = culprit
    if kind == "required":
        return _format_cube(cube, names)
    minterm = cube
    implicant = _minimal_implicant(minterm, off)
    return _format_cube(implicant, names)


def _minimal_implicant(minterm: tuple[int, ...], off) -> tuple[int, ...]:
    """A (greedy) prime implicant covering ``minterm``, for naming a refusal."""
    cube = list(minterm)
    for pos in range(len(cube)):
        candidate = list(cube)
        candidate[pos] = _DONTCARE
        if not any(_covers(candidate, o) for o in off):
            cube = candidate
    return tuple(cube)


def _format_cube(cube: tuple[int, ...], names: tuple[str, ...]) -> str:
    literals = [
        (f"!{names[i]}" if cube[i] == 0 else names[i])
        for i in range(len(cube))
        if cube[i] != _DONTCARE
    ]
    return " & ".join(literals) if literals else "1"


def _covers(cube: tuple[int, ...], minterm: tuple[int, ...]) -> bool:
    return all(c == _DONTCARE or c == m for c, m in zip(cube, minterm))


def _subcube(sub: tuple[int, ...], sup: tuple[int, ...]) -> bool:
    """True when ``sub`` fixes only literals already fixed in ``sup`` (sub ⊆ sup)."""
    return all(s == _DONTCARE or s == p for s, p in zip(sub, sup))


def _literal_count(cube: tuple[int, ...]) -> int:
    return sum(1 for c in cube if c != _DONTCARE)
