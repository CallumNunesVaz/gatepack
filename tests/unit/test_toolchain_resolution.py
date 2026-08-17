"""Tests for tool resolution (env -> bundled -> system) and the run environment.

Nothing here runs a real EDA binary: the "tools" are shell scripts in a temp
directory, and the bundled-location lookup is monkeypatched.  What is exercised
is the precedence itself and the fact that a bundled binary is *not* run bare —
its library directory is surfaced through ``LD_LIBRARY_PATH`` and its own
directory through ``PATH``, so a bundled sby reaches a bundled yosys rather than
a host one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import gatepack.toolchain as tc
from gatepack.toolchain import (
    GATEPACK_TOOLS_ENV,
    ToolchainRunner,
    ToolResolution,
    build_run_env,
    resolve_tool,
)


def _make_tool(directory: Path, name: str, body: str = "#!/bin/sh\necho ran\n") -> Path:
    tool = directory / name
    tool.write_text(body)
    tool.chmod(0o755)
    return tool


@pytest.fixture
def bundled(monkeypatch, tmp_path) -> Path:
    d = tmp_path / "bundled"
    d.mkdir()
    _make_tool(d, "yosys")
    _make_tool(d, "iverilog")
    (d / "lib").mkdir()
    monkeypatch.setattr(tc, "bundled_toolchain_dir", lambda: d)
    return d


def test_resolve_tool_prefers_bundled_over_path(bundled, monkeypatch, tmp_path):
    system = tmp_path / "system"
    system.mkdir()
    _make_tool(system, "yosys", "#!/bin/sh\necho system\n")
    monkeypatch.setattr(tc.shutil, "which", lambda name, path=None: str(system / name))

    res = resolve_tool("yosys")
    assert res is not None
    assert res.source == "bundled"
    assert res.path == str(bundled / "yosys")
    assert res.libdir == str(bundled / "lib")
    assert res.tooldir == str(bundled)


def test_resolve_tool_prefers_env_dir_over_bundled(bundled, monkeypatch, tmp_path):
    env_dir = tmp_path / "env"
    env_dir.mkdir()
    _make_tool(env_dir, "yosys", "#!/bin/sh\necho env\n")

    res = resolve_tool("yosys", environ={GATEPACK_TOOLS_ENV: str(env_dir)})
    assert res is not None
    assert res.source == "env"
    assert res.path == str(env_dir / "yosys")


def test_resolve_tool_falls_back_to_path(bundled, monkeypatch, tmp_path):
    # a tool present only on PATH resolves as "system" with no lib/tooldir
    system = tmp_path / "system"
    system.mkdir()
    _make_tool(system, "z3")
    monkeypatch.setattr(tc.shutil, "which", lambda name, path=None: str(system / name))

    res = resolve_tool("z3")
    assert res is not None
    assert res.source == "system"
    assert res.path == str(system / "z3")
    assert res.libdir is None
    assert res.tooldir is None


def test_resolve_tool_returns_none_when_nowhere(bundled, monkeypatch):
    monkeypatch.setattr(tc.shutil, "which", lambda name, path=None: None)
    assert resolve_tool("espresso") is None


def test_build_run_env_prepends_lib_and_tool_dirs():
    res = ToolResolution("yosys", "/tools/yosys", "bundled", "/tools/lib", "/tools")
    env = build_run_env(res, base_env={"PATH": "/usr/bin", "LD_LIBRARY_PATH": "/x"})
    assert env is not None
    # bundled dir first, then the inherited PATH, then the base system dirs —
    # explicitly, so a bundled sby can still find a POSIX shell under a scrubbed
    # PATH (nothing here relies on inheritance).
    assert env["PATH"] == "/tools:/usr/bin:/bin:/usr/local/bin"
    assert env["LD_LIBRARY_PATH"] == "/tools/lib:/x"


def test_build_run_env_adds_system_dirs_to_empty_path():
    res = ToolResolution("yosys", "/tools/yosys", "bundled", "/tools/lib", "/tools")
    env = build_run_env(res, base_env={"PATH": ""})
    assert env is not None
    assert env["PATH"] == "/tools:/bin:/usr/bin:/usr/local/bin"


def test_build_run_env_is_none_for_system_copy():
    res = ToolResolution("yosys", "/usr/bin/yosys", "system")
    assert build_run_env(res) is None


def test_resolve_tool_host_requirement_by_absolute_path(monkeypatch, tmp_path):
    # a host requirement (bash) is found by absolute path even when PATH is empty
    monkeypatch.setattr(tc.shutil, "which", lambda name, path=None: None)
    res = resolve_tool("bash", environ={"PATH": ""})
    assert res is not None
    assert res.source == "system"
    assert Path(res.path).name == "bash"


def test_runner_runs_bundled_copy_with_environment(bundled, tmp_path, monkeypatch):
    # a bundled yosys that reports the environment it was given; the runner must
    # substitute the bundled path for the bare name and set LD_LIBRARY_PATH/PATH.
    script = (
        "#!/bin/sh\n"
        'echo "path=$PATH"\n'
        'echo "ld=$LD_LIBRARY_PATH"\n'
        'echo "argv0=$0"\n'
    )
    _make_tool(bundled, "yosys", script)
    monkeypatch.setattr(tc.shutil, "which", lambda name, path=None: None)

    runner = ToolchainRunner()
    result = runner.run(["yosys", "-p", "help"], cwd=".")
    assert result.returncode == 0
    assert f"ld={bundled / 'lib'}" in result.stdout
    path_line = result.stdout.splitlines()[0]
    assert path_line.startswith(f"path={bundled}:")
    assert "/bin" in path_line and "/usr/bin" in path_line
    assert f"argv0={bundled / 'yosys'}" in result.stdout


def test_runner_reports_missing_tool_not_fabricated(bundled, monkeypatch):
    monkeypatch.setattr(tc.shutil, "which", lambda name, path=None: None)
    result = ToolchainRunner().run(["espresso", "x"], cwd=".")
    assert result.returncode == -1
    assert "espresso" in result.stderr
    assert result.stdout == ""


def test_runner_honors_injected_which(bundled):
    runner = ToolchainRunner(which=lambda _name: None)
    assert runner.available("yosys") is False
    runner = ToolchainRunner(which=lambda _name: "/nonexistent/yosys")
    result = runner.run(["yosys", "-p", "help"], cwd=".")
    assert result.returncode == -1
    assert result.stderr
