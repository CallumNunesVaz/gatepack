"""Structural self-consistency checks over an emitted ``netlist.net``.

**This is NOT a KiCad import test.**  It is a hand-written parser that reads the
file the emitter produced and checks the file against itself and against the
``refdes.json`` emitted beside it.  A parser that agrees with the emitter proves
nothing about what KiCad will accept — that is exactly the circularity the real
import check (``tests/toolchain/test_kicad_import.py``) exists to avoid.  This
module is the *additional* check: it catches the two failure modes a
wrongly-generated netlist produces regardless of tool, so they are caught early
and cheaply:

* the reference-designator set drifting from ``refdes.json`` (in either
  direction), or a component landing with no footprint;
* a ``no_connect`` pin being quietly attached to a net — and the specific,
  consequential case of it being attached to a power rail, which is a short
  ([R4-20]);
* a component's ``VCC``/``GND`` power pin being dropped or landed on the wrong
  rail.

The parser is deliberately small and understands only the shape
``gatepack/emit/kicad.py`` emits, not the KiCad format in general — it is the
file's *internal* consistency under test, not KiCad compatibility.
"""

from __future__ import annotations

from gatepack.emit.kicad import emit_netlist
from gatepack.emit.refdes import assign_refdes, refdes_map
from gatepack.netlist import stable_cell_names
from gatepack.pack.packer import pack

from .cells import cell, netlist, part


# ---------------------------------------------------------------------------
# A minimal, hand-written `.net` in the emitter's own shape.  Used by the
# "make it fail" tests because its structure is explicit, so each corruption
# can violate exactly one criterion and nothing else.
# ---------------------------------------------------------------------------

MINIMAL_NETLIST = (
    '(export "version" "gatepack-0.1.0")\n'
    '(design "source" "gatepack" (sheet "number" "1" "name" "" "tstamps" "/"))\n'
    '(components '
    '(comp "ref" "U1" "value" "NOR2" "footprint" "SOT-353" "libsource" (lib "gatepack" "part" "NOR2")) '
    '(comp "ref" "U2" "value" "NOR2" "footprint" "SOT-353" "libsource" (lib "gatepack" "part" "NOR2")))\n'
    '(libparts (libpart "lib" "gatepack" "part" "NOR2" (pins '
    '(pin "num" "1" "name" "A" "type" "input") '
    '(pin "num" "2" "name" "B" "type" "input") '
    '(pin "num" "3" "name" "Y" "type" "output") '
    '(pin "num" "4" "name" "VCC" "type" "power_in") '
    '(pin "num" "5" "name" "GND" "type" "power_in"))))\n'
    '(libraries (library "logical" "gatepack" "uri" ""))\n'
    '(nets '
    '(net "code" 1 "name" "VCC" (node "ref" "U1" "pin" "4") (node "ref" "U2" "pin" "4")) '
    '(net "code" 2 "name" "GND" (node "ref" "U1" "pin" "5") (node "ref" "U2" "pin" "5")) '
    '(net "code" 3 "name" "n1" (node "ref" "U1" "pin" "3") (node "ref" "U2" "pin" "1")))\n'
    '(no_connects '
    '(no_connect "ref" "U1" "pin" "1") (no_connect "ref" "U1" "pin" "2") '
    '(no_connect "ref" "U2" "pin" "2") (no_connect "ref" "U2" "pin" "3"))\n'
)

MINIMAL_REFDES = {"p1": "U1", "p2": "U2"}


def _nor(**kwargs):
    return part("NOR2", function="!(A|B)", inputs=2, **kwargs)


def _emit(cells, parts, inputs=(), outputs=()):
    net = netlist("top", cells, inputs=inputs, outputs=outputs)
    names = stable_cell_names(net)
    assigned = assign_refdes(pack(cells, parts, stable_names=names).packed)
    text = emit_netlist(net, assigned, names)
    return text, assigned


# ---------------------------------------------------------------------------
# The parser.  Hand-rolled s-expression reader for the emitted shape only.
# ---------------------------------------------------------------------------


