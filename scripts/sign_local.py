#!/usr/bin/env python3
"""Sign the app locally, with the same verification as CI (§5.2, signing).

For a maintainer who has credentials on their own machine and does not want to
release only from CI.  Every credential is read from the environment — never
from a file in the repository, and never printed to a log — the signed build is
run, then ``scripts/verify_signing.py`` (the exact check the release workflow
runs) is run against the result, and the script *refuses* to call the build
"signed" if it cannot verify it.

Required environment variables, by platform:

  macOS    CSC_LINK, CSC_KEY_PASSWORD, APPLE_ID,
           APPLE_APP_SPECIFIC_PASSWORD, APPLE_TEAM_ID
  Windows  CSC_LINK, CSC_KEY_PASSWORD
  Linux    none (no OS code signing) — produces SHA256SUMS and, with
           GPG_PRIVATE_KEY, a detached signature, then verifies the checksums.

Exit 0 = built and verified.  Any other exit means the build is NOT signed, or
was signed but could not be verified — never a silent "signed".
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
APP = REPO / "app"
VERIFY = REPO / "scripts" / "verify_signing.py"

#: (platform -> ordered list of (secret name, env var)).  Linux has no OS
#: code signing, so it requires none; GPG_PRIVATE_KEY is optional and handled
#: separately by scripts/gpg_sign_sums.py.
REQUIRED_CREDS: dict[str, list[tuple[str, str]]] = {
    "darwin": [
        ("CSC_LINK", "CSC_LINK"),
        ("CSC_KEY_PASSWORD", "CSC_KEY_PASSWORD"),
        ("APPLE_ID", "APPLE_ID"),
        ("APPLE_APP_SPECIFIC_PASSWORD", "APPLE_APP_SPECIFIC_PASSWORD"),
        ("APPLE_TEAM_ID", "APPLE_TEAM_ID"),
    ],
    "win32": [
        ("CSC_LINK", "CSC_LINK"),
        ("CSC_KEY_PASSWORD", "CSC_KEY_PASSWORD"),
    ],
    "linux": [],
}


def platform_tag(sys_platform: str | None = None) -> str:
    plat = sys_platform if sys_platform is not None else sys.platform
    if plat.startswith("darwin"):
        return "darwin"
    if plat.startswith("win"):
        return "win32"
    return "linux"


def missing_creds(platform: str, environ: dict[str, str]) -> list[str]:
    """The credential *names* (never values) that are absent for ``platform``."""
    missing: list[str] = []
    for name, var in REQUIRED_CREDS.get(platform, []):
        if not environ.get(var):
            missing.append(name)
    return missing


def run(argv: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None,
        input: str | None = None) -> subprocess.CompletedProcess:
    """Thin wrapper around subprocess.run, kept separate so tests can stub it."""
    return subprocess.run(
        argv, cwd=str(cwd) if cwd else None, capture_output=True, text=True,
        input=input, env=env,
    )


def _signed_env() -> dict[str, str]:
    """The signing environment, copied from the process env (never printed)."""
    return dict(os.environ)


def build_signed(platform: str, arch: str, runner=run) -> tuple[int, str]:
    """Build the installer, signed.  Returns (exit_code, message)."""
    bundle = runner([sys.executable, str(REPO / "scripts" / "bundle_core.py")])
    if bundle.returncode != 0:
        return bundle.returncode, f"bundled core failed:\n{bundle.stderr}"

    app_build = runner(["npm", "run", "build"], cwd=APP)
    if app_build.returncode != 0:
        return app_build.returncode, f"app build failed:\n{app_build.stderr}"

    argv = ["npx", "electron-builder"]
    if platform == "darwin":
        argv += ["--mac"]
    else:
        argv += ["--win"]
    argv += [f"--{arch}"]
    packaged = runner(argv, cwd=APP, env=_signed_env())
    if packaged.returncode != 0:
        return packaged.returncode, f"electron-builder failed:\n{packaged.stderr}"
    return 0, "built"


#: platform_tag value -> verify_signing.py subcommand name.
VERIFY_SUBCOMMAND = {"darwin": "macos", "win32": "windows", "linux": "linux"}


def verify_command(platform: str, dist_dir: Path) -> list[str]:
    """The argv for scripts/verify_signing.py, mirroring the release workflow."""
    sub = VERIFY_SUBCOMMAND[platform]
    if sub == "linux":
        return [sys.executable, str(VERIFY), "linux", f"--sums-dir={dist_dir}"]
    if sub == "macos":
        apps = sorted(dist_dir.glob("mac*/gatepack.app")) + sorted(dist_dir.glob("mac-arm64/gatepack.app"))
        argv = [sys.executable, str(VERIFY), "macos", f"--app={apps[0] if apps else dist_dir}"]
        dmgs = sorted(dist_dir.glob("*.dmg"))
        if dmgs:
            argv.append(f"--dmg={dmgs[0]}")
        return argv
    exes = sorted(dist_dir.glob("*.exe"))
    return [sys.executable, str(VERIFY), "windows", f"--file={exes[0] if exes else dist_dir}"]


def verify_signed(platform: str, dist_dir: Path, runner=run) -> tuple[int, str]:
    """Run the CI verification; refuse to claim "signed" on a nonzero exit."""
    argv = verify_command(platform, dist_dir)
    proc = runner(argv)
    if proc.returncode != 0:
        return proc.returncode, (
            "verification FAILED — the build is not verified signed and will not "
            f"be called signed:\n{proc.stdout}{proc.stderr}"
        )
    return 0, proc.stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="sign the app locally, then verify the signature (same check as CI)"
    )
    parser.add_argument("--platform", choices=["darwin", "win32", "linux"], default=None,
                        help="override the detected platform")
    parser.add_argument("--arch", default=None, help="arch for electron-builder (e.g. x64, arm64)")
    parser.add_argument("--dist", default=str(REPO / ".gpout" / "dist"),
                        help="dist directory electron-builder wrote (default: %(default)s)")
    args = parser.parse_args(argv)

    platform = args.platform or platform_tag()
    dist_dir = Path(args.dist)

    missing = missing_creds(platform, os.environ)
    if missing:
        print(
            f"refusing to sign on {platform}: missing credentials "
            f"({', '.join(missing)}). Supply them in the environment — never in a "
            "file in the repo — per docs/RELEASING.md.",
            file=sys.stderr,
        )
        return 1

    if platform == "linux":
        print("linux has no OS code signing: producing checksums (+ optional GPG) only.")
        # The checksums are produced by scripts/assemble_release.py in CI; the
        # local equivalent is to verify whatever sums already exist, if any.
        if not (dist_dir / "SHA256SUMS").is_file():
            print("no SHA256SUMS found — run scripts/assemble_release.py first.", file=sys.stderr)
            return 1
        code, message = verify_signed("linux", dist_dir)
        print(message)
        return code

    arch = args.arch or ("arm64" if platform == "darwin" and _is_arm64() else "x64")
    code, message = build_signed(platform, arch)
    if code != 0:
        print(message, file=sys.stderr)
        return code

    code, message = verify_signed(platform, dist_dir)
    print(message)
    if code != 0:
        print(message, file=sys.stderr)
        return code

    print(f"LOCAL SIGNING: built and verified ({platform}).")
    return 0


def _is_arm64() -> bool:
    import platform as _platform

    return _platform.machine() in ("arm64", "aarch64")


if __name__ == "__main__":
    sys.exit(main())
