"""C11's divergence column, against a real Yosys netlist.

The column reported nothing for months: `simulate.load_mapped` never called
`resolve_parts`, and Yosys's post-ABC `write_json` carries no
`port_directions`, so the evaluator could not tell an input pin from an output
pin and every output came back `x`. `diverges` was therefore permanently false
— C11's most valuable affordance was a check incapable of failing.

The unit test that "covered" it fabricated a netlist **with**
`port_directions`, which real Yosys output never has. It passed throughout.
Hence this test, which uses a netlist Yosys actually produced.
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from tests.toolchain.docker_runner import IMAGE, run_repo


def _toolchain() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(
        ["docker", "image", "inspect", IMAGE], capture_output=True
    ).returncode == 0


requires_toolchain = pytest.mark.skipif(
    not _toolchain(), reason=f"{IMAGE} not available; see Dockerfile.probe"
)


def _run(script: str) -> subprocess.CompletedProcess[str]:
    return run_repo("bash", "-c", script)


def _simulate(build: str) -> dict:
    proc = _run(
        f"python3 -m gatepack simulate tests/golden/designs/xor2.yaml "
        f"--library libraries/74aup.csv --build {build} --json"
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)["data"]


@requires_toolchain
def test_actual_column_is_real_not_x() -> None:
    out = ".gpout/t_sim_ok"
    build = _run(
        f"rm -rf {out} && python3 -m gatepack build tests/golden/designs/xor2.yaml "
        f"--library libraries/74aup.csv --out {out}"
    )
    assert build.returncode == 0, build.stderr

    data = _simulate(out)
    assert data["rows"], "no rows simulated"
    for row in data["rows"]:
        actual = row.get("actual")
        assert actual, "no `actual` column: the netlist was not evaluated at all"
        assert "x" not in actual.values(), (
            f"output evaluated to 'x' ({actual}) — pin directions were not "
            "resolved against the library; see this module's docstring"
        )
    assert not any(r["diverges"] for r in data["rows"]), (
        "a correct netlist must not diverge from its own specification"
    )


@requires_toolchain
def test_divergence_fires_when_the_netlist_is_wrong() -> None:
    """The half that matters: the column must be able to say "no"."""
    src, bad = ".gpout/t_sim_ok", ".gpout/t_sim_bad"
    prep = _run(
        f"rm -rf {bad} && cp -r {src} {bad} && python3 - <<'EOF'\n"
        "import json\n"
        f"p = '{bad}/mapped.json'\n"
        "d = json.load(open(p))\n"
        "m = next(iter(d['modules'].values()))\n"
        "for c in m['cells'].values():\n"
        "    if c['type'] == 'XOR2':\n"
        "        c['type'] = 'AND2'\n"
        "json.dump(d, open(p, 'w'))\n"
        "EOF"
    )
    assert prep.returncode == 0, prep.stderr

    data = _simulate(bad)
    diverging = [r for r in data["rows"] if r["diverges"]]
    # AND and XOR agree only on 00; they differ on the other three minterms.
    assert len(diverging) == 3, (
        f"expected 3 diverging minterms for XOR replaced by AND, got "
        f"{len(diverging)}: {data['rows']}"
    )
