"""Tests for ``scripts/sign_local.py`` — the local signing path.

A maintainer with credentials on their own machine signs locally.  The script
must (a) read credentials only from the environment, (b) refuse to run when the
required credentials are absent, and (c) refuse to call a build "signed" when
the CI verification step fails.  These are logic tests — the actual macOS/Windows
codesign is unexercisable without a real certificate, and the script says so
rather than pretending.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "sign_local.py"


def _load():
    spec = importlib.util.spec_from_file_location("sign_local_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_platform_tag_mapping():
    mod = _load()
    assert mod.platform_tag("darwin") == "darwin"
    assert mod.platform_tag("win32") == "win32"
    assert mod.platform_tag("linux") == "linux"
    assert mod.platform_tag("win64") == "win32"


def test_missing_creds_lists_names_not_values():
    mod = _load()
    missing = mod.missing_creds("darwin", {"CSC_LINK": "", "CSC_KEY_PASSWORD": ""})
    assert "CSC_LINK" in missing
    assert "CSC_KEY_PASSWORD" in missing
    assert "APPLE_ID" in missing
    # Only names are ever listed — never the values.
    assert all("secret" not in m for m in missing)


def test_missing_creds_empty_when_present():
    mod = _load()
    full = {
        "CSC_LINK": "a", "CSC_KEY_PASSWORD": "b", "APPLE_ID": "c",
        "APPLE_APP_SPECIFIC_PASSWORD": "d", "APPLE_TEAM_ID": "e",
    }
    assert mod.missing_creds("darwin", full) == []
    assert mod.missing_creds("win32", {"CSC_LINK": "a", "CSC_KEY_PASSWORD": "b"}) == []
    assert mod.missing_creds("linux", {}) == []


def test_verify_command_maps_platform_to_subcommand(tmp_path):
    mod = _load()
    assert mod.verify_command("darwin", tmp_path)[2] == "macos"
    assert mod.verify_command("win32", tmp_path)[2] == "windows"
    assert mod.verify_command("linux", tmp_path)[2] == "linux"


def test_verify_signed_refuses_when_verification_fails(tmp_path):
    mod = _load()

    def fake_run(argv, **kw):
        return SimpleNamespace(returncode=1, stdout="NOT VERIFIED\n", stderr="")

    code, message = mod.verify_signed("darwin", tmp_path, runner=fake_run)
    assert code == 1
    assert "verification FAILED" in message


def test_verify_signed_accepts_when_verification_passes(tmp_path):
    mod = _load()

    def fake_run(argv, **kw):
        return SimpleNamespace(returncode=0, stdout="verified\n", stderr="")

    code, _ = mod.verify_signed("darwin", tmp_path, runner=fake_run)
    assert code == 0


def test_main_refuses_without_credentials(monkeypatch, tmp_path):
    mod = _load()
    for var in ("CSC_LINK", "CSC_KEY_PASSWORD", "APPLE_ID",
                "APPLE_APP_SPECIFIC_PASSWORD", "APPLE_TEAM_ID"):
        monkeypatch.delenv(var, raising=False)

    code = mod.main(["--platform", "darwin", "--dist", str(tmp_path)])
    assert code == 1


def test_main_linux_without_sums_refuses(tmp_path):
    mod = _load()
    code = mod.main(["--platform", "linux", "--dist", str(tmp_path)])
    assert code == 1
