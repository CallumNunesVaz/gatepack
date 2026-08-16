"""`gatepack verify` against a real Yosys, at several ``--build`` depths.

``gatepack build`` had this bug and fixed it (see ``test_build_paths.py``):
``_synthesize`` ran Yosys with ``cwd=out.parent`` while the generated script
holds paths relative to the *invocation* directory, so ``--out build`` worked
and ``--out x/y`` did not — reported as "synthesis unavailable".

``verify`` had the same bug, but its failure was worse to read: ``run_verify``
ignored the synthesis return code, so a nested ``--build`` path that made Yosys
never write ``mapped.json``/``mapped.v`` cascaded into the equivalence check
reading a non-existent ``mapped.v`` and reported ``equivalence: failed`` — a
broken *path* dressed up as a broken *proof*.

The fix keeps the build dir relative to the invocation directory and runs every
tool from there too (no ``.resolve()``, no ``cwd=build_dir.parent``), matching
``build.py``.  ``yosys.ys`` must therefore embed the *relative* build path: an
absolute path there means someone reverted to the ``.resolve()`` workaround,
which masked the bug rather than fixing it and broke byte-reproducibility.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
IMAGE = "gatepack-toolchain:m6"


def _toolchain_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(
        ["docker", "image", "inspect", IMAGE], capture_output=True
    ).returncode == 0


requires_toolchain = pytest.mark.skipif(
    not _toolchain_available(),
    reason=f"toolchain image {IMAGE} not available; see Dockerfile.probe",
)


def _verify(build: str, design: str = "xor2") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{REPO}:/repo", "-w", "/repo", IMAGE,
            "python3", "-m", "gatepack", "verify",
            f"tests/golden/designs/{design}.yaml",
            "--library", "libraries/74aup.csv",
            "--build", build,
        ],
        capture_output=True,
        text=True,
    )


def _read(build: str, name: str) -> str:
    return subprocess.run(
        [
            "docker", "run", "--rm", "-v", f"{REPO}:/repo", "-w", "/repo", IMAGE,
            "cat", f"{build}/{name}",
        ],
        capture_output=True,
        text=True,
    ).stdout


@requires_toolchain
@pytest.mark.parametrize(
    "build",
    [
        ".gpout/tv_flat",
        ".gpout/tv_nested/one",
        ".gpout/tv_nested/one/two/three",
    ],
)
def test_verify_succeeds_at_any_output_depth(build: str) -> None:
    proc = _verify(build)
    assert proc.returncode == 0, (
        f"verify failed for --build {build}:\n{proc.stderr or proc.stdout}"
    )
    # The failure mode this guards: a broken path must never read as a broken
    # proof.  If equivalence reports "failed" here, synthesis silently failed
    # to write mapped.v and the check is blaming the proof for the path.
    assert "equivalence:               failed" not in proc.stdout
    assert "equivalence:               passed" in proc.stdout
    assert "manifest:" in proc.stdout


@requires_toolchain
def test_verify_script_embeds_relative_build_path() -> None:
    """``yosys.ys`` must carry the relative build path, not an absolute one.

    The absolute-path form is the ``.resolve()`` workaround that masked the
    nested-path bug: it made the paths resolve regardless of the working
    directory, so the wrong-``cwd`` bug went unnoticed while silently breaking
    byte-reproducibility of the generated script.
    """
    build = ".gpout/tv_relative"
    proc = _verify(build)
    assert proc.returncode == 0, proc.stderr or proc.stdout
    script = _read(build, "yosys.ys")
    assert f"read_verilog -sv {build}/generated.v" in script, script
    assert "/repo/" not in script, script


@requires_toolchain
def test_verify_properties_close_on_a_nested_path() -> None:
    """sby [files] resolution must survive a nested build dir too.

    The property driver writes ``.sby`` files whose ``[files]`` entries are the
    relative ``generated.v``/``properties.sv`` paths and runs ``sby`` from the
    invocation directory.  A nested path that broke those (e.g. by resolving
    ``[files]`` against ``build_dir.parent`` instead of the invocation
    directory) would report every property ``not run`` while equivalence still
    passed — a second way the same path bug could hide.
    """
    build = ".gpout/tv_props/nested"
    proc = _verify(build, design="traffic_light")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "property one_light_only:   passed" in proc.stdout
    sby = _read(build, "properties_gp_assert_0.sby")
    assert f"{build}/generated.v" in sby, sby