def tokenize(text: str) -> list[str]:
    """Split the s-expression into atoms and ``(``/``)``.

    Quoted strings are unescaped (``\\\\`` and ``\\"``), matching the emitter's
    ``_q``.  Bare atoms (the net ``code`` integers) are returned as strings.
    """
    tokens: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
        elif c in "()":
            tokens.append(c)
            i += 1
        elif c == '"':
            j = i + 1
            buf: list[str] = []
            while j < n:
                if text[j] == "\\" and j + 1 < n:
                    buf.append(text[j + 1])
                    j += 2
                elif text[j] == '"':
                    break
                else:
                    buf.append(text[j])
                    j += 1
            tokens.append("".join(buf))
            i = j + 1
        else:
            j = i
            while j < n and text[j] not in " \t\r\n()\"":
                j += 1
            tokens.append(text[i:j])
            i = j
    return tokens


def _parse(tokens: list[str], pos: int) -> tuple[object, int]:
    tok = tokens[pos]
    if tok == "(":
        pos += 1
        items: list[object] = []
        while tokens[pos] != ")":
            item, pos = _parse(tokens, pos)
            items.append(item)
        return items, pos + 1
    if tok == ")":
        raise ValueError("unbalanced ')' in netlist")
    return tok, pos + 1


def parse_sexprs(text: str) -> list[object]:
    """Parse the top-level s-expressions of ``text`` into nested lists."""
    tokens = tokenize(text)
    out: list[object] = []
    pos = 0
    while pos < len(tokens):
        expr, pos = _parse(tokens, pos)
        out.append(expr)
    return out


def _kv(items: list[object]) -> dict[str, object]:
    """Alternating ``key value`` pairs after a leading head atom."""
    out: dict[str, object] = {}
    i = 1
    while i + 1 < len(items) and isinstance(items[i], str):
        out[items[i]] = items[i + 1]
        i += 2
    return out


def _pairs_until_list(items: list[object]) -> tuple[dict[str, object], list[list[object]]]:
    """Leading ``key value`` pairs; trailing sub-lists are returned separately."""
    kv: dict[str, object] = {}
    sublists: list[list[object]] = []
    i = 1
    while i < len(items):
        if isinstance(items[i], list):
            sublists.append(items[i])  # type: ignore[arg-type]
            i += 1
            continue
        if i + 1 < len(items) and not isinstance(items[i + 1], list):
            kv[items[i]] = items[i + 1]  # type: ignore[index]
            i += 2
        else:
            i += 1
    return kv, sublists


def parse_netlist(text: str) -> dict:
    """Parse an emitted ``.net`` into components, pin tables, nets, no-connects.

    Returns::

        {
          "components": [{"ref", "value", "footprint"}, ...],
          "pins": {part: {pin_number: {"name", "type"}, ...}, ...},
          "nets": {name: [(ref, pin_number), ...], ...},
          "no_connects": [(ref, pin_number), ...],
        }
    """
    components: list[dict[str, str]] = []
    pins: dict[str, dict[str, dict[str, str]]] = {}
    nets: dict[str, list[tuple[str, str]]] = {}
    no_connects: list[tuple[str, str]] = []

    for expr in parse_sexprs(text):
        if not isinstance(expr, list) or not expr:
            continue
        head = expr[0]
        if head == "components":
            for item in expr[1:]:
                if not isinstance(item, list) or item[0] != "comp":
                    continue
                kv = _kv(item)
                components.append(
                    {
                        "ref": str(kv.get("ref", "")),
                        "value": str(kv.get("value", "")),
                        "footprint": str(kv.get("footprint", "")),
                    }
                )
        elif head == "libparts":
            for item in expr[1:]:
                if not isinstance(item, list) or item[0] != "libpart":
                    continue
                kv = _kv(item)
                part_name = str(kv.get("part", ""))
                part_pins: dict[str, dict[str, str]] = {}
                for sub in item:
                    if not isinstance(sub, list) or sub[0] != "pins":
                        continue
                    for p in sub[1:]:
                        if not isinstance(p, list) or p[0] != "pin":
                            continue
                        pkv = _kv(p)
                        part_pins[str(pkv.get("num", ""))] = {
                            "name": str(pkv.get("name", "")),
                            "type": str(pkv.get("type", "")),
                        }
                pins[part_name] = part_pins
        elif head == "nets":
            for item in expr[1:]:
                if not isinstance(item, list) or item[0] != "net":
                    continue
                kv, node_lists = _pairs_until_list(item)
                name = str(kv.get("name", ""))
                for node in node_lists:
                    if node[0] != "node":
                        continue
                    nkv = _kv(node)
                    nets.setdefault(name, []).append(
                        (str(nkv.get("ref", "")), str(nkv.get("pin", "")))
                    )
        elif head == "no_connects":
            for item in expr[1:]:
                if not isinstance(item, list) or item[0] != "no_connect":
                    continue
                kv = _kv(item)
                no_connects.append((str(kv.get("ref", "")), str(kv.get("pin", ""))))

    return {
        "components": components,
        "pins": pins,
        "nets": nets,
        "no_connects": no_connects,
    }


