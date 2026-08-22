"""Tests for the injectable toolchain module (gatepack.toolchain).

The command *line* is a pure function of its inputs, so it can be asserted
without the binary present.  Nothing here runs a real tool; that stays behind
:class:`ToolchainRunner`, which is injected where tools would run.
"""

from __future__ import annotations

from gatepack.toolchain import (
    ToolResult,
    ToolchainRunner,
    iverilog_command,
    vvp_command,
    yosys_command,
)


def test_yosys_command_is_a_pure_function_of_the_script():
    assert yosys_command("read_verilog foo.v") == ["yosys", "-p", "read_verilog foo.v"]


def test_iverilog_command_lists_sources_in_order():
    cmd = iverilog_command("out.vvp", ["mapped.v", "cells_sim.v", "tb.v"])
    assert cmd == ["iverilog", "-o", "out.vvp", "mapped.v", "cells_sim.v", "tb.v"]


def test_vvp_command():
    assert vvp_command("out.vvp") == ["vvp", "out.vvp"]


def test_runner_available_and_run_without_binary():
    # A fake `which` that reports nothing available, so no tool is ever invoked.
    runner = ToolchainRunner(which=lambda _name: None)
    assert runner.available("yosys") is False
    assert runner.available("iverilog") is False


def test_runner_run_failure_is_a_tool_result_not_an_exception():
    runner = ToolchainRunner(which=lambda _name: "/nonexistent/yosys")
    result = runner.run(["yosys", "-p", "help"], cwd=".")
    assert isinstance(result, ToolResult)
    assert result.returncode == -1
    assert result.stderr  # the OSError text, never a fabricated pass


def test_bundled_windows_tool_is_found_by_its_exe_name(tmp_path, monkeypatch):
    """A bundled Windows toolchain ships ``yosys.exe``, and must be found.

    ``shutil.which`` applies ``PATHEXT`` on the ``PATH`` branch, so a *system*
    install on Windows always worked. The bundled and ``GATEPACK_TOOLS``
    branches look the file up directly and used a bare ``d / name``, so they
    found nothing — which is exactly the self-contained case a Windows
    installer exists to serve.
    """
    from gatepack import toolchain

    tools = tmp_path / "bin"
    tools.mkdir()
    exe = tools / "yosys.exe"
    exe.write_text("")
    exe.chmod(0o755)

    env = {toolchain.GATEPACK_TOOLS_ENV: str(tools)}

    # Windows: the `.exe` is found.
    found = toolchain.resolve_tool("yosys", environ=env, platform="win32")
    assert found is not None
    assert found.path == str(exe)
    assert found.source == "env"

    # POSIX: `yosys.exe` is NOT a match for `yosys` — the suffix rule is
    # platform-specific, not a blanket fallback that would mask a missing tool.
    monkeypatch.setattr(toolchain.shutil, "which", lambda _name: None)
    assert toolchain.resolve_tool("yosys", environ=env, platform="linux") is None


def test_a_suffixless_tool_still_wins_on_windows(tmp_path):
    """An extensionless file is preferred, so POSIX layouts keep working."""
    from gatepack import toolchain

    tools = tmp_path / "bin"
    tools.mkdir()
    for name in ("yosys", "yosys.exe"):
        p = tools / name
        p.write_text("")
        p.chmod(0o755)

    found = toolchain.resolve_tool(
        "yosys", environ={toolchain.GATEPACK_TOOLS_ENV: str(tools)}, platform="win32"
    )
    assert found is not None
    assert found.path == str(tools / "yosys")
