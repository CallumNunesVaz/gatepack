"""C7 SCOAP testability analysis (§13.1).

SCOAP (Sandia Controllability/Observability Analysis Program) over the *resolved*
mapped netlist.  The numbers are integer costs, not probabilities: a larger
controllability means the net is harder to set, a larger observability means it
is harder to observe.  Absolute values mean little — this module reports the
**outliers** (the delta table) and the nets that cannot be observed at all,
because those are the findings C12 renders as an overlay.

Scope and assumptions, stated up front because they change the numbers:

* **Combinational controllability** ``CC0``/``CC1`` is computed by the standard
  recurrences over each gate's boolean function.  Primary inputs have
  ``CC0 = CC1 = 1``; the constant rails ``"0"``/``"1"`` are ``0``/uncontrollable.
* **Sequential controllability** ``SC0``/``SC1`` for flip-flops is a *single-pass*
  recurrence (flop ``Q`` is treated as a pseudo-primary-input with ``CC0=CC1=1``
  during the combinational pass; ``SC(Q)`` is then derived from ``D`` plus the
  clock and async set/reset pins).  This is one iteration of the sequential SCOAP
  fixed point — see the note on feedback below.
* **Observability** ``CO`` propagates backwards from the primary outputs, which
  have ``CO = 0``.  A flop's ``D`` is observable through ``Q`` (``SO(D) =
  CO(Q) + clock + async-deassert cost``).  A net with no path to any primary
  output has ``observability = None`` (reported as the ``UNOBSERVABLE`` sentinel
  on the wire) and is listed in :attr:`ScoapReport.unobservable`.

Combinational loops: the design bans latches, so the combinational part is
acyclic **once flop ``Q`` outputs are cut** (a feedback path through a flop — the
one-hot set-via-feedback / ``dfflegalize`` mux-feedback — is a *sequential* loop,
broken by treating ``Q`` as a leaf, so it cannot recurse).  As a defence in
depth, any combinational cell left over after Kahn ordering (a genuine
combinational cycle) has its output marked ``None`` instead of recursing forever,
and observability is computed by a bounded min-relaxation fixed point that is
monotone under positive weights, so it cannot loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from gatepack.liberty import boolean
from gatepack.netlist import MappedCell, MappedNetlist

# Wire-level sentinel for "infinite" (uncontrollable / unobservable).  JSON has
# no infinity and ``api.ts`` types the SCOAP fields as ``number``, so a large
# finite sentinel is used and documented.  Any value >= UNOBSERVABLE means "not
# observable at any primary output" (or, for controllability, "not controllable").
UNOBSERVABLE = 1 << 30

# Number of "worst" nets reported in the delta table (§13.1).
DELTA_LIMIT = 10

# Safety cap on the observability fixed-point relaxation (positive weights make
# it converge; this is defence in depth against an unexpected cycle).
_MAX_OBSERVABILITY_PASSES = 1024

# Logic-rail constants.  Only "0"/"1" — a net *named* "x" or "z" is a real net
# (a legal Verilog identifier, e.g. a design input literally called "x"), not a
# don't-care constant; post-synthesis ``write_json`` output contains only the
# "0"/"1" rails.
_CONSTANTS = frozenset({"0", "1"})


@dataclass(frozen=True)
class ScoapNet:
    """One net's SCOAP measures.  ``None`` means infinite (uncontrollable/
    unobservable)."""

    net: str
    controllability0: int | None
    controllability1: int | None
    observability: int | None

    def to_wire(self) -> dict:
        return {
            "net": self.net,
            "controllability0": self.controllability0 if self.controllability0 is not None else UNOBSERVABLE,
            "controllability1": self.controllability1 if self.controllability1 is not None else UNOBSERVABLE,
            "observability": self.observability if self.observability is not None else UNOBSERVABLE,
        }


@dataclass(frozen=True)
class ScoapReport:
    """Full per-net table plus the §13.1 delta table and unobservable list."""

    nets: tuple[ScoapNet, ...]
    unobservable: tuple[str, ...]
    delta: tuple[ScoapNet, ...]
    note: str

    def to_wire(self) -> list[dict]:
        """The §13.1 delta table, in ``api.ts`` shape (worst nets first)."""
        return [n.to_wire() for n in self.delta]


_NOTE = (
    "absolute SCOAP costs are not directly comparable; the delta table reports "
    "the nets with the highest observability + max(CC0,CC1), where an "
    f"observability >= {UNOBSERVABLE} means the net is unobservable at every "
    "primary output"
)


# ---------------------------------------------------------------------------
# Cell classification
# ---------------------------------------------------------------------------


def _classify(
    netlist: MappedNetlist,
) -> tuple[list[MappedCell], list[MappedCell], list[MappedCell]]:
    """Split cells into combinational, sequential (flop) and source (M/S)."""
    comb: list[MappedCell] = []
    flops: list[MappedCell] = []
    sources: list[MappedCell] = []
    for c in netlist.cells:
        tier = c.tier
        if tier == "F":
            flops.append(c)
        elif tier in ("M", "S"):
            sources.append(c)
        elif c.part is not None and c.part.function:
            comb.append(c)
        else:
            # Unresolved or function-less cell: no cone to analyse.  Treat as a
            # source so its output (if any) is a leaf rather than a dead end.
            sources.append(c)
    return comb, flops, sources


def _output_net(cell: MappedCell) -> str | None:
    for pin in cell.output_pins:
        net = cell.connections.get(pin)
        if net is not None:
            return net
    return None


def _driver_by_net(cells: Sequence[MappedCell]) -> dict[str, str]:
    driver: dict[str, str] = {}
    for c in cells:
        for pin, net in c.connections.items():
            if c.directions.get(pin) == "output":
                driver.setdefault(net, c.name)
    return driver


# ---------------------------------------------------------------------------
# Combinational topological order (with cycle detection)
# ---------------------------------------------------------------------------


def _topo_order(
    comb: Sequence[MappedCell], driver_by_net: Mapping[str, str]
) -> tuple[list[MappedCell], set[str]]:
    """Kahn order of combinational cells; return (order, loop_cell_names)."""
    by_name = {c.name: c for c in comb}
    g_driver = {
        net: name
        for net, name in driver_by_net.items()
        if name in by_name
    }
    indegree = {c.name: 0 for c in comb}
    dependents: dict[str, list[str]] = {c.name: [] for c in comb}
    for c in comb:
        for pin in c.input_pins:
            net = c.connections.get(pin)
            dep = g_driver.get(net) if net is not None else None
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
    loop = {c.name for c in comb} - seen
    order.extend(sorted((c for c in comb if c.name in loop), key=lambda c: c.name))
    return order, loop


# ---------------------------------------------------------------------------
# Gate-level helpers (controllability + observability via enumeration)
# ---------------------------------------------------------------------------


def _min_cost(*vals: int | None) -> int | None:
    finite = [v for v in vals if v is not None]
    return min(finite) if finite else None


def _add_cost(*vals: int | None) -> int | None:
    total = 0
    for v in vals:
        if v is None:
            return None
        total += v
    return total


def _gate_assignments(func: str, inputs: int) -> list[tuple[dict[str, bool], bool]]:
    """All 2**n input assignments for ``func`` with their output value."""
    pins = boolean.pin_names(inputs)
    out: list[tuple[dict[str, bool], bool]] = []
    for code in range(1 << inputs):
        assignment = {pins[i]: bool(code & (1 << (inputs - 1 - i))) for i in range(inputs)}
        out.append((assignment, boolean.evaluate(func, inputs, assignment)))
    return out


def _reachable_assignments(
    func: str, inputs: int, pin_cc: Mapping[str, tuple[int | None, int | None]]
) -> list[tuple[dict[str, bool], bool]]:
    """The input assignments whose every pin is at a reachable value (finite CC)."""
    out: list[tuple[dict[str, bool], bool]] = []
    for assignment, result in _gate_assignments(func, inputs):
        for pin, value in assignment.items():
            cc = pin_cc.get(pin)
            if cc is None or cc[1 if value else 0] is None:
                break
        else:
            out.append((assignment, result))
    return out


def _gate_cc(
    func: str, inputs: int, pin_cc: Mapping[str, tuple[int | None, int | None]]
) -> tuple[int | None, int | None]:
    """CC0/CC1 of a gate's output by the standard controlling-value recurrence.

    For output value ``v``: if some input can be set to a value that *forces* the
    output to ``v`` (the controlling value), the cost is ``1 + min`` of those
    inputs' controllability to that value; otherwise every input must be set to
    its non-controlling value and the cost is ``1 + sum``.  Only assignments
    reachable under the inputs' controllability (constants excluded) are
    considered.
    """
    pins = boolean.pin_names(inputs)
    reachable = _reachable_assignments(func, inputs, pin_cc)
    by_out = {v: [a for a, r in reachable if r == v] for v in (0, 1)}

    result: dict[int, int | None] = {}
    for v in (0, 1):
        controlling: list[int] = []
        for i, pin in enumerate(pins):
            for w in (0, 1):
                cc = pin_cc.get(pin)
                if cc is None or cc[w] is None:
                    continue
                if all(
                    r == v
                    for a, r in reachable
                    if a[pin] == bool(w)
                ):
                    controlling.append(cc[w])
        if controlling:
            result[v] = min(controlling) + 1
        else:
            best: int | None = None
            for assignment in by_out[v]:
                cost = 1
                for pin, value in assignment.items():
                    cost += pin_cc[pin][1 if value else 0]
                best = cost if best is None else min(best, cost)
            result[v] = best
    return result[0], result[1]


def _gate_observability(
    func: str,
    inputs: int,
    co_out: int | None,
    pin_cc: Mapping[str, tuple[int | None, int | None]],
    pin_index: int,
) -> int | None:
    """Observability of input pin ``pin_index`` through the gate (boolean difference).

    ``CO(pin) = CO(output) + 1 + min over assignments of the other pins that make
    the gate sensitive to ``pin`` of the cost to set those other pins``.
    """
    if co_out is None:
        return None
    pins = boolean.pin_names(inputs)
    best: int | None = None
    for code in range(1 << (inputs - 1)):
        other = [p for j, p in enumerate(pins) if j != pin_index]
        assignment = {other[i]: bool(code & (1 << (len(other) - 1 - i))) for i in range(len(other))}
        a0 = dict(assignment)
        a0[pins[pin_index]] = False
        a1 = dict(assignment)
        a1[pins[pin_index]] = True
        if boolean.evaluate(func, inputs, a0) == boolean.evaluate(func, inputs, a1):
            continue
        cost = co_out + 1
        for pin, value in assignment.items():
            cc = pin_cc.get(pin)
            if cc is None:
                cost = None
                break
            branch = cc[1] if value else cc[0]
            if branch is None:
                cost = None
                break
            cost += branch
        if cost is not None:
            best = cost if best is None else min(best, cost)
    return best


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def analyze_scoap(netlist: MappedNetlist) -> ScoapReport:
    """Compute SCOAP measures over a *resolved* mapped netlist.

    Returns a :class:`ScoapReport`; see the module docstring for the recurrences
    and the feedback/loop handling.
    """
    comb, flops, sources = _classify(netlist)
    driver_by_net = _driver_by_net(list(netlist.cells))

    # --- controllability seeds (leaves) --------------------------------------
    cc: dict[str, tuple[int | None, int | None]] = {}
    for n in netlist.inputs:
        cc[n] = (1, 1)
    for c in sources:
        out = _output_net(c)
        if out is not None:
            cc[out] = (1, 1)
    for c in flops:
        out = _output_net(c)
        if out is not None:
            cc[out] = (1, 1)
    cc["0"] = (0, None)
    cc["1"] = (None, 0)

    # --- combinational controllability (single forward pass) -----------------
    order, loop = _topo_order(comb, driver_by_net)
    for c in order:
        if c.name in loop:
            out = _output_net(c)
            if out is not None:
                cc[out] = (None, None)
            continue
        pin_cc: dict[str, tuple[int | None, int | None]] = {}
        complete = True
        for pin in c.input_pins:
            net = c.connections.get(pin)
            if net is None:
                complete = False
                continue
            if net not in cc:
                complete = False
                continue
            pin_cc[pin] = cc[net]
        out = _output_net(c)
        if out is None:
            continue
        if not complete or c.part is None or not c.part.function:
            cc[out] = (None, None)
            continue
        cc[out] = _gate_cc(c.part.function, c.part.inputs, pin_cc)

    # --- sequential controllability (one step for each flop) -----------------
    for c in flops:
        q = _output_net(c)
        if q is None:
            continue
        sc = _flop_sc(c, cc)
        cc[q] = sc

    # --- observability (backward min-relaxation to fixpoint) -----------------
    co: dict[str, int | None] = {}
    for n in netlist.outputs:
        co[n] = 0

    gates: list[MappedCell] = list(comb) + list(flops)
    for _ in range(_MAX_OBSERVABILITY_PASSES):
        changed = False
        for c in gates:
            out = _output_net(c)
            if out is None:
                continue
            co_out = co.get(out)
            if c in comb:
                if co_out is None or c.part is None or not c.part.function:
                    continue
                pin_cc = {pin: cc.get(c.connections.get(pin), (None, None)) for pin in c.input_pins}
                for idx, pin in enumerate(c.input_pins):
                    net = c.connections.get(pin)
                    if net is None or net in _CONSTANTS:
                        continue
                    val = _gate_observability(
                        c.part.function, c.part.inputs, co_out, pin_cc, idx
                    )
                    if val is not None and (co.get(net) is None or val < co[net]):
                        co[net] = val
                        changed = True
            else:
                d = c.connections.get("D")
                if d is not None and d not in _CONSTANTS and co_out is not None:
                    val = _flop_so_d(c, co_out, cc)
                    if val is not None and (co.get(d) is None or val < co[d]):
                        co[d] = val
                        changed = True
        if not changed:
            break

    # --- report --------------------------------------------------------------
    # Control nets (clock / async set / async reset) are control signals, not
    # data: their observability is not modelled here, and they must not be
    # listed as "unobservable" (which would flag them as testability outliers).
    control_nets = {
        net
        for c in flops
        for pin in ("CK", "RST_N", "SET_N")
        if (net := c.connections.get(pin)) is not None
    }

    reportable = _reportable_nets(netlist)
    nets = tuple(
        sorted(
            (
                ScoapNet(
                    net=n,
                    controllability0=cc.get(n, (None, None))[0],
                    controllability1=cc.get(n, (None, None))[1],
                    observability=co.get(n),
                )
                for n in reportable
            ),
            key=lambda s: s.net,
        )
    )

    unobservable = tuple(
        sorted(
            n
            for n in reportable
            if co.get(n) is None and n not in set(netlist.outputs) and n not in control_nets
        )
    )

    delta = tuple(_delta(nets, exclude=control_nets))

    return ScoapReport(nets=nets, unobservable=unobservable, delta=delta, note=_NOTE)


def _flop_sc(
    cell: MappedCell, cc: Mapping[str, tuple[int | None, int | None]]
) -> tuple[int | None, int | None]:
    """Single-pass sequential controllability of a flop's ``Q`` output.

    ``CC1(CK)`` is the cost of clocking; async controls (``RST_N``/``SET_N``) are
    active-low.  An async reset makes ``SC0(Q)`` cheap, an async set makes
    ``SC1(Q)`` cheap.  See the module docstring for the exact recurrences.
    """
    ck = cell.connections.get("CK")
    d = cell.connections.get("D")
    rst = cell.connections.get("RST_N")
    setn = cell.connections.get("SET_N")

    cc1_ck = (cc.get(ck, (1, 1))[1] if ck else 1)
    cc0_d, cc1_d = cc.get(d, (None, None)) if d else (None, None)
    cc0_rst = cc.get(rst, (None, None))[0] if rst else None
    cc1_rst = cc.get(rst, (None, None))[1] if rst else None
    cc0_setn = cc.get(setn, (None, None))[0] if setn else None
    cc1_setn = cc.get(setn, (None, None))[1] if setn else None

    if rst is None and setn is None:  # DFF
        sc0 = _add_cost(1, cc1_ck, cc0_d)
        sc1 = _add_cost(1, cc1_ck, cc1_d)
    elif rst is not None and setn is None:  # DFF_R
        sc0 = _add_cost(1, _min_cost(_add_cost(cc1_ck, cc0_d), cc0_rst))
        sc1 = _add_cost(1, cc1_ck, cc1_d, cc1_rst)
    elif setn is not None and rst is None:  # DFF_S
        sc0 = _add_cost(1, cc1_ck, cc0_d, cc1_setn)
        sc1 = _add_cost(1, _min_cost(_add_cost(cc1_ck, cc1_d), cc0_setn))
    else:  # DFF_SR
        sc0 = _add_cost(1, _min_cost(_add_cost(cc1_ck, cc0_d, cc1_setn), cc0_rst))
        sc1 = _add_cost(1, _min_cost(_add_cost(cc1_ck, cc1_d, cc1_rst), cc0_setn))
    return sc0, sc1


def _flop_so_d(
    cell: MappedCell,
    co_q: int | None,
    cc: Mapping[str, tuple[int | None, int | None]],
) -> int | None:
    """Sequential observability of a flop's ``D`` input through ``Q``.

    ``SO(D) = CO(Q) + 1 + CC1(CK) + sum(CC1(async pins))``; absent async pins
    contribute nothing, but a present async pin that is uncontrollable to 1 makes
    ``D`` unobservable.
    """
    if co_q is None:
        return None
    terms: list[int | None] = [co_q, 1]
    for pin in ("CK", "RST_N", "SET_N"):
        net = cell.connections.get(pin)
        if net is not None:
            terms.append(cc.get(net, (None, None))[1])
    return _add_cost(*terms)


def _reportable_nets(netlist: MappedNetlist) -> set[str]:
    nets: set[str] = set(netlist.inputs) | set(netlist.outputs)
    for c in netlist.cells:
        for net in c.connections.values():
            if net not in _CONSTANTS:
                nets.add(net)
    return nets


def _delta(
    nets: Sequence[ScoapNet],
    limit: int = DELTA_LIMIT,
    exclude: frozenset[str] = frozenset(),
) -> list[ScoapNet]:
    """The §13.1 delta table: the ``limit`` nets with the worst values.

    "Worst" is defined explicitly: score = observability + max(CC0, CC1), with
    an unobservable net (observability ``None``) treated as infinite so it always
    tops the table.  Ties break by net name for determinism.  Nets in
    ``exclude`` (control signals) are dropped from the table.
    """

    def key(n: ScoapNet):
        obs = n.observability if n.observability is not None else UNOBSERVABLE
        cc = max(
            n.controllability0 if n.controllability0 is not None else 0,
            n.controllability1 if n.controllability1 is not None else 0,
        )
        return (-obs, -cc, n.net)

    candidates = [n for n in nets if n.net not in exclude]
    return sorted(candidates, key=key)[:limit]
