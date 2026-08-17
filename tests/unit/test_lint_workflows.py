"""Tests for ``scripts/lint_workflows.py`` — the guard that keeps the workflow
YAML from silently breaking.

The release workflow is the one place a signing step can be dropped without a
single pytest noticing (the workflows are not executed by pytest).  These tests
pin that (a) the real workflow files parse, (b) a YAML syntax break is caught,
(c) a workflow that drops the verification or the unsigned marker is flagged,
and (d) block-scalar ``run:`` bodies are preserved so the structural checks can
actually see the commands they are guarding.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "lint_workflows.py"


def _load():
    spec = importlib.util.spec_from_file_location("lint_workflows_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _good_tree() -> dict:
    return {
        "jobs": {
            "build": {
                "strategy": {
                    "matrix": {
                        "include": [
                            {"platform": "linux"},
                            {"platform": "macos"},
                            {"platform": "macos"},
                            {"platform": "windows"},
                        ]
                    }
                },
                "steps": [
                    {"name": "Build installer — UNSIGNED (no credentials)", "run": "npx electron-builder"},
                    {"name": "Build installer — SIGNED + notarized", "run": "npx electron-builder"},
                    {"name": "Verify signature — macOS", "run": "python scripts/verify_signing.py macos --app x"},
                    {"name": "Stage artefacts", "run": "echo unsigned > .gpout/staging/SIGNING-STATUS.txt"},
                ],
            },
            "publish": {"steps": []},
        }
    }


def test_real_workflows_lint_clean():
    mod = _load()
    assert mod.lint(mod.WORKFLOWS_DIR) == 0


def test_broken_indentation_is_caught():
    mod = _load()
    with pytest.raises(mod.WorkflowLintError):
        mod.load_workflow("jobs:\n    build:\n   bad-indent: x\n")


def test_tab_indentation_is_caught():
    mod = _load()
    with pytest.raises(mod.WorkflowLintError):
        mod.load_workflow("jobs:\n\tbuild: x\n")


def test_block_scalar_content_is_preserved():
    mod = _load()
    tree = mod.load_workflow(
        "jobs:\n"
        "  build:\n"
        "    steps:\n"
        "      - name: verify\n"
        "        run: |\n"
        "          python scripts/verify_signing.py macos\n"
        "          echo done\n"
    )
    run = tree["jobs"]["build"]["steps"][0]["run"]
    assert "verify_signing.py" in run


def test_missing_verify_step_is_flagged():
    mod = _load()
    tree = _good_tree()
    tree["jobs"]["build"]["steps"] = [
        s for s in tree["jobs"]["build"]["steps"]
        if "verify_signing.py" not in (s.get("run") or "")
    ]
    problems = mod.release_structure_problems(tree)
    assert any("verify_signing.py" in p for p in problems)


def test_missing_unsigned_marker_is_flagged():
    mod = _load()
    tree = _good_tree()
    tree["jobs"]["build"]["steps"] = [
        s for s in tree["jobs"]["build"]["steps"]
        if "SIGNING-STATUS.txt" not in (s.get("run") or "")
    ]
    problems = mod.release_structure_problems(tree)
    assert any("SIGNING-STATUS.txt" in p for p in problems)


def test_good_tree_has_no_problems():
    mod = _load()
    assert mod.release_structure_problems(_good_tree()) == []


def test_unbalanced_flow_bracket_is_caught():
    mod = _load()
    with pytest.raises(mod.WorkflowLintError):
        mod.load_workflow("on:\n  push:\n    tags: [\"v*\"]\n  pull_request: [\n")
