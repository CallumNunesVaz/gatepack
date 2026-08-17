"""One place to build every ``docker run`` in the toolchain suite.

The pinned toolchain container mounts a directory out of the checkout and runs a
command inside it.  If it runs as *root* (docker's default), everything it
writes back — ``build/``, ``.gpout/``, stray ``__pycache__`` — is owned by root,
and the developer's next *local* ``gatepack`` command fails with
``[Errno 13] Permission denied``.  The fix is a single flag, ``-u <uid>:<gid>``,
the same one ``scripts``' ``start`` already passes and that ``test_examples.py``
inlined when it was fixed in passing.  This module centralises it so no call
site can forget it again: the tests express *what* to run, never *how* the
container is invoked.

``os.getuid``/``os.getgid`` do not exist on Windows, where these tests still run
under Docker Desktop.  Rather than skip (which would hide the whole suite on a
platform that can still exercise the real toolchain), the helper falls back to
the image default there: a Windows bind mount has no POSIX ownership, so the
root-owned-artefact defect this flag exists to prevent cannot occur on that
platform anyway.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

IMAGE = "gatepack-toolchain:m6"
REPO = Path(__file__).resolve().parents[2]


def _user_spec() -> str | None:
    """``uid:gid`` for ``-u``, or ``None`` to run as the image default."""
    try:
        return f"{os.getuid()}:{os.getgid()}"
    except AttributeError:  # Windows: no uid/gid, and the defect is POSIX-only
        return None


def run(
    *argv: str,
    host_dir: Path,
    container_dir: str,
    workdir: str | None = None,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run ``argv`` inside ``IMAGE`` with ``host_dir`` mounted at ``container_dir``.

    The invoking user's uid/gid is passed as ``-u`` (when the platform has one)
    so nothing the container writes comes back root-owned.
    """
    cmd: list[str] = ["docker", "run", "--rm"]
    user = _user_spec()
    if user is not None:
        cmd += ["-u", user]
    cmd += ["-v", f"{host_dir}:{container_dir}"]
    if workdir is not None:
        cmd += ["-w", workdir]
    cmd += [IMAGE, *argv]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def run_repo(
    *argv: str, timeout: int | None = None
) -> subprocess.CompletedProcess[str]:
    """Run ``argv`` with the checkout mounted at ``/repo``, working there."""
    return run(*argv, host_dir=REPO, container_dir="/repo", workdir="/repo", timeout=timeout)


def run_work(
    host_dir: Path, *argv: str, timeout: int | None = None
) -> subprocess.CompletedProcess[str]:
    """Run ``argv`` with ``host_dir`` mounted at ``/work`` (no workdir override)."""
    return run(*argv, host_dir=host_dir, container_dir="/work", timeout=timeout)
