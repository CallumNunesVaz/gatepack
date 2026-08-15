"""M6 — §11 properties discharged by SymbiYosys.

C1 emits SystemVerilog assertions and antecedent covers in ``properties.sv``
(see :mod:`gatepack.frontend.verilog`).  This module is the part that actually
*runs* them: it generates a ``.sby`` driver, invokes ``sby``, parses its output
into the four-way check status of ``app/shared/api.ts``, and extracts a
counterexample from the VCD witness.

Properties are checked against the **behavioural source, never the mapped
netlist** (§11): equivalence proves the implementation matches the spec,
properties prove the spec is sensible.  Checking them on the netlist would let
them pass vacuously on a degenerate result.

Guard against vacuity: every property's antecedent is emitted as a ``cover``
(``gp_cover_N``) alongside its assertion (``gp_assert_N``).  A property that
passes only because its antecedent is unreachable is reported as a *failure of
the cover*, never as a pass — the exact vacuous-pass failure mode R2/R18 exist
to prevent.

``sby`` is not on the host PATH; it lives in the ``gatepack-toolchain`` image
(``Dockerfile.probe``).  Both the ``.sby`` generation and the output parser are
pure functions over strings, unit-tested against fixtures in the **measured**
sby output format (docs/M6-FINDINGS.md §3–4), and the generated script has been
run against real sby: the traffic-light mutex proves and the property-violating
golden fails.  When ``sby`` is absent every property check is reported as
``not_run`` with ``skippedReason: "sby not found on PATH"`` — visibly, never
silently as a pass.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from gatepack.frontend.model import CompiledDesign
from gatepack.frontend.verilog import (
    property_assert_label,
    property_cover_label,
)
from gatepack.toolchain import sby_command
from gatepack.verify.base import (
    CheckResult,
    CheckStatus,
    Counterexample,
    VerifyConfig,
)

SBY_MISSING_REASON = "sby not found on PATH"

# §21.5: default k = max(2 * state count, 64).
def default_depth(state_count: int) -> int:
    return max(2 * state_count, 64)


@dataclass(frozen=True)
class PropertyTask:
    """One property role (assertion or antecedent cover) to discharge in sby."""

    name: str  # the design.yaml property name
    index: int  # position in design.properties
    kind: str  # invariant|mutex|reachability|liveness
    role: str  # "assert" | "cover"
    mode: str  # "prove" (k-induction) | "bmc" (bounded)
    depth: int
    label: str  # the SVA label emitted by C1 (gp_assert_N / gp_cover_N)


def property_tasks(compiled: CompiledDesign) -> list[PropertyTask]:
    """Enumerate the sby tasks for a compiled design's properties.

    * ``invariant`` / ``mutex``: one ``mode prove`` task for the assertion plus
      one ``mode cover`` task for the antecedent cover (the vacuity guard).
    * ``reachability`` / ``liveness``: one ``mode cover`` task for the target
      cover (bounded reachability; §21.5).

    ``mode cover`` (not ``mode bmc``) is used for every cover — measured
    (docs/M6-FINDINGS.md §4): ``mode cover`` reports the step at which the cover
    statement was reached.
    """
    state_count = len(compiled.state_order)
    depth = default_depth(state_count)
    tasks: list[PropertyTask] = []
    for index, prop in enumerate(compiled.design.properties):
        if prop.kind in ("invariant", "mutex"):
            tasks.append(
                PropertyTask(
                    name=prop.name,
                    index=index,
                    kind=prop.kind,
                    role="assert",
                    mode="prove",
                    depth=depth,
                    label=property_assert_label(index),
                )
            )
            tasks.append(
                PropertyTask(
                    name=prop.name,
                    index=index,
                    kind=prop.kind,
                    role="cover",
                    mode="cover",
                    depth=depth,
                    label=property_cover_label(index),
                )
            )
        else:  # reachability, liveness
            tasks.append(
                PropertyTask(
                    name=prop.name,
                    index=index,
                    kind=prop.kind,
                    role="cover",
                    mode="cover",
                    depth=depth,
                    label=property_cover_label(index),
                )
            )
    return tasks


def build_sby_file(
    top: str,
    generated_v: str,
    properties_sv: str,
    task: PropertyTask,
    engine: str = "smtbmc z3",
) -> str:
    """Emit a ``.sby`` file for one :class:`PropertyTask`.

    One task per file. sby's multi-task grammar would let several share a
    header, but every task here needs its own ``mode`` anyway, and the
    single-task form is the one measured to work against real sby
    (docs/M6-FINDINGS.md §3).
    """
    lines: list[str] = [
        "# Generated by gatepack (M6). One task per file: sby's multi-task",
        "# grammar buys nothing here and the single-task form is the one",
        "# measured to work (docs/M6-FINDINGS.md §3).",
        "",
        "[options]",
        f"mode {task.mode}",
        f"depth {task.depth}",
        "",
        "[engines]",
        engine,
        "",
        "[script]",
        # `properties.sv` is `include`d into the design module under GP_FORMAL,
        # so it is NOT read separately and the top is the design itself. A
        # wrapper module cannot see the design's signals: Yosys turns
        # `dut.<sig>` into a new undriven wire and the property then checks a
        # free variable connected to nothing (M6-FINDINGS §6).
        f"read_verilog -sv -formal -DGP_FORMAL {generated_v}",
        f"prep -top {top}",
        # The design uses async-assert/sync-de-assert reset (§9.3); smtbmc
        # cannot model an async reset, and without this the reset is simply
        # ignored and every property fails from a state that never resets.
        "async2sync",
        "",
        "[files]",
        generated_v,
        properties_sv,
    ]
    return "\n".join(lines) + "\n"

@dataclass(frozen=True)
class TaskResult:
    status: str  # "passed" | "bounded" | "failed" | "not_run"
    detail: str = ""
    bound: int | None = None


def parse_sby(stdout: str, tasks: Sequence[PropertyTask]) -> dict[str, TaskResult]:
    """Parse sby output into one :class:`TaskResult` per task label.

    The format follows the **measured** sby output (docs/M6-FINDINGS.md §3–4):

    * ``mode prove`` → ``passed`` only when both ``returned pass for basecase``
      and ``returned pass for induction`` appear.  Both ``mode prove`` and
      ``mode cover`` emit the literal string ``returned pass``, so the status is
      never inferred from a summary line alone — the mode the driver chose is the
      distinguishing information (M6-FINDINGS §3.1).
    * ``mode prove`` with basecase pass + induction fail → ``bounded``
      (k-induction did not close; BMC passed to ``depth``).
    * ``mode prove`` with basecase fail → ``failed`` (a real counterexample, or
      the missing-reset signature of M6-FINDINGS §2).
    * ``mode cover`` with ``Reached cover statement ... in step N`` → ``bounded``
      with ``bound = N``.
    * ``mode cover`` otherwise failing → ``failed`` (unreached cover — vacuity).
    * no status line → ``not_run``.
    """
    results: dict[str, TaskResult] = {}
    for task in tasks:
        chunk = _task_chunk(stdout, task.label)
        results[task.label] = _parse_task_chunk(chunk, task)
    return results


def _task_chunk(stdout: str, label: str) -> str:
    """The lines of ``stdout`` belonging to the sby task for ``label``.

    Real sby brackets the **task name**, which is the ``.sby`` file's stem —
    ``[properties_gp_assert_0]``, not ``[gp_assert_0]``. Matching on ``[label]``
    exactly finds nothing and every check silently degrades to ``not_run``,
    which is how this was found: hand-written fixtures used the bare label and
    the first real sby run parsed to four ``not_run``s.

    The bracketed name is therefore matched as a *containing* token. Lines that
    name the label directly (``Assert failed in mod: gp_assert_0``) also count,
    so a chunk is never empty when the task genuinely ran.
    """
    wanted: list[str] = []
    for line in stdout.splitlines():
        start = line.find("[")
        end = line.find("]", start + 1)
        if start != -1 and end != -1 and label in line[start + 1 : end]:
            wanted.append(line)
        elif f": {label}" in line:
            wanted.append(line)
    return "\n".join(wanted)


def _parse_task_chunk(chunk: str, task: PropertyTask) -> TaskResult:
    if not chunk.strip():
        return TaskResult(
            "not_run", f"no status line for task {task.label!r} in sby output"
        )
    if task.role == "assert":
        return _parse_prove(chunk, task)
    return _parse_cover(chunk, task)


def _parse_prove(chunk: str, task: PropertyTask) -> TaskResult:
    basecase = "returned pass for basecase" in chunk
    induction = "returned pass for induction" in chunk
    if basecase and induction:
        return TaskResult("passed")
    if induction and not basecase:
        # M6-FINDINGS §2: induction pass + basecase fail is the signature of a
        # missing reset assumption, not a bounded result.
        return TaskResult(
            "failed",
            "induction passed but the base case failed — a true invariant "
            "failing at step 1 usually means the reset assumption is missing "
            "(M6-FINDINGS §2)",
        )
    if basecase and not induction:
        # k-induction did not close; BMC passed to depth -> bounded, never passed.
        return TaskResult(
            "bounded",
            f"BMC passed to depth {task.depth}; induction did not close",
            bound=task.depth,
        )
    if "Assert failed" in chunk or "FAIL" in chunk:
        return TaskResult("failed", "assertion violated")
    return TaskResult("not_run", f"unrecognized sby output for {task.label!r}")


def _parse_cover(chunk: str, task: PropertyTask) -> TaskResult:
    reached = re.search(r"Reached cover statement at \S+ in step (\d+)", chunk)
    if reached:
        step = int(reached.group(1))
        return TaskResult(
            "bounded",
            f"cover reached in step {step} (M6-FINDINGS §4)",
            bound=step,
        )
    if "FAIL" in chunk or "DONE (FAIL" in chunk:
        return TaskResult("failed", "cover statement not reached")
    if "DONE (PASS" in chunk or "returned pass" in chunk:
        # A cover task that reported a pass without an explicit "Reached ... in
        # step N" line still means the antecedent is reachable (bounded).
        return TaskResult("bounded", "cover satisfied", bound=task.depth)
    return TaskResult("not_run", f"unrecognized sby output for {task.label!r}")


# ---------------------------------------------------------------------------
# VCD counterexample extraction
# ---------------------------------------------------------------------------

_VAR_RE = re.compile(r"\$var\s+\S+\s+\d+\s+(\S+)\s+(\S+)\s+\$end")
_SCALAR_RE = re.compile(r"^([01xz])(\S+)$")
_VECTOR_RE = re.compile(r"^[bB]([01xz]+)\s+(\S+)$")


def parse_vcd(text: str) -> list[dict[str, str]]:
    """Parse a VCD witness into a list of steps (one dict per timestamp).

    Each dict maps a signal name to ``'0'``/``'1'``/``'x'``.  Multi-bit vectors
    are stored as their bit string (a deviation from the single-bit contract that
    only arises for binary/gray state encodings; see BUILD-NOTES-M6).
    """
    id_to_name: dict[str, str] = {}
    for m in _VAR_RE.finditer(text):
        id_to_name[m.group(1)] = m.group(2)

    steps: list[dict[str, str]] = []
    current: dict[str, str] = {}
    seen_timestamp = False
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("$"):
            if s.startswith("$dumpvars"):
                seen_timestamp = True
            continue
        if s.startswith("#"):
            if seen_timestamp and current:
                steps.append(dict(current))
            seen_timestamp = True
            continue
        value, id_code = _parse_value(s)
        if id_code is None:
            continue
        name = id_to_name.get(id_code)
        if name is not None:
            current[name] = value
    if seen_timestamp and current:
        steps.append(dict(current))
    return steps


def _parse_value(s: str) -> tuple[str | None, str | None]:
    vector = _VECTOR_RE.match(s)
    if vector:
        bits = vector.group(1)
        return _bits_to_value(bits), vector.group(2)
    scalar = _SCALAR_RE.match(s)
    if scalar:
        return _scalar(scalar.group(1)), scalar.group(2)
    return None, None


def _scalar(c: str) -> str:
    return "x" if c in ("x", "z") else c


def _bits_to_value(bits: str) -> str:
    if len(bits) == 1:
        return _scalar(bits)
    return "".join(_scalar(b) for b in bits)


# ---------------------------------------------------------------------------
# Check assembly
# ---------------------------------------------------------------------------


def checks_from_sby(
    compiled: CompiledDesign,
    tasks: Sequence[PropertyTask],
    results: Mapping[str, TaskResult],
    counterexample: Counterexample | None = None,
) -> list[CheckResult]:
    """Fold per-task sby results into one :class:`CheckResult` per property.

    Vacuity is the load-bearing rule here: an ``invariant``/``mutex`` property
    whose antecedent cover fails (precondition unreachable) is reported as a
    failure, even when its assertion passed.
    """
    by_index: dict[int, list[PropertyTask]] = {}
    for task in tasks:
        by_index.setdefault(task.index, []).append(task)

    checks: list[CheckResult] = []
    for index, prop in enumerate(compiled.design.properties):
        props = by_index.get(index, [])
        check = _combine_property(compiled, index, prop, props, results)
        if (
            check.status is CheckStatus.FAILED
            and counterexample is not None
            and check.counterexample is None
        ):
            check = CheckResult(
                check.name,
                check.status,
                check.detail,
                check.bound,
                kind=check.kind,
                duration_ms=check.duration_ms,
                counterexample=counterexample,
            )
        checks.append(check)
    return checks


def _combine_property(
    compiled: CompiledDesign,
    index: int,
    prop,
    tasks: Sequence[PropertyTask],
    results: Mapping[str, TaskResult],
) -> CheckResult:
    name = f"property {prop.name}"
    assert_task = next((t for t in tasks if t.role == "assert"), None)
    cover_task = next((t for t in tasks if t.role == "cover"), None)

    if assert_task is not None:
        ar = results.get(assert_task.label)
        cr = results.get(cover_task.label) if cover_task is not None else None
        if ar is None:
            return CheckResult(name, CheckStatus.NOT_RUN, "sby not found on PATH", kind="property")
        if ar.status == "failed":
            return CheckResult(name, CheckStatus.FAILED, ar.detail, kind="property")
        if ar.status == "bounded":
            return CheckResult(
                name, CheckStatus.BOUNDED_PASS, ar.detail, ar.bound, kind="property"
            )
        if ar.status == "not_run":
            return CheckResult(name, CheckStatus.NOT_RUN, ar.detail, kind="property")
        # assertion passed — now the vacuity guard
        if cr is not None and cr.status == "failed":
            return CheckResult(
                name,
                CheckStatus.FAILED,
                "antecedent unreachable (vacuous pass — §11): the property holds "
                "only because its precondition never occurs",
                kind="property",
            )
        if cr is not None and cr.status == "not_run":
            return CheckResult(
                name,
                CheckStatus.NOT_RUN,
                "vacuity cover did not run; cannot confirm the antecedent is "
                "reachable",
                kind="property",
            )
        return CheckResult(name, CheckStatus.PASSED, kind="property")

    # reachability / liveness: a single cover task
    cover_task = tasks[0] if tasks else None
    if cover_task is None:
        return CheckResult(name, CheckStatus.NOT_RUN, "sby not found on PATH", kind="property")
    cr = results.get(cover_task.label)
    if cr is None:
        return CheckResult(name, CheckStatus.NOT_RUN, "sby not found on PATH", kind="property")
    if cr.status == "bounded":
        return CheckResult(
            name, CheckStatus.BOUNDED_PASS, cr.detail, cr.bound, kind="property"
        )
    if cr.status == "failed":
        return CheckResult(
            name,
            CheckStatus.FAILED,
            f"{cr.detail} (target not reachable within depth {cover_task.depth})",
            kind="property",
        )
    return CheckResult(name, CheckStatus.NOT_RUN, cr.detail, kind="property")


def run_properties(
    compiled: CompiledDesign, config: VerifyConfig, runner
) -> list[CheckResult]:
    """Run every property check for a compiled design.

    ``sby`` absence is a visible ``not_run`` state, never a silent pass.
    """
    tasks = property_tasks(compiled)
    if not tasks:
        return []
    if not runner.available("sby"):
        return [
            CheckResult(
                f"property {prop.name}",
                CheckStatus.NOT_RUN,
                SBY_MISSING_REASON,
                kind="property",
            )
            for prop in compiled.design.properties
        ]

    # One sby invocation per task: each needs its own `mode`, and the
    # single-task file is the form measured to work (M6-FINDINGS §3).
    base = Path(config.properties_sv)
    base.parent.mkdir(parents=True, exist_ok=True)
    results: dict[str, TaskResult] = {}
    combined_stdout: list[str] = []
    for task in tasks:
        sby_file = base.with_name(f"{base.stem}_{task.label}.sby")
        sby_file.write_text(
            build_sby_file(config.top, config.generated_v, config.properties_sv, task)
        )
        result = runner.run(sby_command(str(sby_file)), cwd=config.cwd)
        combined_stdout.append(result.stdout)
        results.update(parse_sby(result.stdout, [task]))
    stdout = "\n".join(combined_stdout)

    counterexample = None
    vcd_text = _locate_vcd(config, stdout)
    if vcd_text is not None:
        steps = parse_vcd(vcd_text)
        if steps:
            counterexample = Counterexample(
                steps=tuple(steps),
                pointers=_trace_pointers(compiled),
            )

    return checks_from_sby(compiled, tasks, results, counterexample)


def _locate_vcd(config: VerifyConfig, stdout: str) -> str | None:
    """Best-effort: find the VCD witness sby wrote and return its text.

    Unverified against real sby (sby is not installed).  Searches the sby output
    directory for ``*.vcd`` files.
    """
    for path in Path(config.cwd).glob("**/*.vcd"):
        try:
            return path.read_text()
        except OSError:
            continue
    return None


def _pointer(compiled: CompiledDesign, path: str) -> str | None:
    line = compiled.provenance.get(path)
    if line is None:
        return None
    return f"{compiled.source_name}:{line}:{path}"


def _trace_pointers(compiled: CompiledDesign) -> tuple[str, ...]:
    """Provenance pointers for the spec constructs implicated in a trace.

    Best-effort: the property list and the state machine are the two constructs
    a property counterexample implicates; the exact property/transition is not
    recovered from the VCD signal values here.
    """
    pointers = [p for p in (_pointer(compiled, "properties"), _pointer(compiled, "states")) if p]
    return tuple(pointers)


__all__ = [
    "PropertyTask",
    "TaskResult",
    "SBY_MISSING_REASON",
    "build_sby_file",
    "checks_from_sby",
    "default_depth",
    "parse_sby",
    "parse_vcd",
    "property_tasks",
    "run_properties",
]
