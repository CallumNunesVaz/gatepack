"""Tests for the §10.4 single-file project format (gatepack.project).

Pins the two properties the format exists to protect: byte-deterministic
round-tripping and detection (rather than silent divergence) of an embedded
library that no longer matches the on-disk CSV.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gatepack.frontend import yaml_subset as yaml_mod
from gatepack.project import (
    ProjectError,
    bundle,
    explode,
    explode_to_dir,
    gpk_text,
    library_divergence,
    load_project,
    parse_gpk,
)
from gatepack.project import serialize

DESIGNS = Path(__file__).resolve().parents[2] / "tests" / "golden" / "designs"
LIBRARY_CSV = Path(__file__).resolve().parents[2] / "libraries" / "74aup.csv"

DESIGN = (
    "name: t\n"
    "timing_model: synchronous\n"
    "clock: {signal: clk, freq_hz: 1, source: OSC}\n"
    "reset: {signal: rst_n, active: low, source: SUPERVISOR}\n"
    "inputs:\n  - {name: x, sync: false}\n"
    "states: [A, B]\n"
    "initial: A\n"
    "transitions:\n"
    '  - {from: A, to: B, when: "x"}\n'
    '  - {from: A, to: A, when: "!x"}\n'
    '  - {from: B, to: A, when: "1"}\n'
    "output_logic: {}\n"
)


def _write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text)
    return p


def _project_dir(tmp_path: Path, design: str = DESIGN) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    _write(tmp_path, "design.yaml", design)
    return tmp_path


def test_round_trip_is_byte_deterministic(tmp_path):
    src = _project_dir(tmp_path)
    text = bundle(src)
    project = explode(text)
    assert gpk_text(project) == text


def test_explode_then_rebundle_is_byte_deterministic(tmp_path):
    src = _project_dir(tmp_path)
    text = bundle(src)
    out = tmp_path / "out"
    explode_to_dir(text, out)
    assert bundle(out) == text
    assert (out / "design.yaml").exists()


@pytest.mark.parametrize("name", ["traffic_light", "xor2", "decoder_3to8"])
def test_reference_design_round_trips(tmp_path, name):
    raw = (DESIGNS / f"{name}.yaml").read_text()
    src = _project_dir(tmp_path / name, raw)
    text = bundle(src)
    project = explode(text)
    assert gpk_text(project) == text
    out = tmp_path / f"{name}_out"
    explode_to_dir(text, out)
    assert bundle(out) == text


def test_truth_table_and_library_round_trip(tmp_path):
    src = _project_dir(tmp_path)
    _write(tmp_path, "truth_table.csv", "a,b,y\n0,0,0\n0,1,1\n1,0,1\n1,1,0\n")
    _write(tmp_path, "parts.csv", LIBRARY_CSV.read_text())
    text = bundle(src)
    project = explode(text)
    assert project.truth_table is not None
    assert project.truth_table.columns == ("a", "b", "y")
    assert project.truth_table.rows == ((0, 0, 0), (0, 1, 1), (1, 0, 1), (1, 1, 0))
    assert project.library is not None
    assert project.library.source == "parts.csv"
    assert gpk_text(project) == text


def test_empty_truth_table_round_trips(tmp_path):
    src = _project_dir(tmp_path)
    _write(tmp_path, "truth_table.csv", "a,b\n")
    text = bundle(src)
    project = explode(text)
    assert project.truth_table.columns == ("a", "b")
    assert project.truth_table.rows == ()
    assert gpk_text(project) == text


def test_expression_strings_survive_round_trip_exactly():
    # expressions with `!`, `&`, `|`, `#`, `:` and a `---` sequence must come
    # back byte-for-byte (§10.4: "arm & !fault" must survive a round trip).
    data = {
        "when": "arm & !fault",
        "expr": "!(a & b) | c",
        "hash": "a # b",
        "colon": "left: right",
        "dashes": "---",
        "numeric_str": "123",
    }
    text = serialize.dumps_mapping(data)
    assert 'when: "arm & !fault"' in text
    assert 'expr: "!(a & b) | c"' in text
    assert 'hash: "a # b"' in text
    assert 'colon: "left: right"' in text
    assert 'dashes: "---"' in text
    assert 'numeric_str: "123"' in text
    assert yaml_mod.to_python(yaml_mod.parse(text)) == data


def test_missing_gatepack_version_key():
    text = "---\nkind: design\nname: t\n"
    with pytest.raises(ProjectError, match="missing 'gatepack'"):
        parse_gpk(text)


def test_wrong_gatepack_version():
    text = "---\ngatepack: 2\nkind: design\nname: t\n"
    with pytest.raises(ProjectError, match="unsupported gatepack version"):
        parse_gpk(text)


def test_unknown_kind():
    text = "---\ngatepack: 1\nkind: banana\nname: t\n"
    with pytest.raises(ProjectError, match="unknown kind 'banana'"):
        parse_gpk(text)


def test_missing_kind_key():
    text = "---\ngatepack: 1\nname: t\n"
    with pytest.raises(ProjectError, match="missing 'kind'"):
        parse_gpk(text)


def test_document_must_be_mapping():
    text = "---\n- a\n- b\n"
    with pytest.raises(ProjectError, match="must be a mapping"):
        parse_gpk(text)


def test_missing_design_document():
    text = "---\ngatepack: 1\nkind: truth_table\ncolumns: [a]\nrows: []\n"
    with pytest.raises(ProjectError, match="missing 'design'"):
        parse_gpk(text)


def test_truth_table_row_length_mismatch():
    text = (
        "---\ngatepack: 1\nkind: design\nname: t\n"
        "---\ngatepack: 1\nkind: truth_table\ncolumns: [a, b]\nrows:\n  - [0]\n"
    )
    with pytest.raises(ProjectError, match="row 0 has 1 value"):
        parse_gpk(text)


def test_error_names_file_document_and_line():
    text = "---\ngatepack: 1\nkind: design\nname: t\n---\ngatepack: 1\nkind: nope\n"
    with pytest.raises(ProjectError) as exc:
        parse_gpk(text, source_name="x.gpk")
    message = str(exc.value)
    assert "x.gpk" in message
    assert "document 2" in message
    assert "line" in message


def test_library_divergence_detected(tmp_path):
    src = _project_dir(tmp_path)
    _write(tmp_path, "parts.csv", LIBRARY_CSV.read_text())
    text = bundle(src)
    project = explode(text)

    status, _ = library_divergence(project, tmp_path)
    assert status == "match"

    # mutate the on-disk library so the canonical sha256 no longer matches
    parts = tmp_path / "parts.csv"
    parts.write_text(parts.read_text().replace("1G04", "1G99"))
    status, detail = library_divergence(project, tmp_path)
    assert status == "mismatch"
    assert "does not match" in detail


def test_library_divergence_missing_source(tmp_path):
    src = _project_dir(tmp_path)
    _write(tmp_path, "parts.csv", LIBRARY_CSV.read_text())
    text = bundle(src)
    project = explode(text)
    (tmp_path / "parts.csv").unlink()
    status, _ = library_divergence(project, tmp_path)
    assert status == "missing"


def test_load_project_accepts_directory_and_gpk(tmp_path):
    src = _project_dir(tmp_path)
    gpk_path = tmp_path / "p.gpk"
    gpk_path.write_text(bundle(src))

    from_dir = load_project(src)
    from_gpk = load_project(gpk_path)
    assert from_dir.design.data == from_gpk.design.data


def test_bundle_rejects_directory_without_design(tmp_path):
    with pytest.raises(ProjectError, match="no design.yaml"):
        bundle(tmp_path)
