"""Does KiCad's *own* code read an emitted ``netlist.net``?  (M10-1)

The descoped v0.1.0 criterion — "KiCad import clean, including power symbols and
no-connects" — was removed on the premise that it needs a human with KiCad.  The
counter-argument was that KiCad ships its netlist reader as a Python module, so
the check should be automatable by driving ``pcbnew`` headlessly.

Measured result, against real KiCad (9.0.9, cross-checked 10.0.5): **it is not
automatable.**  ``pcbnew`` exposes no netlist reader — ``NETLIST_READER``,
``PCB_NETLIST`` and ``LoadFootprintsFromNetlist`` are all absent from the Python
API (``grep -c NETLIST pcbnew.py`` == 0), and ``kicad-cli`` has no
netlist-import subcommand.  So this test does not *fake* an import; it drives
``scripts/kicad_import_check.py`` inside the pinned image and asserts the honest
result — that the check reports "blocked" and exits 2.

The test is still a *real* check with teeth: it runs the real probe in the real
pinned image.  If a future KiCad version finally exposes the reader, the script
stops reporting "blocked", this test fails with a message saying to implement
the real import check — rather than silently continuing to assert a now-false
absence.  It skips cleanly (never faked) only when the KiCad image is not built.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from gatepack.emit.kicad import emit_netlist
from gatepack.emit.refdes import assign_refdes
from gatepack.netlist import stable_cell_names
from gatepack.pack.packer import pack

from tests.unit.cells import cell, netlist, part
from tests.toolchain.docker_runner import REPO, run_repo

#: The image `Dockerfile.kicad` produces; CI builds it with this exact tag.
KICAD_IMAGE = "gatepack-kicad:9.0.9"

#: `scripts/kicad_import_check.py` exits 2 when the reader is not drivable.
EXIT_BLOCKED = 2


def _kicad_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return (
        subprocess.run(
            ["docker", "image", "inspect", KICAD_IMAGE], capture_output=True, text=True
        ).returncode
        == 0
    )


requires_kicad = pytest.mark.skipif(
    not _kicad_available(),
    reason=f"KiCad image {KICAD_IMAGE} not available; see Dockerfile.kicad",
)


def _emit_netlist() -> str:
    """A real emitter-produced ``.net`` (no Yosys needed for this shape)."""
    nor = part("NOR2", function="!(A|B)", inputs=2)
    cells = [cell("g0", nor, {"A": "0", "B": "sig", "Y": "out"})]
    net = netlist("top", cells, inputs=("sig",), outputs=("out",))
    names = stable_cell_names(net)
    assigned = assign_refdes(pack(cells, [nor], stable_names=names).packed)
    return emit_netlist(net, assigned, names)


@requires_kicad
def test_kicad_netlist_reader_is_not_exposed_headlessly():
    """The pinned KiCad image has no scriptable netlist reader — reported, not faked.

    This is the honest form of the M10-1 check: feed a real netlist to the probe,
    and require it to *say* it is blocked (exit 2) rather than to pretend it read
    the file.  The day a KiCad release exposes the reader, this assertion fails
    and its message is the instruction to implement the real import.
    """
    out_dir = REPO / ".gpout" / "kicad-import-probe"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "netlist.net").write_text(_emit_netlist())

    proc = run_repo(
        "python3",
        "scripts/kicad_import_check.py",
        ".gpout/kicad-import-probe/netlist.net",
        image=KICAD_IMAGE,
    )

    assert proc.returncode == EXIT_BLOCKED, (
        "kicad_import_check.py no longer reports 'blocked' against "
        f"{KICAD_IMAGE}. A headless KiCad netlist reader may now exist — "
        "implement the real import check (the three criteria) in "
        "scripts/kicad_import_check.py and rewrite this test to assert them.\n"
        f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
    )

    report = proc.stdout
    assert "no headless netlist reader" in report
    assert "pcbnew " in report  # the version line proves pcbnew itself was reached
    # each of the would-be reader symbols must be named absent — if one appears,
    # the reader is half-exposed and the real check is the next step.
    for symbol in ("NETLIST_READER", "PCB_NETLIST", "LoadFootprintsFromNetlist"):
        assert f"{symbol}: absent" in report
