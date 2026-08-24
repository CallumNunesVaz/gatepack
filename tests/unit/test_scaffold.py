"""Tests for `gatepack project new` (gatepack.scaffold).

The GUI could open designs but never create one. These pin the template that
closed that gap: it must be a *working* project, not a plausible-looking stub,
because the first thing a new user does with it is press verify.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gatepack.frontend import compile_design_file
from gatepack.scaffold import ScaffoldError, design_name_from, new_project

REPO = Path(__file__).resolve().parents[2]


def test_new_project_writes_a_design_and_a_library(tmp_path):
    written = new_project(tmp_path / "widget")
    names = sorted(p.name for p in written)
    assert names == ["design.yaml", "parts.csv"]
    for p in written:
        assert p.is_file() and p.stat().st_size > 0


def test_the_scaffolded_design_actually_compiles(tmp_path):
    """The template must survive the front-end, not merely look like YAML.

    A scaffold that produces a spec the compiler rejects is worse than no
    scaffold: the user's first action after File > New is to press a button,
    and the error they get would be about a file they did not write.
    """
    new_project(tmp_path / "widget")
    result = compile_design_file(tmp_path / "widget" / "design.yaml")
    compiled = result.compiled
    assert compiled.design.name == "widget"
    assert compiled.design.timing_model == "synchronous"
    # Two states and both reachable; the transitions cover every input value,
    # so the front-end raises nothing about coverage.
    assert set(compiled.design.states) == {"IDLE", "RUN"}


def test_the_design_name_follows_the_directory_and_stays_an_identifier():
    """Directory names come from a file dialog, so they are not identifiers.

    The name reaches generated Verilog as a module name. Sanitise rather than
    reject: someone who types "My First Board" should get a working project.
    """
    assert design_name_from("widget") == "widget"
    assert design_name_from("My First Board") == "my_first_board"
    assert design_name_from("led-blinker") == "led_blinker"
    # A leading digit is not a valid identifier, and an empty stem has nothing
    # to derive from; both get a prefix rather than an error.
    assert design_name_from("7seg") == "design_7seg"
    assert design_name_from("--") == "design"


def test_an_explicit_name_overrides_the_directory(tmp_path):
    new_project(tmp_path / "whatever", name="traffic")
    assert "name: traffic" in (tmp_path / "whatever" / "design.yaml").read_text()


def test_new_project_never_overwrites_an_existing_design(tmp_path):
    """Scaffolding onto a real project would destroy work.

    A GUI's File > New cannot always tell that the directory the user picked in
    a dialog already holds a design, so the refusal has to live here.
    """
    target = tmp_path / "widget"
    new_project(target)
    (target / "design.yaml").write_text("name: mine\n")
    with pytest.raises(ScaffoldError, match="will not overwrite"):
        new_project(target)
    assert (target / "design.yaml").read_text() == "name: mine\n"


def test_an_existing_parts_csv_is_left_alone(tmp_path):
    """A user's own library beside a fresh design is theirs, not ours."""
    target = tmp_path / "widget"
    target.mkdir()
    (target / "parts.csv").write_text("mine\n")
    written = new_project(target)
    assert [p.name for p in written] == ["design.yaml"]
    assert (target / "parts.csv").read_text() == "mine\n"


def test_the_seeded_library_matches_the_shipped_one(tmp_path):
    """The drift guard for the frozen build.

    `libraries/74aup.csv` is deliberately NOT bundled into the PyInstaller core
    (scripts/bundle_core.py), so the scaffold seeds from the widest bundled
    example library instead — one code path from source and when frozen. That
    only stays honest while some example still carries the full library. If
    someone trims them all, a new project would quietly ship a narrower parts
    list, and this fails instead.
    """
    shipped = REPO / "libraries" / "74aup.csv"
    if not shipped.exists():  # pragma: no cover - source checkouts have it
        pytest.skip("not a source checkout")
    new_project(tmp_path / "widget")
    assert (tmp_path / "widget" / "parts.csv").read_text() == shipped.read_text()


def test_scaffolding_is_deterministic(tmp_path):
    """Two new projects of the same name are byte-identical (§5.5's spirit)."""
    new_project(tmp_path / "a", name="widget")
    new_project(tmp_path / "b", name="widget")
    for f in ("design.yaml", "parts.csv"):
        assert (tmp_path / "a" / f).read_text() == (tmp_path / "b" / f).read_text()
