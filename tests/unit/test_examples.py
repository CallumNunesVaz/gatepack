"""Unit tests for the bundled examples (§18.1), toolchain-free.

The toolchain-dependent half (every example builds and verifies against real
Yosys) lives in ``tests/toolchain/test_examples.py``. This module pins the
things a broken example can get wrong without any tool: a missing ``design.yaml``,
a file that does not parse, an empty summary line, a ``parts.csv`` whose rows
were not copied verbatim from the shipped library, or a new example shipping a
lossy ``.gpk`` copy of itself.

None of these iterates a hand-written list of names: every test walks the
``examples/`` directory, so an example added later is checked the moment it
lands, whether or not anyone remembered to update a test.
"""

from __future__ import annotations

from pathlib import Path

from gatepack.examples import SHOWCASE, examples_root, get_example, list_examples
from gatepack.frontend import compile_design_file
from gatepack.frontend import expr as expr_mod
from gatepack.parts import load_parts

REPO = Path(__file__).resolve().parents[2]
LIBRARY = REPO / "libraries" / "74aup.csv"


def _example_dirs() -> list[Path]:
    return sorted(p for p in examples_root().iterdir() if p.is_dir())


def test_every_example_has_a_design_yaml_and_is_discoverable():
    discovered = {e.name for e in list_examples()}
    assert discovered, "no bundled examples discovered"
    for directory in _example_dirs():
        assert (directory / "design.yaml").is_file(), (
            f"{directory.name}: example directory has no design.yaml"
        )
        assert directory.name in discovered, (
            f"{directory.name}: not returned by gatepack.examples.list_examples()"
        )


def test_every_example_parses_and_compiles():
    for example in list_examples():
        compiled = compile_design_file(example.path / "design.yaml").compiled
        assert compiled.design.name == example.name


def test_every_example_has_a_summary_line():
    for example in list_examples():
        assert example.summary, (
            f"{example.name}: empty summary — the first non-empty comment line "
            "of design.yaml becomes the `examples list` one-liner"
        )


def test_every_example_ships_its_own_library_and_citations():
    """A project the app opens must carry its own `parts.csv`.

    The app builds an open project with `--library <project>/parts.csv` when
    that file exists and with **no** `--library` at all when it does not — and
    `gatepack build` requires the flag, so an example without a `parts.csv`
    cannot be built from the GUI at all.

    An example whose library offers a *multi-gate* part needs the companion
    `parts.refs.md` as well. The citations live beside the CSV
    (`refs.py::find_refs_file`); without them a multi-gate part reads as
    uncited, and the `gates_per_pkg` gate refuses the build — correctly, since
    a wrong gate count produces a board that cannot be assembled. The showcase
    ships a single-gate-only subset and so needs no citations; every example
    that ships the full library does.
    """
    for example in list_examples():
        parts = example.path / "parts.csv"
        assert parts.is_file(), (
            f"{example.name}: no parts.csv — the app builds an open project with "
            "its project-local library, and `build` requires one"
        )
        rows = [r for r in parts.read_text().splitlines()[1:] if r.strip()]
        multi_gate = [r for r in rows if r.split(",")[7].strip() not in ("", "1")]
        if multi_gate:
            assert (example.path / "parts.refs.md").is_file(), (
                f"{example.name}: parts.csv offers {len(multi_gate)} multi-gate "
                "part(s) but ships no parts.refs.md beside it — they would read "
                "as uncited and the build would be refused"
            )


def test_example_parts_csv_rows_are_verbatim_from_the_library():
    library_lines = set(LIBRARY.read_text().splitlines())
    for example in list_examples():
        parts = example.path / "parts.csv"
        if not parts.exists():
            continue
        for row in parts.read_text().splitlines():
            assert row in library_lines, (
                f"{example.name}: parts.csv row not copied verbatim from "
                f"libraries/74aup.csv: {row!r}"
            )


def test_every_example_library_contains_the_cells_its_design_names():
    """`design.yaml` names cells; the project's `parts.csv` must provide them.

    The two places a design *names* a cell without synthesising are the reset
    source (`reset.source`, an S-cell) and any `macros[].cell` (an M-cell). A
    design whose `parts.csv` lacks a cell it names cannot be built from its own
    library — the path the GUI takes — so the two files must agree. This is the
    toolchain-free half of the "build against the project's own library" check
    (`tests/toolchain/test_examples.py`), which requires Yosys and skips without
    it; this runs everywhere.
    """
    for example in list_examples():
        parts = example.path / "parts.csv"
        if not parts.exists():
            continue
        cells = {part.cell for part in load_parts(parts)}
        compiled = compile_design_file(example.path / "design.yaml").compiled
        design = compiled.design
        if design.reset.source:
            assert design.reset.source in cells, (
                f"{example.name}: reset source {design.reset.source!r} is not a "
                "cell in its parts.csv — the GUI build path cannot place it"
            )
        for macro in design.macros:
            assert macro.cell in cells, (
                f"{example.name}: macro {macro.instance!r} names M-cell "
                f"{macro.cell!r}, which is not in its parts.csv"
            )


