"""Tests for the C3 SynchronousBackend Yosys-script generation (§12 C3).

These test *script generation*, not a real Yosys run (Yosys is not installed).
The assertions pin the corrections the design mandates: no bare ``fsm``
([R4-5]), ``setundef -zero`` before the golden/mapped split ([R4-12]), explicit
``dfflegalize`` ([R4-2]), the ``$mem`` assertion ([R4-13]), and the latch ban
(§9.2).
"""

from __future__ import annotations

import pytest

from gatepack.synth.asynchronous import AsynchronousBackend
from gatepack.synth.base import SynthConfig
from gatepack.synth.synchronous import SynchronousBackend
from gatepack.frontend.errors import AsyncRefused


def _config(**overrides) -> SynthConfig:
    base = dict(
        top="mytop",
        flop_cells=("DFF", "DFF_R", "DFF_SR"),
    )
    base.update(overrides)
    return SynthConfig(**base)


def _script(config: SynthConfig | None = None) -> str:
    return SynchronousBackend().generate_script(config or _config())


def _lines(s: str) -> list[str]:
    return [ln.strip() for ln in s.splitlines() if ln.strip()]


def test_script_contains_common_frontend_commands():
    s = _script()
    for expected in [
        "read_verilog -sv",
        "hierarchy -check -top mytop",
        "proc; flatten; opt",
        "techmap; opt",
        "setundef -zero",
        "write_json",
    ]:
        assert expected in s


def test_no_bare_fsm_pass():
    # No *command* line starts with `fsm`; the only occurrence is the R4-5
    # comment explaining why the bare `fsm` pass is deliberately absent.
    for line in _lines(_script()):
        assert not line.startswith("fsm")


def test_setundef_comes_before_split():
    s = _script()
    assert s.index("setundef -zero") < s.index("dfflibmap")
    assert s.index("setundef -zero") < s.index("abc ")


def test_explicit_dfflegalize():
    s = _script()
    assert "dfflegalize" in s
    assert "$_DFF_P_ 01" in s
    assert "$_DFF_PN0_ 01" in s
    assert "$_DFFSR_PNN_ 01" in s


def test_dfflegalize_only_lists_present_flop_cells():
    s = _script(_config(flop_cells=("DFF",)))
    assert "$_DFF_P_ 01" in s
    assert "$_DFF_PN0_" not in s


def test_mem_assertion():
    assert "select -assert-none t:$mem" in _script()


def test_latch_ban():
    assert "select -assert-none t:$_DLATCH_* t:$_SR_*" in _script()


def test_dfflibmap_precedes_abc():
    s = _script()
    assert s.index("dfflibmap") < s.index("abc ")


def test_write_verilog_noattr_for_icarous():
    assert "write_verilog -noattr" in _script()


def test_common_frontend_is_shared_verbatim():
    from gatepack import yosys

    raw = yosys.load_common_frontend()
    rendered = yosys.common_frontend("top", "gen.v", "premap.json")
    assert "__TOP__" not in rendered
    assert "top" in rendered
    # the shared file is the single source of truth (§C4)
    assert raw.count("read_verilog") == 1


def test_asynchronous_backend_refuses():
    with pytest.raises(AsyncRefused, match="v0.1.0"):
        AsynchronousBackend().generate_script(_config())
