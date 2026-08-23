"""The asynchronous backend against the *real* toolchain (z3 + Icarus).

Every claim here closes under ``gatepack-toolchain:m6`` (z3 4.8.12, Icarus 11):
the single-variable-change assignment, the cover, determinism, and both hazard
checks.  Nothing is faked; a missing container skips cleanly.
"""

from __future__ import annotations

import shutil
import subprocess
import textwrap

import pytest

from tests.toolchain.docker_runner import IMAGE, run_repo


def _toolchain_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return (
        subprocess.run(
            ["docker", "image", "inspect", IMAGE], capture_output=True
        ).returncode
        == 0
    )


requires_toolchain = pytest.mark.skipif(
    not _toolchain_available(),
    reason=f"toolchain image {IMAGE} not available; see Dockerfile.probe",
)


def _run_python(script: str) -> subprocess.CompletedProcess[str]:
    return run_repo("python3", "-c", textwrap.dedent(script))


_LATCH_PROBE = """
import json
from pathlib import Path
from gatepack.frontend import yaml_subset, model as model_mod
from gatepack.frontend.schema import Design
from gatepack.async_pipeline import run_async_pipeline
from gatepack.parts import load_parts
from gatepack.liberty.generator import generate as generate_liberty
from gatepack.verify.asynchronous import cell_functions_from_liberty
from gatepack.toolchain import ToolchainRunner


def compile_async(path):
    node = yaml_subset.parse(Path(path).read_text())
    design = Design.model_validate(yaml_subset.to_python(node))
    return model_mod.compile_design(design, source_name=path, provenance={})

compiled = compile_async('tests/golden/designs/async_latch.yaml')
parts = load_parts('libraries/74aup.csv')
lib = generate_liberty(parts, library_name="gatepack",
                       project_vcc=compiled.design.constraints.vcc)
cell_funcs = cell_functions_from_liberty(lib.text)
runner = ToolchainRunner()
r1 = run_async_pipeline(compiled, runner, workdir='.gpout/async_tc', cell_functions=cell_funcs)
r2 = run_async_pipeline(compiled, runner, workdir='.gpout/async_tc', cell_functions=cell_funcs)
assert dict(r1.assignment.codes) == dict(r2.assignment.codes), "codes not deterministic"
assert r1.mapped_verilog() == r2.mapped_verilog(), "netlist not deterministic"
assert r1.mapped_json() == r2.mapped_json(), "mapped.json not deterministic"
assert r1.hazard_passed, [c.name + '=' + c.status.value for c in r1.hazard_checks]
statuses = {c.name: c.status.value for c in r1.hazard_checks}
assert statuses['hazard (ternary)'] == 'passed', statuses
assert statuses['hazard (glitch sim)'] == 'passed', statuses
print('ASYNC_LATCH_OK', json.dumps(dict(r1.assignment.codes)), r1.assignment.width, r1.covers.max_literals)
"""

_REFUSALS_PROBE = """
from gatepack.frontend import yaml_subset, model as model_mod
from gatepack.frontend.schema import Design
from gatepack.frontend.errors import AsyncRefused
from gatepack.synth.asynchronous import AsynchronousBackend
from gatepack.toolchain import ToolchainRunner


def compile_async(path):
    node = yaml_subset.parse(open(path).read())
    design = Design.model_validate(yaml_subset.to_python(node))
    return model_mod.compile_design(design, source_name=path, provenance={})

backend = AsynchronousBackend()
runner = ToolchainRunner()
for name in ('async_4literal', 'async_no_svc', 'async_two_input'):
    try:
        backend._synthesize(compile_async(f'tests/golden/designs/{name}.yaml'),
                            runner, workdir='.gpout/async_tc')
    except AsyncRefused as exc:
        print('REFUSED', name, ':', str(exc))
    else:
        raise AssertionError(f'{name} was not refused')
"""

