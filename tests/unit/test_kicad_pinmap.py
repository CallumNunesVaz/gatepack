"""KiCad emitter pin-map provenance: conditional, per-part pin-number notices.

The emitter reads a part's pin map when one is present and falls back to
positional numbering when it is not.  The pin-number *notice* is conditional on
provenance, not presence: a placeholder map is still not a manufacturer pinout,
so the notice stays loud — it only softens for a part whose pin map is cited.
"""

from __future__ import annotations

from gatepack.emit.kicad import PIN_NUMBER_NOTICE, emit_netlist
from gatepack.emit.refdes import assign_refdes
from gatepack.netlist import stable_cell_names
from gatepack.pack.packer import pack
from gatepack.parts import Verification
from gatepack.pinmap import PartPinMap, PinMapRow

from .cells import cell, netlist, part


def _pinmap(suffix, package, rows, verification=Verification.PLACEHOLDER):
    return PartPinMap(
        part_suffix=suffix,
        package=package,
        pins=[
            PinMapRow(part_suffix=suffix, package=package, pin=p, signal=s, gate=g)
            for (p, s, g) in rows
        ],
        verification=verification,
    )


def _emit(cells, parts):
    net = netlist("top", cells, inputs=("a", "b"), outputs=("y",))
    names = stable_cell_names(net)
    assigned = assign_refdes(pack(cells, parts, stable_names=names).packed)
    return emit_netlist(net, assigned, names)


def test_no_pin_map_falls_back_to_positional_and_loud_notice():
    # Acceptance: a library with no pin map behaves exactly as before — pins
    # numbered positionally (A, B, Y, VCC, GND) with the loud positional notice.
    nor = part("NOR2", function="!(A|B)", inputs=2)
    cells = [cell("g0", nor, {"A": "a", "B": "b", "Y": "y"})]
    text = _emit(cells, [nor])
    assert "POSITIONAL PLACEHOLDERS" in text
    assert PIN_NUMBER_NOTICE in text
    # positional numbering: A=1, B=2, Y=3, VCC=4, GND=5
    assert '(pin "num" "1" "name" "A" "type" "input")' in text
    assert '(pin "num" "3" "name" "Y" "type" "output")' in text
    assert '(pin "num" "5" "name" "GND" "type" "power_in")' in text


def test_placeholder_pin_map_still_produces_the_loud_notice():
    # A placeholder map is not a manufacturer pinout, so the notice stays loud.
    nor = part("NOR2", function="!(A|B)", inputs=2, part_suffix="1G02")
    nor.pinmap = _pinmap(
        "1G02", "SOT-353",
        [(1, "A", 1), (2, "B", 1), (3, "Y", 1), (4, "VCC", None), (5, "GND", None)],
    )
    text = _emit([cell("g0", nor, {"A": "a", "B": "b", "Y": "y"})], [nor])
    assert "Do not fabricate" in text
    assert "PLACEHOLDERS, NOT THE MANUFACTURER PINOUT" in text
    # the notice names the part and its placeholder source, not "no pin map"
    assert "PIN NUMBERS ARE POSITIONAL PLACEHOLDERS" not in text


def test_removing_the_placeholder_notice_fails_the_test():
    # Pin the exact placeholder wording: if the emitter stops emitting it, this
    # test (and the one above) fails, so the placeholder warning cannot silently
    # disappear.
    nor = part("NOR2", function="!(A|B)", inputs=2, part_suffix="1G02")
    nor.pinmap = _pinmap(
        "1G02", "SOT-353",
        [(1, "A", 1), (2, "B", 1), (3, "Y", 1), (4, "VCC", None), (5, "GND", None)],
    )
    text = _emit([cell("g0", nor, {"A": "a", "B": "b", "Y": "y"})], [nor])
    assert "Do not fabricate a board from these numbers until the pin map is verified." in text


def test_cited_pin_map_softens_the_notice():
    nor = part("NOR2", function="!(A|B)", inputs=2, part_suffix="1G02")
    nor.pinmap = _pinmap(
        "1G02", "SOT-353",
        [(1, "A", 1), (2, "B", 1), (3, "Y", 1), (4, "VCC", None), (5, "GND", None)],
        verification=Verification.VERIFIED,
    )
    text = _emit([cell("g0", nor, {"A": "a", "B": "b", "Y": "y"})], [nor])
    assert "Do not fabricate" not in text
    assert "cited pin map" in text


def test_mixed_netlist_says_which_part_is_which():
    # A netlist mixing a cited part and a placeholder part must name each part's
    # status, not make one global claim.
    cited = part("NOR2", function="!(A|B)", inputs=2, part_suffix="1G02")
    cited.pinmap = _pinmap(
        "1G02", "SOT-353",
        [(1, "A", 1), (2, "B", 1), (3, "Y", 1), (4, "VCC", None), (5, "GND", None)],
        verification=Verification.VERIFIED,
    )
    placeholder = part("NAND2", function="!(A&B)", inputs=2, part_suffix="1G00")
    placeholder.pinmap = _pinmap(
        "1G00", "SOT-353",
        [(1, "A", 1), (2, "B", 1), (3, "Y", 1), (4, "VCC", None), (5, "GND", None)],
    )
    cells = [
        cell("g0", cited, {"A": "a", "B": "b", "Y": "y"}),
        cell("g1", placeholder, {"A": "a", "B": "b", "Y": "y"}),
    ]
    text = _emit(cells, [cited, placeholder])
    # both parts are named in the per-part notices
    assert "74AUP1G02" in text
    assert "74AUP1G00" in text
    # the cited part carries the soft notice, the placeholder part the loud one
    assert "74AUP1G02: PIN NUMBERS come from a cited pin map" in text
    assert "74AUP1G00: PIN NUMBERS ARE PLACEHOLDERS" in text


def test_pin_map_numbers_are_used_not_positional():
    # A (placeholder) pin map with non-positional numbers: the emitter uses the
    # map's numbers, not the positional fallback.
    nor = part("NOR2", function="!(A|B)", inputs=2, part_suffix="1G02")
    nor.pinmap = _pinmap(
        "1G02", "SOT-353",
        [(1, "GND", None), (2, "VCC", None), (3, "Y", 1), (4, "B", 1), (5, "A", 1)],
    )
    text = _emit([cell("g0", nor, {"A": "a", "B": "b", "Y": "y"})], [nor])
    assert '(pin "num" "5" "name" "A" "type" "input")' in text
    assert '(pin "num" "4" "name" "B" "type" "input")' in text
    assert '(pin "num" "3" "name" "Y" "type" "output")' in text
    # the net nodes use the map's numbers, not positional ones
    assert '(net "code" 3 "name" "a" (node "ref" "U1" "pin" "5"))' in text
