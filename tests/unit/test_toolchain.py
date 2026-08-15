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
