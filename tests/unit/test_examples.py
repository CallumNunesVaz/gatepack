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

from gatepack.examples import SHOWCASE, examples_root, list_examples
from gatepack.frontend import compile_design_file

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
