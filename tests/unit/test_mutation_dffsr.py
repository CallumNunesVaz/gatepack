"""Unit tests for the DFF_SR set-path mutation family.

Mirrors the reset-family tests in ``test_verify.py``.  The set family exists
because a bundled example now instantiates ``DFF_SR`` (``down_counter`` resets
to a non-zero code, so its state bits preset to 1); before that example a
set-path mutation was ``not_applicable`` on every design and measured nothing.

These tests are pure Python: they pin the text transforms, that each mutation
changes *both* artefacts (a ``str.replace`` that no-ops measures nothing), that
each targets only ``DFF_SR`` and leaves ``DFF_R`` byte-identical, and that each
is ``not_applicable`` to a design that instantiates no ``DFF_SR``.
"""

from __future__ import annotations

from pathlib import Path

from gatepack.verify import mutation

REPO = Path(__file__).resolve().parents[2]


def _artefacts() -> tuple[str, str]:
    from gatepack.liberty.generator import generate as generate_liberty
    from gatepack.liberty.sim import generate as generate_sim
    from gatepack.parts import load_parts

    parts = load_parts(REPO / "libraries" / "74aup.csv")
    return generate_liberty(parts, library_name="t").text, generate_sim(parts)


def _mutation(name: str) -> mutation.Mutation:
    return next(m for m in mutation.MUTATIONS if m.name == name)


_SET_FAMILY = ("set_never_asserts", "set_becomes_synchronous", "set_value_flips")


def test_set_family_mutations_all_change_both_artefacts() -> None:
    lib, sim = _artefacts()
    for name in _SET_FAMILY:
        m = _mutation(name)
        lib2, sim2 = m.mutate(lib, sim)
        assert lib2 != lib, f"{name}: did not change cells.lib"
        assert sim2 != sim, f"{name}: did not change cells_sim.v"


def test_set_never_asserts_mutation() -> None:
    lib, sim = _artefacts()
    lib2, sim2 = _mutation("set_never_asserts").mutate(lib, sim)
    # The preset line is gone; the clear-only ff block remains.
    assert 'preset : "!SET_N";' not in lib2
    assert 'clear : "!RST_N";' in lib2
    # The async-set always block is gone; the clear-only block appears.
    assert "negedge SET_N" not in sim2
    assert "else if (!SET_N) Q <= 1'b1;" not in sim2
    assert "always @(posedge CK or negedge RST_N) begin" in sim2


def test_set_becomes_synchronous_mutation() -> None:
    lib, sim = _artefacts()
    lib2, sim2 = _mutation("set_becomes_synchronous").mutate(lib, sim)
    # async preset removed, set folded into next_state; clear stays async.
    assert lib2.count('preset : "!SET_N";') == 0
    assert 'next_state : "(!SET_N | D)";' in lib2
    assert 'clear : "!RST_N";' in lib2
    # the async-set event is dropped but the set test survives, inside the edge.
    assert "negedge SET_N" not in sim2
    assert "else if (!SET_N) Q <= 1'b1;" in sim2
    assert "always @(posedge CK or negedge RST_N) begin" in sim2


def test_set_value_flips_mutation() -> None:
    lib, sim = _artefacts()
    lib2, sim2 = _mutation("set_value_flips").mutate(lib, sim)
    # DFF_SR's preset becomes a clear (set now drives 0), folded into the one
    # `clear` expression the ff group is allowed — see the note below on why a
    # second `clear` line is not an option.
    assert 'preset : "!SET_N";' not in lib2
    assert 'clear : "(!RST_N) | (!SET_N)";' in lib2
    # the set writes 0 instead of 1; the async sensitivity list is unchanged.
    assert "else if (!SET_N) Q <= 1'b0;" in sim2
    assert "always @(posedge CK or negedge RST_N or negedge SET_N) begin" in sim2


def test_set_family_mutations_target_only_dff_sr() -> None:
    lib, _sim = _artefacts()
    for name in _SET_FAMILY:
        m = _mutation(name)
        assert m.targets == ("DFF_SR",), name
        lib2, _ = m.mutate(lib, _sim)
        # DFF_R's own ff block (no preset, no clear_preset_var) is untouched.
        assert mutation._DFF_R_FF in lib2, f"{name} perturbed DFF_R"


