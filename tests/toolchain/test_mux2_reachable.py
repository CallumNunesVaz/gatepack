"""The MUX2 cell is reachable: a real synthesis maps a 2:1 mux onto it.

`MUX2` (74AUP1G157) is single-sourced, so it is excluded from the default
Liberty file (§10.1 [R4-9]).  That is a *sourcing* policy, not a capability:
this test proves the cell's function string and generated Liberty model are
correct by building a Liberty that includes it (`allow_single_source=True`),
running the pinned Yosys toolchain over a combinational 2:1 mux design, and
asserting MUX2 appears in the mapped netlist with the right port count.  A
part whose model could not be mapped onto would be dead weight; this is the
check that prevents that from being asserted without a real run.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from gatepack.frontend import compile_design_file
from gatepack.liberty.generator import generate as generate_liberty
from gatepack.parts import load_parts
from gatepack.synth.base import SynthConfig
from gatepack.synth.synchronous import SynchronousBackend
from tests.toolchain.docker_runner import IMAGE, run_work

REPO = Path(__file__).resolve().parents[2]
DESIGN = REPO / "tests" / "golden" / "designs" / "mux2.yaml"
LIBRARY = REPO / "libraries" / "74aup.csv"


def _toolchain_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(
        ["docker", "image", "inspect", IMAGE], capture_output=True, text=True
    ).returncode == 0


requires_toolchain = pytest.mark.skipif(
    not _toolchain_available(),
    reason=f"toolchain image {IMAGE} not available; see Dockerfile.probe",
)


@requires_toolchain
def test_synthesis_maps_mux_onto_mux2(tmp_path: Path) -> None:
    result = compile_design_file(DESIGN)
    (tmp_path / "generated.v").write_text(result.verilog)

    # Build a Liberty that includes the single-sourced MUX2 cell.
    parts = load_parts(LIBRARY)
    liberty = generate_liberty(
        parts, library_name="gatepack", project_vcc=3.3, allow_single_source=True
    )
    assert "cell (MUX2)" in liberty.text
    (tmp_path / "cells.lib").write_text(liberty.text)

    flop_cells = tuple(
        sorted(p.cell for p in parts if p.tier == "F" and p.cell in liberty.cells)
    )
    script = SynchronousBackend().generate_script(
        SynthConfig(
            top=result.compiled.design.name,
            generated_v="generated.v",
            cells_lib="cells.lib",
            premap_json="premap.json",
            mapped_json="mapped.json",
            mapped_v="mapped.v",
            flop_cells=flop_cells,
        )
    )
    (tmp_path / "yosys.ys").write_text(script)

    proc = run_work(tmp_path, "bash", "-c", "cd /work && yosys -q yosys.ys")
    assert proc.returncode == 0, (
        f"yosys failed on the mux2 design:\n{proc.stdout}\n{proc.stderr}"
    )

    mapped = json.loads((tmp_path / "mapped.json").read_text())
    cells = list(mapped["modules"][result.compiled.design.name]["cells"].values())
    mux_cells = [c for c in cells if c["type"] == "MUX2"]
    assert mux_cells, (
        "the mux2 design did not map onto MUX2; mapped cell types: "
        f"{sorted({c['type'] for c in cells})}"
    )
    for c in mux_cells:
        assert sorted(c["connections"]) == ["A", "B", "C", "Y"]