_HAZARDOUS_PROBE = """
from pathlib import Path
from gatepack.netlist import MappedNetlist, MappedCell
from gatepack.verify import hazard
from gatepack.verify.hazard import check_static_hazards, TransitionProbe
from gatepack.toolchain import ToolchainRunner, iverilog_command, vvp_command

def cell(name, cell, conns):
    d = {'A': 'input', 'Y': 'output'} if cell == 'INV' else {'A': 'input', 'B': 'input', 'Y': 'output'}
    return MappedCell(name=name, cell=cell, tier='G', connections=conns, directions=d)

netlist = MappedNetlist(
    top='haz',
    cells=(
        cell('inv1', 'INV', {'A': 'A', 'Y': 'an'}),
        cell('and1', 'AND2', {'A': 'A', 'B': 'B', 'Y': 't1'}),
        cell('and2', 'AND2', {'A': 'an', 'B': 'C', 'Y': 't2'}),
        cell('or1', 'OR2', {'A': 't1', 'B': 't2', 'Y': 'Y'}),
    ),
    inputs=('A', 'B', 'C'),
    outputs=('Y',),
)
funcs = {'INV': '!A', 'AND2': 'A&B', 'OR2': 'A|B'}
probes = [
    TransitionProbe(changing_input='A', stable_inputs={'B': True, 'C': True}, from_value=False),
    TransitionProbe(changing_input='A', stable_inputs={'B': True, 'C': True}, from_value=True),
]
findings = check_static_hazards(netlist, funcs, probes)
assert len(findings) == 2, findings  # one per direction; 5a is direction-agnostic
assert findings[0].output == 'Y' and findings[0].kind == 'static-1'

# 5b: Icarus glitch simulation must observe the glitch too.
mapped_v = "module haz (input wire A, input wire B, input wire C, output wire Y);\\n" \\
           "  wire an, t1, t2;\\n" \\
           "  INV inv1 (.A(A), .Y(an));\\n" \\
           "  AND2 and1 (.A(A), .B(B), .Y(t1));\\n" \\
           "  AND2 and2 (.A(an), .B(C), .Y(t2));\\n" \\
           "  OR2 or1 (.A(t1), .B(t2), .Y(Y));\\nendmodule\\n"
Path('.gpout/async_tc/haz.v').write_text(mapped_v)
Path('.gpout/async_tc/cells.v').write_text(hazard.unit_delay_cells(funcs, seed=0))
Path('.gpout/async_tc/tb.v').write_text(hazard.build_glitch_testbench('haz', ['A', 'B', 'C'], ['Y'], probes))
runner = ToolchainRunner()
vvp = '.gpout/async_tc/haz.vvp'
c = runner.run(iverilog_command(vvp, ['.gpout/async_tc/haz.v', '.gpout/async_tc/cells.v', '.gpout/async_tc/tb.v']), cwd='.')
assert c.returncode == 0, c.stderr
r = runner.run(vvp_command(vvp), cwd='.')
assert 'GLITCH_FAIL' in r.stdout, r.stdout
print('HAZARDOUS_DETECTED', r.stdout.strip().splitlines()[-1])
"""


@requires_toolchain
def test_latch_synthesises_deterministically_and_is_hazard_free():
    proc = _run_python(_LATCH_PROBE)
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "ASYNC_LATCH_OK" in proc.stdout
    assert proc.stdout.strip().splitlines()[0].startswith("ASYNC_LATCH_OK")


@requires_toolchain
def test_refusals_name_the_construct_with_real_z3():
    proc = _run_python(_REFUSALS_PROBE)
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    out = proc.stdout
    assert "REFUSED async_4literal" in out
    assert "a & b & c & d" in out  # names the offending 4-literal term
    assert "REFUSED async_no_svc" in out
    assert "A->B" in out and "B->C" in out and "C->A" in out  # the 3-cycle
    assert "REFUSED async_two_input" in out
    assert "simultaneously" in out  # names both inputs of the two-input change


@requires_toolchain
def test_hazardous_netlist_detected_by_5a_and_5b():
    proc = _run_python(_HAZARDOUS_PROBE)
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "HAZARDOUS_DETECTED" in proc.stdout