def validate_netlist(parsed: dict, refdes_values: dict) -> list[str]:
    """Return self-consistency violations (empty list == consistent).

    Three criteria, each reported with a distinct prefix so a test can prove an
    input that violates exactly one criterion is caught by that criterion and
    only that criterion:

    * ``refdes`` — the netlist's component set matches ``refdes_values`` in both
      directions, and every component carries a non-empty footprint;
    * ``power`` — the ``VCC``/``GND`` rails exist and every component's
      ``VCC``/``GND`` power pin is on its rail;
    * ``no_connect`` — every no-connect pin names a real component pin and is
      attached to no net (in particular, not a rail).
    """
    violations: list[str] = []

    comps_by_ref = {c["ref"]: c for c in parsed["components"]}
    netlist_refs = set(comps_by_ref)
    expected_refs = set(refdes_values.values())

    for ref in sorted(netlist_refs - expected_refs):
        violations.append(f"refdes: {ref} in netlist but not in refdes.json")
    for ref in sorted(expected_refs - netlist_refs):
        violations.append(f"refdes: {ref} in refdes.json but not in netlist")

    for c in parsed["components"]:
        if not c["footprint"]:
            violations.append(f"refdes: {c['ref']} has no footprint")

    nets = parsed["nets"]
    if "VCC" not in nets:
        violations.append("power: no VCC net")
    if "GND" not in nets:
        violations.append("power: no GND net")

    vcc_nodes = set(nets.get("VCC", []))
    gnd_nodes = set(nets.get("GND", []))
    for ref, c in comps_by_ref.items():
        part_pins = parsed["pins"].get(c["value"], {})
        for signal, rail_nodes in (("VCC", vcc_nodes), ("GND", gnd_nodes)):
            num = next(
                (n for n, pinfo in part_pins.items() if pinfo.get("name") == signal),
                None,
            )
            if num is None:
                violations.append(f"power: {ref} ({c['value']}) has no {signal} pin defined")
                continue
            if (ref, num) not in rail_nodes:
                violations.append(
                    f"power: {ref} ({c['value']}) {signal} pin {num} not on the {signal} net"
                )

    all_nodes: set[tuple[str, str]] = set()
    for nodes in nets.values():
        all_nodes.update(nodes)

    for ref, pin in parsed["no_connects"]:
        if ref not in comps_by_ref:
            violations.append(f"no_connect: {ref} pin {pin} names an unknown component")
            continue
        part_pins = parsed["pins"].get(comps_by_ref[ref]["value"], {})
        if pin not in part_pins:
            violations.append(
                f"no_connect: {ref} pin {pin} is not a pin of {comps_by_ref[ref]['value']}"
            )
            continue
        if (ref, pin) in all_nodes:
            rail = " on a power rail" if (ref, pin) in vcc_nodes | gnd_nodes else ""
            violations.append(f"no_connect: {ref} pin {pin} is attached to a net{rail}")

    return violations


# ---------------------------------------------------------------------------
# Tests: the parser reads real emitted output, and the validator accepts it.
# ---------------------------------------------------------------------------