def test_set_family_mutations_leave_dff_r_only_artefacts_byte_identical() -> None:
    """The set anchors must not collide with DFF_R (or anything else a design
    using only DFF_R has in its cells.lib/cells_sim.v).

    A DFF_R-only library is simulated by dropping ``DFF_SR`` from the parts; the
    set mutations then have no anchor to match, so both artefacts must come back
    byte-identical.  If an anchor were written to match DFF_R text (or a G-cell,
    or ``DFF``), this test would catch it.
    """
    from gatepack.liberty.generator import generate as generate_liberty
    from gatepack.liberty.sim import generate as generate_sim
    from gatepack.parts import load_parts

    parts = load_parts(REPO / "libraries" / "74aup.csv")
    dff_r_only = [p for p in parts if p.cell != "DFF_SR"]
    lib = generate_liberty(dff_r_only, library_name="t").text
    sim = generate_sim(dff_r_only)

    assert 'preset : "!SET_N";' not in lib  # sanity: DFF_SR really is gone
    assert "negedge SET_N" not in sim

    for name in _SET_FAMILY:
        m = _mutation(name)
        lib2, sim2 = m.mutate(lib, sim)
        assert lib2 == lib, f"{name}: changed a DFF_R-only cells.lib"
        assert sim2 == sim, f"{name}: changed a DFF_R-only cells_sim.v"


def test_set_family_mutations_not_applicable_without_dff_sr() -> None:
    dff_r_only = (
        "module t;\n"
        "  DFF_R _0_ (.D(d), .CK(clk), .Q(q), .RST_N(r));\n"
        "endmodule\n"
    )
    for name in _SET_FAMILY:
        m = _mutation(name)
        assert not mutation.is_applicable(m, dff_r_only), name


def test_set_family_mutations_applicable_with_dff_sr() -> None:
    dff_sr = (
        "module t;\n"
        "  DFF_SR _0_ (.D(d), .CK(clk), .Q(q), .RST_N(r), .SET_N(s));\n"
        "endmodule\n"
    )
    for name in _SET_FAMILY:
        m = _mutation(name)
        assert mutation.is_applicable(m, dff_sr), name


# ---------------------------------------------------------------------------
# Reviewed addition.  The first form of `set_value_flips` emitted a second
# `clear` line into the DFF_SR ff group, which is not valid Liberty.  Measured
# 2026-08-23: Yosys 0.23 imports it *without complaint* ("Imported 11 cell
# types", exit 0), which is worse than rejecting it — the mutation would then
# rest on whichever of the two lines the parser happened to keep, and if it kept
# the second the mutation would be corrupting the RESET path while its name,
# description and verdict all said it was corrupting the SET path.
#
# A mutation whose meaning depends on undefined parser behaviour is a check that
# does not know what it is checking.
# ---------------------------------------------------------------------------


def _dff_sr_ff_group(lib: str) -> str:
    start = lib.index("cell (DFF_SR)")
    ff = lib.index("ff (IQ, IQN)", start)
    return lib[ff : lib.index("}", ff) + 1]


def test_set_value_flips_emits_valid_liberty_with_one_clear():
    lib, sim = _artefacts()
    mutated, _ = _mutation("set_value_flips").mutate(lib, sim)
    group = _dff_sr_ff_group(mutated)
    assert group.count("clear :") == 1, f"a Liberty ff group has one clear, got:\n{group}"
    assert "(!RST_N) | (!SET_N)" in group
    # `preset` is gone: that is the fault — the set pin now clears.
    assert "preset :" not in group


def test_set_value_flips_still_changes_the_set_path_only():
    lib, sim = _artefacts()
    mutated, _ = _mutation("set_value_flips").mutate(lib, sim)
    dff_r_before = lib[lib.index("cell (DFF_R)") : lib.index("cell (DFF_SR)")]
    dff_r_after = mutated[mutated.index("cell (DFF_R)") : mutated.index("cell (DFF_SR)")]
    assert dff_r_before == dff_r_after
