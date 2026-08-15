"""Tests for the hand-rolled YAML subset parser (gatepack.frontend.yaml_subset)."""

from __future__ import annotations

import pytest

from gatepack.frontend import yaml_subset as ys


def test_scalars_interpretation():
    node = ys.parse("a: 1\nb: 3.3\nc: true\nd: false\ne: hello\nf: \"quoted & string\"\n")
    data = ys.to_python(node)
    assert data == {
        "a": 1,
        "b": 3.3,
        "c": True,
        "d": False,
        "e": "hello",
        "f": "quoted & string",
    }


def test_on_off_are_strings_not_bools():
    # YAML 1.1 footgun avoided: `on`/`off`/`yes`/`no` stay strings.
    data = ys.to_python(ys.parse("a: ON\nb: off\nc: yes\n"))
    assert data == {"a": "ON", "b": "off", "c": "yes"}


def test_flow_mapping_and_sequence():
    text = "clock: {signal: clk, freq_hz: 32768, source: OSC}\n"
    text += "states: [IDLE, ARMED, RUNNING]\n"
    data = ys.to_python(ys.parse(text))
    assert data["clock"] == {"signal": "clk", "freq_hz": 32768, "source": "OSC"}
    assert data["states"] == ["IDLE", "ARMED", "RUNNING"]


def test_block_sequence_of_flow_mappings():
    text = (
        "inputs:\n"
        "  - {name: arm, sync: true}\n"
        "  - {name: fault, sync: false}\n"
    )
    data = ys.to_python(ys.parse(text))
    assert data["inputs"] == [
        {"name": "arm", "sync": True},
        {"name": "fault", "sync": False},
    ]


def test_nested_block_mapping():
    text = "reset:\n  signal: rst_n\n  active: low\n  async_assert: true\n"
    data = ys.to_python(ys.parse(text))
    assert data["reset"] == {
        "signal": "rst_n",
        "active": "low",
        "async_assert": True,
    }


def test_nested_flow_sequences():
    data = ys.to_python(ys.parse("fundamental_mode:\n  mutually_exclusive: [[a, b], [c, d]]\n"))
    assert data["fundamental_mode"]["mutually_exclusive"] == [["a", "b"], ["c", "d"]]


def test_comment_stripping():
    data = ys.to_python(ys.parse("name: foo  # a trailing comment\n# full-line\nx: 1\n"))
    assert data == {"name": "foo", "x": 1}


def test_hash_inside_quotes_not_a_comment():
    data = ys.to_python(ys.parse('expr: "a # b"\n'))
    assert data["expr"] == "a # b"


def test_provenance_records_line_numbers():
    text = "name: foo\nstates: [A, B]\ntransitions:\n  - {from: A, to: B, when: \"1\"}\n"
    prov = ys.provenance(ys.parse(text))
    assert prov["name"] == 1
    assert prov["states"] == 2
    assert prov["transitions[0]"] == 4
    assert prov["transitions[0].when"] == 4


def test_tab_indentation_rejected():
    with pytest.raises(ys.ParseError, match="tab"):
        ys.parse("a:\n\tb: 1\n")


def test_missing_colon_rejected():
    with pytest.raises(ys.ParseError, match="key: value"):
        ys.parse("a b\n")


def test_block_scalar_rejected():
    with pytest.raises(ys.ParseError, match="block scalar"):
        ys.parse("x: |\n  text\n")