def test_seven_segment_matches_the_reference_glyph_table():
    """The decoder's segment logic is the textbook seven-segment glyph table.

    ``gatepack verify`` proves the *synthesised* netlist matches the spec, not
    that the spec matches the digit shapes a human expects — a wrong boolean
    expression verifies just as green as a right one. So the segment expressions
    are checked here against an independent reference: for each of the 16 input
    codes, the set of segments that must light, written as the classic on-segment
    letters (a..g) rather than as the minterms the design spells out. The two
    representations are different enough that a transcription error in either
    one shows up as a mismatch.
    """
    glyphs = {
        0x0: "abcdef",
        0x1: "bc",
        0x2: "abdeg",
        0x3: "abcdg",
        0x4: "bcfg",
        0x5: "acdfg",
        0x6: "acdefg",
        0x7: "abc",
        0x8: "abcdefg",
        0x9: "abcdfg",
        0xA: "abcefg",
        0xB: "cdefg",
        0xC: "adef",
        0xD: "bcdeg",
        0xE: "adefg",
        0xF: "aefg",
    }
    compiled = compile_design_file(
        get_example("seven_segment").path / "design.yaml"
    ).compiled
    inputs = ["b3", "b2", "b1", "b0"]
    for segment in "abcdefg":
        ast = compiled.output_asts[f"seg_{segment}"]
        for value in range(16):
            env = {
                name: bool((value >> (3 - index)) & 1)
                for index, name in enumerate(inputs)
            }
            assert expr_mod.evaluate(ast, env) is (segment in glyphs[value]), (
                f"seg_{segment} at code {value:#x}: decoder logic disagrees with "
                f"the reference glyph {glyphs[value]!r}"
            )


def test_no_new_example_ships_a_gpk():
    # §10.4's single-file form currently loses comments and key order, so a new
    # example shipping a lossy copy of itself is a trap. The showcase's .gpk
    # predates that defect and is grandfathered; nothing else may ship one.
    for directory in _example_dirs():
        if directory.name == SHOWCASE:
            continue
        assert not list(directory.glob("*.gpk")), (
            f"{directory.name}: new example ships a .gpk (a lossy round-trip copy)"
        )
        assert not (directory.parent / f"{directory.name}.gpk").exists(), (
            f"{directory.name}: new example ships a .gpk (a lossy round-trip copy)"
        )


def test_seven_segment_glyphs_match_the_hex_font():
    """The decoder lights the right segments for all sixteen digits.

    The example's own SOP test catches a *transcription* error — an expression
    that does not match the table beside it. It cannot catch a wrong table,
    which the package flagged as its weakest point. This asserts the glyphs
    themselves against the hex seven-segment font written out independently
    here, so a plausible-but-wrong entry fails rather than teaching a wrong
    circuit.
    """
    import re

    from gatepack.frontend import expr as expr_mod
    from gatepack.examples import get_example

    text = (get_example("seven_segment").path / "design.yaml").read_text()
    body = text.split("output_logic:")[1]
    logic = {
        m.group(1): expr_mod.parse(m.group(2))
        for m in re.finditer(r'^\s+(seg_[a-g]):\s*"(.*)"\s*$', body, re.M)
    }
    assert sorted(logic) == [f"seg_{s}" for s in "abcdefg"]

    font = {
        0x0: "abcdef", 0x1: "bc", 0x2: "abdeg", 0x3: "abcdg",
        0x4: "bcfg", 0x5: "acdfg", 0x6: "acdefg", 0x7: "abc",
        0x8: "abcdefg", 0x9: "abcdfg", 0xA: "abcefg", 0xB: "cdefg",
        0xC: "adef", 0xD: "bcdeg", 0xE: "adefg", 0xF: "aefg",
    }

    for value, expected in font.items():
        env = {f"b{bit}": bool((value >> bit) & 1) for bit in range(4)}
        lit = "".join(
            segment
            for segment in "abcdefg"
            if expr_mod.evaluate(logic[f"seg_{segment}"], env)
        )
        assert lit == expected, f"digit {value:X}: lights {lit!r}, font says {expected!r}"
