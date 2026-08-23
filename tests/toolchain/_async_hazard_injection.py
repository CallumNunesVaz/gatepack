"""Fault-injection probe: the asynchronous functional check, exercised for real.

Run inside ``gatepack-toolchain:m6``; now driven by
``tests/toolchain/test_async_injection.py`` (the real test) and kept as the
evidence behind the acceptance criterion: a wrong-but-hazard-free cover must
*now* fail the verification, where before Package L it shipped green.

The fault is injected where a real defect would sit: one product term is dropped
from the cover *after* z3 selected it, exactly what a bug in the covering
constraints would do.  The resulting netlist is still hazard-free (both hazard
checks pass), but it no longer implements the specified machine — and the new
exhaustive fundamental-mode check is what catches that.  This probe does not
demonstrate a defect in the hazard checker: hazards are all it claims to check,
and it checks them.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

from gatepack.frontend import frontend
from gatepack.liberty import generator
from gatepack.parts import load_parts
from gatepack.toolchain import ToolchainRunner


def _drop_a_cube(original):
    """Wrap ``build_covers`` so the largest cube of the first cover is dropped."""

    def wrapper(*args, **kwargs):
        wrapper.calls += 1
        result = original(*args, **kwargs)
        covers = list(result.covers)
        for i, cover in enumerate(covers):
            if len(cover.cubes) > 1:
                widest = max(cover.cubes, key=lambda c: sum(1 for v in c if v != -1))
                covers[i] = replace(
                    cover, cubes=tuple(c for c in cover.cubes if c != widest)
                )
                break
        else:
            raise SystemExit("no cover had more than one cube; injection impossible")
        return replace(result, covers=tuple(covers))

    wrapper.calls = 0
    return wrapper


def run_probe() -> dict:
    design = Path("examples/async_latch/design.yaml")
    workdir = Path(".gpout/async_inject")
    workdir.mkdir(parents=True, exist_ok=True)

    compiled = frontend.compile_design_file(design).compiled

    parts = load_parts("libraries/74aup.csv")
    lib = generator.generate(parts)
    lib_text = getattr(lib, "text", lib)

    from gatepack.verify.asynchronous import cell_functions_from_liberty

    cell_functions = cell_functions_from_liberty(lib_text)

    from gatepack import async_pipeline
    from gatepack.synth import asynchronous as backend

    out = {"injected": True}

    # Control: the unpatched pipeline must pass, or the experiment proves nothing.
    clean = async_pipeline.run_async_pipeline(
        compiled, ToolchainRunner(), workdir / "clean", cell_functions
    )
    out["control_hazard_passed"] = clean.hazard_passed
    out["control_checks"] = [(c.name, c.status.value) for c in clean.hazard_checks]

    injected = _drop_a_cube(backend.build_covers)
    backend.build_covers = injected
    faulty = async_pipeline.run_async_pipeline(
        compiled, ToolchainRunner(), workdir / "faulty", cell_functions
    )
    out["injection_calls"] = injected.calls
    out["cover_cubes_clean"] = [len(c.cubes) for c in clean.covers.covers]
    out["cover_cubes_faulty"] = [len(c.cubes) for c in faulty.covers.covers]
    out["faulty_hazard_passed"] = faulty.hazard_passed
    out["faulty_checks"] = [(c.name, c.status.value) for c in faulty.hazard_checks]

    try:
        faulty.netlist()
        out["netlist_accessor"] = "RETURNED A NETLIST"
    except Exception as exc:  # noqa: BLE001 - the type is asserted by the caller
        out["netlist_accessor"] = type(exc).__name__
        out["netlist_reason"] = str(exc)[:300]

    return out


def main() -> int:
    out = run_probe()
    print(json.dumps(out, indent=2))
    # The acceptance criterion: the injection must now FAIL the functional check
    # and the netlist must not be obtainable.  A probe run that no longer shows
    # this is itself a failure.
    checks = dict(out["faulty_checks"])
    ok = (
        dict(out["control_checks"]).get("functional (fundamental mode)") == "passed"
        and checks.get("functional (fundamental mode)") == "failed"
        and out["netlist_accessor"] == "HazardFailed"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
