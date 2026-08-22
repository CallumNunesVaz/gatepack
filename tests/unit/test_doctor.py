"""Unit tests for ``gatepack.doctor`` — the toolchain/self-check report.

The report is a *report*, never a gate: a missing tool is a visible
``found: false`` entry, and ``allToolsPresent`` folds only the tools gatepack
invokes directly (yosys, sby, iverilog, vvp), never the indirect ones (z3 via
sby, espresso via the not-yet-built async backend).
"""

from __future__ import annotations

from gatepack.doctor import TOOLS, ToolSpec, is_windows, run_doctor


def test_tool_table_is_the_pinned_order():
    names = [spec.name for spec in TOOLS]
    assert names == ["yosys", "sby", "iverilog", "vvp", "z3", "bash", "espresso"]
    # every spec names its purpose and whether gatepack invokes it directly
    for spec in TOOLS:
        assert spec.purpose
        assert isinstance(spec.direct, bool)


def test_run_doctor_reports_every_tool_with_stable_shape():
    payload = run_doctor()
    assert payload["version"]
    assert [t["name"] for t in payload["tools"]] == [s.name for s in TOOLS]
    for tool in payload["tools"]:
        assert set(tool) == {"name", "found", "purpose", "direct", "path", "version", "source"}
        assert isinstance(tool["found"], bool)
        if tool["found"]:
            assert tool["path"]
            assert tool["source"] in {"bundled", "system", "env"}
        else:
            assert tool["path"] is None
            assert tool["version"] is None
            assert tool["source"] is None
    # resources actually load in the source tree
    assert payload["resources"] == {
        "commonFrontendYs": True,
        "mcellModels": True,
        "mcellCount": 2,
    }


def test_all_tools_present_ignores_indirect_tools(monkeypatch):
    found = {"yosys": "/usr/bin/yosys", "sby": "/usr/bin/sby",
             "iverilog": "/usr/bin/iverilog", "vvp": "/usr/bin/vvp"}

    def fake_which(name: str) -> str | None:
        return found.get(name)

    import shutil

    monkeypatch.setattr(shutil, "which", fake_which)
    # doctor.py probes versions by shelling out; stub that to avoid spawning.
    import gatepack.doctor as doctor

    monkeypatch.setattr(doctor, "_probe_version", lambda name, args: "1.2.3")

    payload = run_doctor()
    by_name = {t["name"]: t for t in payload["tools"]}
    assert all(by_name[name]["found"] for name in found)
    assert by_name["z3"]["found"] is False  # indirect: does not gate the flag
    assert by_name["espresso"]["found"] is False
    assert payload["allToolsPresent"] is True
    assert by_name["yosys"]["version"] == "1.2.3"


def test_all_tools_present_false_when_a_direct_tool_is_missing(monkeypatch):
    found = {"yosys": "/usr/bin/yosys", "sby": "/usr/bin/sby",
             "iverilog": "/usr/bin/iverilog"}  # vvp missing

    def fake_which(name: str) -> str | None:
        return found.get(name)

    import shutil

    monkeypatch.setattr(shutil, "which", fake_which)
    import gatepack.doctor as doctor

    monkeypatch.setattr(doctor, "_probe_version", lambda name, args: None)

    payload = run_doctor()
    assert payload["allToolsPresent"] is False
    by_name = {t["name"]: t for t in payload["tools"]}
    assert by_name["vvp"]["found"] is False
    assert by_name["yosys"]["found"] is True


def test_is_windows_is_injectable():
    assert is_windows("win32") is True
    assert is_windows("linux") is False
    assert is_windows("darwin") is False
    import sys

    assert is_windows() is (sys.platform == "win32")


def test_windows_guidance_only_on_windows(monkeypatch):
    # The host is not Windows, so the default report carries no Windows wording.
    monkeypatch.setattr("gatepack.doctor._probe_version", lambda name, args: None)
    payload = run_doctor()
    by_name = {t["name"]: t for t in payload["tools"]}
    assert "On Windows" not in by_name["yosys"]["purpose"]
    assert "OSS CAD Suite" not in by_name["yosys"]["purpose"]


def test_windows_guidance_names_a_real_distribution(monkeypatch):
    # The Windows code path, exercised on this POSIX host the way
    # app/main/core.test.ts exercises core.cts with platform: 'win32'.
    monkeypatch.setattr("gatepack.doctor._probe_version", lambda name, args: None)
    payload = run_doctor(platform="win32")
    # the JSON envelope shape is byte-identical to the non-Windows report —
    # only the purpose text differs, so the contract holds on Windows too.
    assert set(payload) == {"version", "tools", "resources", "allToolsPresent"}
    by_name = {t["name"]: t for t in payload["tools"]}
    for tool in payload["tools"]:
        assert set(tool) == {"name", "found", "purpose", "direct", "path", "version", "source"}
    # every EDA tool points a Windows user at a real distribution, and the
    # bash entry explains the one thing the native build can never provide.
    assert "OSS CAD Suite" in by_name["yosys"]["purpose"]
    assert "WSL2" in by_name["yosys"]["purpose"]
    assert "OSS CAD Suite" in by_name["sby"]["purpose"]
    assert "Icarus Verilog" in by_name["iverilog"]["purpose"]
    assert "WSL2" in by_name["iverilog"]["purpose"]
    assert "Icarus Verilog" in by_name["vvp"]["purpose"]
    assert "OSS CAD Suite" in by_name["z3"]["purpose"]
    assert "WSL2" in by_name["bash"]["purpose"]
    # a tool that is still "missing" on Windows says so, and says where to get it
    assert by_name["yosys"]["found"] is False
    assert by_name["yosys"]["purpose"].startswith("logic synthesis")
