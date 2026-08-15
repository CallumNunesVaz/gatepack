#!/usr/bin/env python3
"""Reproducibility check (§5.5, R7; §C6).

Runs ``gatepack estimate`` twice on the same golden design and library, in two
different working directories with the same *relative* build path, then compares
the produced artefacts byte-for-byte.  Any mismatch fails the check.

Using a relative build path is deliberate: the C3 Yosys script embeds the build
directory path, so the comparison must hold the path constant while varying the
location to prove the content is otherwise deterministic.  Determinism of the
payload is guaranteed by construction (sorted JSON output, no timestamps, §C6);
this script verifies it rather than asserting it.

Scope: only the artefacts ``estimate`` produces *without* Yosys — the C1
Verilog/properties, the C2 Liberty file, the C3 Yosys script, and the
``manifest.json`` verdict.  Byte-reproducibility of the *mapped* netlist
(``mapped.json`` / ``mapped.v``) depends on the pinned Yosys container (M0) and
is documented in docs/REPRODUCIBILITY.md, not tested here.
"""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from gatepack.cli import EXIT_OK, main as cli_main  # noqa: E402

DESIGN = REPO / "tests" / "golden" / "designs" / "traffic_light.yaml"
LIBRARY = REPO / "libraries" / "74aup.csv"

ARTEFACTS = (
    "generated.v",
    "properties.sv",
    "cells.lib",
    "yosys.ys",
    "manifest.json",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if not DESIGN.exists():
        print(f"error: golden design not found: {DESIGN}", file=sys.stderr)
        return 1

    original_cwd = os.getcwd()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            work_a = base / "a"
            work_b = base / "b"
            work_a.mkdir()
            work_b.mkdir()

            for work in (work_a, work_b):
                os.chdir(work)
                code = cli_main(
                    ["estimate", str(DESIGN), "--library", str(LIBRARY), "--build", "build"]
                )
                if code != EXIT_OK:
                    print(f"error: estimate exited {code} in {work}", file=sys.stderr)
                    return 1

            failures = 0
            for name in ARTEFACTS:
                a = work_a / "build" / name
                b = work_b / "build" / name
                if not a.exists() or not b.exists():
                    print(f"FAIL {name}: missing artefact", file=sys.stderr)
                    failures += 1
                    continue
                if _sha256(a) == _sha256(b):
                    print(f"ok   {name}: identical")
                else:
                    print(f"FAIL {name}: differs between builds", file=sys.stderr)
                    failures += 1
    finally:
        os.chdir(original_cwd)

    if failures:
        print(f"reproducibility check: {failures} artefact(s) differ", file=sys.stderr)
        return 1
    print(f"reproducibility check: {len(ARTEFACTS)} artefact(s) byte-identical")
    return 0


if __name__ == "__main__":
    sys.exit(main())
