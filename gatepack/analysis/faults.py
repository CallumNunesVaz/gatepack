"""C7 single stuck-at fault analysis (§13.2).

Enumerates and collapses the single stuck-at fault list over the *resolved*
mapped netlist, then classifies each collapsed fault by simulating it against
the design's vector set.  The four words are used precisely and are **not**
interchangeable:

* **detected** — at least one applied vector makes a primary output (or a
  flip-flop ``D`` input, see the sequential note below) differ from the
  fault-free machine.
* **undetected** — no applied vector detects it, but the vector space was
  *not* exhausted (too large), so a test may exist outside the applied set.
  The fault's testability is *unknown*, not proven absent.
* **redundant** — no test can exist.  Proven only when the vector space was
  exhausted: the stuck value never changes any output for any input, i.e. the
  net sits in redundant logic (typically an unobservable net).  A redundant
  fault is a *design* finding (dead logic), distinct from a missing test.
* **untestable** — no test exists, but for a reason other than redundant
  logic: a stuck-at on a clock or asynchronous set/reset net, which the
  single-time-frame vector model cannot exercise through the data path.  A
  test-access finding, not a redundancy finding.

Collapsing is reported as **two** counts because a coverage figure quoted
against a collapsed list is not comparable to one quoted against the full
list:

* ``uncollapsed`` — every net and every G/F-cell pin is a fault site (2 faults
  each), counted *before* any collapsing.  A pin fault and the fault on the net
  it attaches to are therefore counted separately, so this deliberately
  over-counts relative to the textbook ``2 * lines`` figure; it is the literal
  "nets and cell pins" enumeration requested.
* ``collapsed`` — after node-level equivalence, then gate-level equivalence and
  dominance over each combinational gate's boolean function, with fanout
  handled correctly: a net that fans out to two or more combinational gates is
  a *stem* plus one *branch* per sink, and gate collapsing is applied to the
  branch lines, never to a fanout stem (the checkpoint rule).  This is the
  figure to quote for coverage.

Sequential designs are analysed by the **combinational-cut model**: every
flip-flop ``Q`` is treated as a pseudo-primary-input and every ``D`` as a
pseudo-primary-output, so the vector space is ``(data input vectors) x
(flip-flop states)``.  All ``2**k`` flip-flop states are enumerated, which
over-approximates reachability (illegal one-hot states are included), so the
detected count is an *upper bound*, not an exact sequential coverage figure;
the note says so.  Faults on clock / async set / async reset nets are
``untestable`` rather than simulated.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from gatepack.liberty import boolean
from gatepack.netlist import MappedCell, MappedNetlist

# Largest (input x flip-flop-state) vector space enumerated exhaustively.  Above
# this, a deterministic *prefix* of the space is applied and ``exhaustive`` is
# False, so ``undetected`` means "unknown against a partial set" — never a
# coverage figure (§21.4 [R4-18]: no random vectors with a coverage figure).
VECTOR_CAP = 1 << 16

# Logic-rail constants.  Only "0"/"1" — a net *named* "x" or "z" is a real net
# (a legal Verilog identifier, e.g. a design input literally called "x"), not a
# don't-care constant; post-synthesis ``write_json`` output contains only the
# "0"/"1" rails.
_CONSTANTS = frozenset({"0", "1"})

_NOTE = (
    "single stuck-at analysis over the combinational cut (flop Q as "
    "pseudo-inputs, D as pseudo-outputs); detected is an upper bound because "
    "all 2**k flop states are enumerated, not just reachable ones"
)


@dataclass(frozen=True)
class Fault:
    """One stuck-at fault site.  ``cell``/``pin`` empty means a net stem fault;
    non-empty means a fanout *branch* fault at that sink input pin."""

    net: str
    stuck: int  # 0 | 1
    cell: str = ""
    pin: str = ""

    @property
    def is_branch(self) -> bool:
        return bool(self.cell)


@dataclass(frozen=True)
class FaultReport:
    uncollapsed: int
    collapsed: int
    detected: int
    undetected: int
    redundant: int
    untestable: int
    exhaustive: bool
    vectors_applied: int
    vectors_total: int
    note: str

    def to_wire(self) -> dict:
        return {
            "detected": self.detected,
            "undetected": self.undetected,
            "redundant": self.redundant,
            "untestable": self.untestable,
        }


# ---------------------------------------------------------------------------
# Netlist helpers
# ---------------------------------------------------------------------------


def _non_constant_nets(netlist: MappedNetlist) -> set[str]:
    nets: set[str] = set(netlist.inputs) | set(netlist.outputs)
    for c in netlist.cells:
        for net in c.connections.values():
            if net not in _CONSTANTS:
                nets.add(net)
    return nets


def _output_net(cell: MappedCell) -> str | None:
    for pin in cell.output_pins:
        net = cell.connections.get(pin)
        if net is not None:
            return net
    return None


def _comb_cells(netlist: MappedNetlist) -> list[MappedCell]:
    return [
        c
        for c in netlist.cells
        if c.tier == "G" and c.part is not None and c.part.function
    ]


# ---------------------------------------------------------------------------
# Enumeration and collapsing
# ---------------------------------------------------------------------------


def enumerate_faults(netlist: MappedNetlist) -> tuple[int, list[Fault]]:
    """Return ``(uncollapsed_count, collapsed_faults)``.

    ``uncollapsed_count`` counts every net and every G/F-cell pin (2 faults
    each) before collapsing.  ``collapsed_faults`` is the branch-aware collapsed
    list (node equivalence, then gate equivalence/dominance at branches).
    """
    nets = sorted(_non_constant_nets(netlist))

    uncollapsed = 2 * len(nets)
    for c in netlist.cells:
        if c.tier in ("G", "F"):
            uncollapsed += 2 * len(set(c.input_pins) | set(c.output_pins))

    collapsed = _collapsed_lines(netlist, nets)
    return uncollapsed, sorted(collapsed, key=lambda f: (f.net, f.cell, f.pin, f.stuck))


def _collapsed_lines(netlist: MappedNetlist, nets: set[str]) -> set[Fault]:
    comb = _comb_cells(netlist)

    # Fanout to combinational gates only (sequential pins are treated at the net
    # level; see the module docstring).
    g_fanout: dict[str, list[tuple[str, str]]] = {}
    for c in comb:
        for pin in c.input_pins:
            net = c.connections.get(pin)
            if net is not None and net not in _CONSTANTS:
                g_fanout.setdefault(net, []).append((c.name, pin))

    lines = {Fault(n, v) for n in nets for v in (0, 1)}
    for net, sinks in g_fanout.items():
        if len(sinks) >= 2:
            for cell_name, pin in sinks:
                lines.add(Fault(net, 0, cell_name, pin))
                lines.add(Fault(net, 1, cell_name, pin))

    for c in comb:
        func = c.part.function
        n = c.part.inputs
        pins = boolean.pin_names(n)
        out_net = _output_net(c)
        if out_net is None:
            continue

        input_lines: list[tuple[str, Fault | None]] = []
        for pin in pins:
            net = c.connections.get(pin)
            if net is None or net in _CONSTANTS:
                input_lines.append((pin, None))
                continue
            if len(g_fanout.get(net, [])) >= 2:
                input_lines.append((pin, Fault(net, 0, c.name, pin)))
            else:
                input_lines.append((pin, Fault(net, 0)))

        # Local detection test sets (as assignment tuples) per input line and
        # per output value.
        pin_tests: dict[int, dict[int, set[tuple[bool, ...]]]] = {}
        for i, (pin, line) in enumerate(input_lines):
            if line is None:
                continue
            pin_tests[i] = {
                v: _pin_test_set(func, n, i, v) for v in (0, 1)
            }
        out_tests = {v: _output_test_set(func, n, v) for v in (0, 1)}

        # Equivalence: drop an input-line fault whose test set equals the output
        # fault's, keeping the output representative.
        for i, (pin, line) in enumerate(input_lines):
            if line is None:
                continue
            for v in (0, 1):
                for out_v in (0, 1):
                    if pin_tests[i][v] == out_tests[out_v]:
                        lines.discard(Fault(line.net, v, line.cell, line.pin))

        # Dominance: drop the output-line fault if its test set contains some
        # surviving input-line fault's test set (output dominates input).
        surviving_tests: list[set[tuple[bool, ...]]] = []
        for i, (pin, line) in enumerate(input_lines):
            if line is None:
                continue
            for v in (0, 1):
                if Fault(line.net, v, line.cell, line.pin) in lines:
                    surviving_tests.append(pin_tests[i][v])
        for out_v in (0, 1):
            if any(tset <= out_tests[out_v] for tset in surviving_tests):
                lines.discard(Fault(out_net, out_v))

    return lines


def _pin_test_set(func: str, inputs: int, pin_index: int, stuck: int) -> set[tuple[bool, ...]]:
    """Local assignments that detect input pin ``pin_index`` stuck-at ``stuck``."""
    pins = boolean.pin_names(inputs)
    tests: set[tuple[bool, ...]] = set()
    for code in range(1 << inputs):
        assignment = [bool(code & (1 << (inputs - 1 - i))) for i in range(inputs)]
        if assignment[pin_index] == bool(stuck):
            continue
        good = {pins[i]: assignment[i] for i in range(inputs)}
        faulty = dict(good)
        faulty[pins[pin_index]] = bool(stuck)
        if boolean.evaluate(func, inputs, good) != boolean.evaluate(func, inputs, faulty):
            tests.add(tuple(assignment))
    return tests


def _output_test_set(func: str, inputs: int, stuck: int) -> set[tuple[bool, ...]]:
    """Local assignments that detect the output stuck-at ``stuck``."""
    pins = boolean.pin_names(inputs)
    tests: set[tuple[bool, ...]] = set()
    for code in range(1 << inputs):
        assignment = {pins[i]: bool(code & (1 << (inputs - 1 - i))) for i in range(inputs)}
        if boolean.evaluate(func, inputs, assignment) != bool(stuck):
            tests.add(tuple(assignment.values()))
    return tests


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _SimModel:
    comb_order: tuple[MappedCell, ...]
    flop_q: tuple[str, ...]
    flop_d: tuple[str, ...]
    control_nets: frozenset[str]
    data_inputs: tuple[str, ...]


def _build_model(netlist: MappedNetlist, compiled) -> _SimModel:
    comb = _comb_cells(netlist)
    flops = [c for c in netlist.cells if c.tier == "F"]

    flop_q: list[str] = []
    flop_d: list[str] = []
    control: set[str] = set()
    for c in flops:
        q = _output_net(c)
        if q is not None:
            flop_q.append(q)
        for pin in ("D", "CK", "RST_N", "SET_N"):
            net = c.connections.get(pin)
            if net is None:
                continue
            if pin == "D":
                flop_d.append(net)
            else:
                control.add(net)

    if compiled is not None:
        data_inputs = tuple(n for n in compiled.input_names if n in netlist.inputs)
    else:
        data_inputs = tuple(netlist.inputs)

    return _SimModel(
        comb_order=tuple(_comb_topo_order(comb)),
        flop_q=tuple(sorted(set(flop_q))),
        flop_d=tuple(sorted(set(flop_d))),
        control_nets=frozenset(control),
        data_inputs=data_inputs,
    )


def _comb_topo_order(comb: Sequence[MappedCell]) -> list[MappedCell]:
    by_name = {c.name: c for c in comb}
    driver: dict[str, str] = {}
    for c in comb:
        out = _output_net(c)
        if out is not None:
            driver.setdefault(out, c.name)
    indegree = {c.name: 0 for c in comb}
    dependents: dict[str, list[str]] = {c.name: [] for c in comb}
    for c in comb:
        for pin in c.input_pins:
            net = c.connections.get(pin)
            dep = driver.get(net) if net is not None else None
            if dep is not None and dep != c.name:
                indegree[c.name] += 1
                dependents[dep].append(c.name)
    ready = sorted((c for c in comb if indegree[c.name] == 0), key=lambda c: c.name)
    order: list[MappedCell] = []
    seen: set[str] = set()
    while ready:
        nxt = ready.pop(0)
        order.append(nxt)
        seen.add(nxt.name)
        for dep in sorted(dependents[nxt.name]):
            indegree[dep] -= 1
            if indegree[dep] == 0:
                ready.append(by_name[dep])
                ready.sort(key=lambda c: c.name)
    order.extend(sorted((c for c in comb if c.name not in seen), key=lambda c: c.name))
    return order


def _input_vectors(names: Sequence[str]) -> Iterable[dict[str, bool]]:
    n = len(names)
    for code in range(1 << n):
        yield {names[i]: bool(code & (1 << (n - 1 - i))) for i in range(n)}


def _flop_vectors(names: Sequence[str]) -> Iterable[dict[str, bool]]:
    k = len(names)
    for code in range(1 << k):
        yield {names[i]: bool(code & (1 << (k - 1 - i))) for i in range(k)}


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def analyze_faults(
    netlist: MappedNetlist,
    compiled=None,
    *,
    vector_cap: int = VECTOR_CAP,
) -> FaultReport:
    """Enumerate, collapse and classify single stuck-at faults.

    ``compiled`` supplies the design's data-input names (clock/reset are held,
    not enumerated); when ``None`` every primary input is treated as a data
    input — adequate for hand-written combinational netlists, approximate for
    sequential ones.  See the module docstring for the four classifications.
    """
    uncollapsed, collapsed = enumerate_faults(netlist)
    model = _build_model(netlist, compiled)

    data_inputs = model.data_inputs
    flop_q = model.flop_q
    total = (1 << len(data_inputs)) * (1 << len(flop_q))
    exhaustive = total <= vector_cap

    funcs = {
        c.name: boolean.parse_function(c.part.function, c.part.inputs)
        for c in model.comb_order
    }
    outputs = tuple(netlist.outputs)

    def evaluate(
        inputs: Mapping[str, bool],
        flop: Mapping[str, bool],
        fault: Fault | None,
    ) -> tuple[dict[str, bool], dict[str, bool]]:
        vals: dict[str, bool] = {"0": False, "1": True}
        for n, v in inputs.items():
            vals[n] = v
        for n, v in flop.items():
            vals[n] = v
        if fault is not None and not fault.is_branch and fault.net not in _CONSTANTS:
            vals[fault.net] = bool(fault.stuck)
        for c in model.comb_order:
            out_net = _output_net(c)
            if out_net is None or (fault is not None and not fault.is_branch and out_net == fault.net):
                continue
            assignment: dict[str, bool] = {}
            for pin in c.input_pins:
                net = c.connections.get(pin)
                if net is None:
                    continue
                if fault is not None and fault.is_branch and fault.cell == c.name and fault.pin == pin:
                    assignment[pin] = bool(fault.stuck)
                else:
                    assignment[pin] = vals.get(net, False)
            vals[out_net] = boolean.eval_function(funcs[c.name], assignment)
        return {n: vals.get(n, False) for n in outputs}, {n: vals.get(n, False) for n in model.flop_d}

    vectors: list[tuple[dict[str, bool], dict[str, bool]]] = []
    applied = 0
    for flop in _flop_vectors(flop_q):
        for inp in _input_vectors(data_inputs):
            if applied >= vector_cap:
                break
            vectors.append((inp, flop))
            applied += 1
        if applied >= vector_cap:
            break

    good = [evaluate(inp, flop, None) for inp, flop in vectors]

    detected: set[Fault] = set()
    for fault in collapsed:
        if fault.net in model.control_nets:
            continue
        for idx, (inp, flop) in enumerate(vectors):
            out_g, d_g = good[idx]
            out_f, d_f = evaluate(inp, flop, fault)
            if out_g != out_f or d_g != d_f:
                detected.add(fault)
                break

    counts = {"detected": 0, "undetected": 0, "redundant": 0, "untestable": 0}
    for fault in collapsed:
        if fault.net in model.control_nets:
            counts["untestable"] += 1
        elif fault in detected:
            counts["detected"] += 1
        elif exhaustive:
            counts["redundant"] += 1
        else:
            counts["undetected"] += 1

    return FaultReport(
        uncollapsed=uncollapsed,
        collapsed=len(collapsed),
        detected=counts["detected"],
        undetected=counts["undetected"],
        redundant=counts["redundant"],
        untestable=counts["untestable"],
        exhaustive=exhaustive,
        vectors_applied=applied,
        vectors_total=total,
        note=_NOTE,
    )
