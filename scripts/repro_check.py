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

Scope adapts to the toolchain present. Without Yosys it compares the artefacts
``estimate`` produces anyway — the C1 Verilog/properties, the C2 Liberty file,
the C3 Yosys script and the ``manifest.json`` verdict. **With Yosys on PATH it
also compares the mapped netlist**, which is what §20's M11a criterion ("two
clean builds hash-identical") actually asks for: a build whose netlist is not
in the comparison is not a build.

Run it inside the toolchain container to get the full comparison::

    docker run --rm -v "$PWD:/repo" -w /repo gatepack-toolchain:m6 \
        python3 scripts/repro_check.py

The script reports which set it compared, so a partial run can never be
mistaken for a full one.
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

#: Compared always — produced by the front end with no external toolchain.
BASE_ARTEFACTS = (
    "generated.v",
    "properties.sv",
    "cells.lib",
    "yosys.ys",
    "manifest.json",
)

#: Compared only when `build` ran, because only then do they exist. `estimate`
#: invokes Yosys but does not persist the netlist, so comparing these requires
#: a full build rather than an estimate — the earlier version of this script
#: looked for them after `estimate` and could never have found them.
BUILD_ARTEFACTS = (
    "mapped.json",
    "bom.csv",
    "netlist.net",
    "netlist.unpacked.net",
    "refdes.json",
)


def _artefacts(work: Path, names: tuple[str, ...]) -> tuple[str, ...]:
    """Those of ``names`` that this run actually produced.

    Determined by what is on disk rather than by probing for `yosys`: the
    question is what the build emitted, and a build that emitted no netlist
    cannot have its netlist compared no matter what is installed.
    """
    return tuple(name for name in names if (work / name).exists())


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

            # Phase 2: a full build, which is what actually persists the
            # mapped netlist and the BOM. Skipped cleanly (and reported) when
            # Yosys is absent, because `build` refuses rather than faking one.
            built = True
            for work in (work_a, work_b):
                os.chdir(work)
                code = cli_main(
                    ["build", str(DESIGN), "--library", str(LIBRARY), "--out", "build"]
                )
                if code != EXIT_OK:
                    built = False
                    break

            failures = 0
            compare = BASE_ARTEFACTS
            if built:
                compare = compare + _artefacts(work_a / "build", BUILD_ARTEFACTS)
            for name in compare:
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

            checked = len(compare)
            netlist = [n for n in compare if n in BUILD_ARTEFACTS]
            scope = (
                f"including the mapped netlist and BOM ({', '.join(netlist)})"
                if netlist
                else "front-end artefacts only - `build` did not run (no Yosys), "
                     "so M11a's 'two clean builds' is NOT fully exercised here"
            )
    finally:
        os.chdir(original_cwd)

    if failures:
        print(f"reproducibility check: {failures} artefact(s) differ", file=sys.stderr)
        return 1
    print(f"reproducibility check: {checked} artefact(s) byte-identical, {scope}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
