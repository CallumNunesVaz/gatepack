"""Fault-injection probe: what the asynchronous verify path does NOT check.

Run by hand inside ``gatepack-toolchain:m6``; kept because it is the evidence
behind a recorded gap, not because it asserts anything.

The intent was to make a genuinely hazardous netlist reach stage 5 through the
real pipeline, since stage 4 builds the cover under the required-cube condition
and so never produces one — meaning the refusal path had never actually fired.
The fault is injected where a real defect would sit: one product term is dropped
from the cover *after* z3 selected it, exactly what a bug in the covering
constraints would do.

What it measured instead, 2026-08-24, is more useful:

    cover cubes, clean run   [1, 2]
    cover cubes, faulty run  [1, 1]      <- the injection fired
    hazard (ternary)         passed
    hazard (glitch sim)      passed
    netlist accessor         RETURNED A NETLIST

Dropping a cube changes the *function*; it does not necessarily make the
circuit hazardous. So the netlist no longer implements the specified machine,
and the asynchronous verify path reports:

    verification: passed
      equivalence:        not applicable
      hazard (ternary):   passed
      hazard (glitch sim): passed

There is no functional check on the asynchronous path — no equivalence (there
is no synchronous golden) and no exhaustive simulation against the flow table.
A stage-4 bug that yields a wrong but hazard-free cover therefore ships green.
See docs/handoff/prompt-asyncfunc.md.

This probe does not demonstrate a defect in the hazard checker: hazards are all
it claims to check, and it checks them.
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


def main() -> int:
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
    out["verilog_differs"] = (
        (workdir / "clean" / "async_mapped.v").read_text()
        != (workdir / "faulty" / "async_mapped.v").read_text()
    ) if (workdir / "clean" / "async_mapped.v").exists() else "no async_mapped.v"
    out["faulty_hazard_passed"] = faulty.hazard_passed
    out["faulty_checks"] = [(c.name, c.status.value) for c in faulty.hazard_checks]

    try:
        faulty.netlist()
        out["netlist_accessor"] = "RETURNED A NETLIST"
    except Exception as exc:  # noqa: BLE001 - the type is asserted by the caller
        out["netlist_accessor"] = type(exc).__name__
        out["netlist_reason"] = str(exc)[:300]

    out["deliverables_in_faulty_dir"] = sorted(
        p.name for p in (workdir / "faulty").iterdir() if p.suffix in {".net", ".csv"}
    )
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