def test_parser_reads_real_emitted_structure():
    nor = _nor()
    cells = [cell("g0", nor, {"A": "0", "B": "sig", "Y": "out"})]
    text, _ = _emit(cells, [nor], inputs=("sig",), outputs=("out",))
    parsed = parse_netlist(text)
    assert [c["ref"] for c in parsed["components"]] == ["U1"]
    assert parsed["components"][0]["value"] == "74AUPNOR2"
    assert parsed["components"][0]["footprint"] == "SOT-353"
    assert "VCC" in parsed["nets"] and "GND" in parsed["nets"]
    # a tie-off input lands on the GND rail; the power pins on their rails
    assert ("U1", "5") in parsed["nets"]["GND"]
    assert ("U1", "4") in parsed["nets"]["VCC"]
    assert parsed["pins"]["74AUPNOR2"]["4"]["name"] == "VCC"


def test_emitted_netlist_is_self_consistent():
    nor = _nor()
    cells = [
        cell("g0", nor, {"A": "0", "B": "sig", "Y": "n0"}),
        cell("g1", nor, {"A": "n0", "B": "sig2", "Y": "out"}),
    ]
    text, assigned = _emit(cells, [nor], inputs=("sig", "sig2"), outputs=("out",))
    parsed = parse_netlist(text)
    assert validate_netlist(parsed, refdes_map(assigned)) == []


def test_emitted_netlist_with_spare_gate_is_self_consistent():
    nor2 = _nor(gates_per_pkg=2)
    cells = [cell("g0", nor2, {"A": "a", "B": "b", "Y": "n0"})]
    text, assigned = _emit(cells, [nor2], inputs=("a", "b"), outputs=("n0",))
    parsed = parse_netlist(text)
    violations = validate_netlist(parsed, refdes_map(assigned))
    # the spare gate ties inputs to GND and flags its output as a no_connect;
    # all of that must be self-consistent, not reported as a violation.
    assert violations == []


# ---------------------------------------------------------------------------
# "Make it fail": each criterion has an input that violates exactly it.
# ---------------------------------------------------------------------------


def test_minimal_fixture_is_consistent():
    assert validate_netlist(parse_netlist(MINIMAL_NETLIST), MINIMAL_REFDES) == []


def test_refdes_in_json_but_missing_from_netlist_fails():
    violations = validate_netlist(
        parse_netlist(MINIMAL_NETLIST), {"p1": "U1", "p2": "U2", "p3": "U3"}
    )
    assert violations == ["refdes: U3 in refdes.json but not in netlist"]


def test_refdes_in_netlist_but_missing_from_json_fails():
    violations = validate_netlist(parse_netlist(MINIMAL_NETLIST), {"p1": "U1"})
    assert violations == ["refdes: U2 in netlist but not in refdes.json"]


def test_component_without_footprint_fails():
    text = MINIMAL_NETLIST.replace('"ref" "U1" "value" "NOR2" "footprint" "SOT-353"',
                                   '"ref" "U1" "value" "NOR2"')
    violations = validate_netlist(parse_netlist(text), MINIMAL_REFDES)
    assert violations == ["refdes: U1 has no footprint"]


def test_power_pin_dropped_from_rail_fails():
    text = MINIMAL_NETLIST.replace(' (node "ref" "U2" "pin" "5")', "")
    violations = validate_netlist(parse_netlist(text), MINIMAL_REFDES)
    assert violations == ["power: U2 (NOR2) GND pin 5 not on the GND net"]


def test_no_connect_attached_to_power_rail_fails():
    text = MINIMAL_NETLIST.replace(
        '(net "code" 1 "name" "VCC" ',
        '(net "code" 1 "name" "VCC" (node "ref" "U1" "pin" "1") ',
    )
    violations = validate_netlist(parse_netlist(text), MINIMAL_REFDES)
    assert violations == ["no_connect: U1 pin 1 is attached to a net on a power rail"]


def test_no_connect_attached_to_ordinary_net_fails():
    text = MINIMAL_NETLIST.replace(
        '(net "code" 3 "name" "n1" ',
        '(net "code" 3 "name" "n1" (node "ref" "U1" "pin" "1") ',
    )
    violations = validate_netlist(parse_netlist(text), MINIMAL_REFDES)
    assert violations == ["no_connect: U1 pin 1 is attached to a net"]
