"""Shared helpers for front-end unit tests."""

from __future__ import annotations


def sync_design(**overrides) -> str:
    """A minimal, valid synchronous design (explicit self-loops, one input ``x``)."""
    name = overrides.pop("name", "min")
    states = overrides.pop("states", ["A", "B"])
    initial = overrides.pop("initial", "A")
    transitions = overrides.pop(
        "transitions",
        [
            ("A", "B", "x"),
            ("A", "A", "!x"),
            ("B", "A", "!x"),
            ("B", "B", "x"),
        ],
    )
    outputs = overrides.pop("outputs", [])
    output_logic = overrides.pop("output_logic", {})
    expressions = overrides.pop("expressions", {})

    lines = [
        f"name: {name}",
        "timing_model: synchronous",
        "clock: {signal: clk, freq_hz: 1000, source: OSC}",
        "reset: {signal: rst_n, active: low, source: SUPERVISOR}",
        "encoding: one_hot",
        "inputs:",
        "  - {name: x, sync: false}",
    ]
    if expressions:
        lines.append("expressions:")
        for k, v in expressions.items():
            lines.append(f'  {k}: "{v}"')
    lines.append(f"states: {states}")
    lines.append(f"initial: {initial}")
    lines.append("transitions:")
    for src, dst, when in transitions:
        lines.append(f'  - {{from: {src}, to: {dst}, when: "{when}"}}')
    if outputs:
        lines.append("outputs:")
        for o in outputs:
            lines.append(f"  - {{name: {o}}}")
    if output_logic:
        lines.append("output_logic:")
        for k, v in output_logic.items():
            lines.append(f'  {k}: "{v}"')
    for k, v in overrides.items():
        lines.append(f"{k}: {v}")
    return "\n".join(lines) + "\n"
