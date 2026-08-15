"""§18.1 — the showcase project that opens on first launch.

This is the one design every user sees, so it is a golden like any other. A
broken showcase is a broken first impression, and it would be broken silently:
nothing else in the suite compiles it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gatepack.frontend import compile_design_file
from gatepack.project import bundle, explode

ROOT = Path(__file__).resolve().parents[2]
SHOWCASE = ROOT / "examples" / "pelican"
GPK = ROOT / "examples" / "pelican.gpk"


def test_showcase_compiles():
    result = compile_design_file(SHOWCASE / "design.yaml")
    c = result.compiled
    assert c.encoding == "one_hot"
    assert c.state_order == ["GO", "WARN", "STOP", "CROSS", "CLEAR"]
    # 5 state flops + 2 reset sync + 2 per synchronised input
    assert c.flop_count == 5 + 2 + 2 + 2


def test_showcase_exercises_the_features_it_is_meant_to_demonstrate():
    # §18.1(2): every pane must have something real to render. If a future edit
    # trims the showcase down, this is what notices.
    result = compile_design_file(SHOWCASE / "design.yaml")
    design = result.compiled.design
    assert len(design.states) >= 4, "FSM graph needs a non-trivial machine"
    assert len(design.transitions) >= 6
    assert len(design.outputs) >= 3, "truth table needs several output columns"
    assert any(result.compiled.input_sync.values()), "no synchronised input"
    assert len(design.properties) >= 1, "verification panel needs a property"
    assert design.constraints is not None, "analysis dashboard needs constraints"
    assert design.safe_state, "§18.1 requires a declared safe state"


def test_showcase_properties_are_emitted_and_guarded():
    result = compile_design_file(SHOWCASE / "design.yaml")
    props = result.properties
    # each property gets an assertion and an antecedent cover (§11 vacuity)
    for index in range(len(result.compiled.design.properties)):
        assert f"gp_assert_{index}: assert (" in props
        assert f"gp_cover_{index}: cover (" in props


def test_showcase_gpk_is_present_and_round_trips_semantically():
    assert GPK.exists(), "the .gpk showcase is missing; regenerate with `project bundle`"
    project = explode(GPK.read_text())
    assert project.design.data["name"] == "pelican"
    assert project.library is not None, "the .gpk must carry its parts library"
    # Semantic round trip only. Comments and key order are NOT preserved -
    # see the §10.4 limitation recorded in gatepack-design.md. When that is
    # fixed, tighten this into a byte-for-byte comparison of design.yaml.
    assert bundle(SHOWCASE) == GPK.read_text()


@pytest.mark.parametrize("field", ["walk", "traffic_red", "traffic_green"])
def test_showcase_outputs_are_state_decoded(field: str):
    result = compile_design_file(SHOWCASE / "design.yaml")
    assert f"wire {field}_int = " in result.verilog
