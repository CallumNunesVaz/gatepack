"""The structural binding: an async netlist is un-obtainable without stage 5.

The one rule of the package (§7.3) is that no asynchronous netlist is written,
returned or reported unless stage 5 (the independent hazard checks) has run and
passed.  These tests pin that binding structurally, not by convention: the
guarded accessors raise, the backend no longer exposes ``synthesize``, and the
pipeline always runs stage 5.
"""

from __future__ import annotations

import pytest

from gatepack.async_pipeline import (
    AsyncPipelineResult,
    HazardFailed,
    run_async_pipeline,
)
from gatepack.frontend import model as model_mod
from gatepack.frontend import yaml_subset
from gatepack.frontend.errors import AsyncRefused
from gatepack.frontend.schema import Design
from gatepack.netlist import MappedNetlist
from gatepack.synth.asynchronous import AsynchronousBackend
from gatepack.synth.async_.assign import Assignment
from gatepack.synth.async_.cover import CoverResult
from gatepack.synth.async_.emit import EmittedNetlist
from gatepack.synth.async_.flowtable import FlowTable, build_flow_table
from gatepack.verify.asynchronous import AsynchronousVerify
from gatepack.verify.base import CheckResult, CheckStatus, VerificationReport

LATCH = """
name: async_latch
timing_model: asynchronous
reset: {signal: rst_n, active: low}
inputs: [{name: req, sync: false}, {name: ack, sync: false}]
states: [IDLE, BUSY]
initial: IDLE
transitions:
  - {from: IDLE, to: BUSY, when: "req"}
  - {from: IDLE, to: IDLE, when: "!req"}
  - {from: BUSY, to: IDLE, when: "ack"}
  - {from: BUSY, to: BUSY, when: "!ack"}
outputs: [{name: q}]
output_logic: {q: "state == BUSY"}
fundamental_mode: {mutually_exclusive: [[req, ack]]}
"""


def _compile(yaml_text: str):
    node = yaml_subset.parse(yaml_text)
    data = yaml_subset.to_python(node)
    design = Design.model_validate(data)
    return model_mod.compile_design(design, source_name="t.yaml", provenance={})


def _dummy_emitted() -> EmittedNetlist:
    return EmittedNetlist(
        netlist=MappedNetlist(
            top="async_latch",
            cells=(),
            inputs=("req", "ack"),
            outputs=("q",),
        ),
        verilog="module async_latch;\nendmodule\n",
        json='{"modules": {}}',
    )


def _passed_report() -> VerificationReport:
    return VerificationReport(
        checks=[
            CheckResult("hazard (ternary)", CheckStatus.PASSED, kind="hazard"),
            CheckResult("hazard (glitch sim)", CheckStatus.PASSED, kind="hazard"),
        ]
    )


def _failed_report() -> VerificationReport:
    return VerificationReport(
        checks=[
            CheckResult(
                "hazard (ternary)",
                CheckStatus.FAILED,
                "potential static hazard: q (static-1, changing req)",
                kind="hazard",
            ),
            CheckResult("hazard (glitch sim)", CheckStatus.FAILED, kind="hazard"),
        ]
    )


def _not_run_report() -> VerificationReport:
    return VerificationReport(
        checks=[
            CheckResult(
                "hazard (glitch sim)",
                CheckStatus.NOT_RUN,
                "iverilog not installed (Icarus — glitch simulation)",
                kind="hazard",
            )
        ]
    )


def _result(report: VerificationReport) -> AsyncPipelineResult:
    table: FlowTable = build_flow_table(_compile(LATCH))
    return AsyncPipelineResult(
        flow_table=table,
        assignment=Assignment(codes={"IDLE": 1, "BUSY": 0}, width=1),
        covers=CoverResult(
            width=1, input_names=("req", "ack"), state_names=("s_0",), covers=()
        ),
        report=report,
        _emitted=_dummy_emitted(),
    )


def test_result_gates_every_accessor_on_hazard_failure():
    result = _result(_failed_report())
    with pytest.raises(HazardFailed, match="static-1"):
        result.netlist()
    with pytest.raises(HazardFailed):
        result.mapped_verilog()
    with pytest.raises(HazardFailed):
        result.mapped_json()


def test_result_gates_write_on_hazard_not_run(tmp_path):
    # "not run" is not a pass (§14): a netlist must not be emitted on an unrun
    # stage 5 any more than on a failed one.
    result = _result(_not_run_report())
    with pytest.raises(HazardFailed, match="not run"):
        result.write_artefacts(tmp_path)
    assert not (tmp_path / "mapped.json").exists()
    assert not (tmp_path / "mapped.v").exists()


def test_result_yields_netlist_only_after_hazard_pass(tmp_path):
    result = _result(_passed_report())
    assert result.netlist() is not None
    written = result.write_artefacts(tmp_path)
    assert (tmp_path / "mapped.json").exists()
    assert (tmp_path / "mapped.v").exists()
    assert set(written) == {"mapped_json", "mapped_v"}


def test_backend_synthesize_is_internal_only():
    # The old public seam that returned a netlist without stage 5 must be gone:
    # `synthesize` is demoted to `_synthesize`, and the only public route is
    # run_async_pipeline, which runs stage 5.
    assert not hasattr(AsynchronousBackend, "synthesize")
    assert hasattr(AsynchronousBackend, "_synthesize")


class _Result:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class _FakeZ3:
    """Answers assignment (sat, fixed codes) and cover (sat, all candidates)."""

    def __init__(self):
        self.calls: list[str] = []

    def available(self, name: str) -> bool:
        return name == "z3"

    def run(self, argv, cwd, timeout=600):
        self.calls.append(argv[2])
        script = open(argv[2]).read()
        if "bvxor" in script:
            return _Result(stdout="sat\n((s_IDLE #b1)\n (s_BUSY #b0))")
        n = script.count("(declare-const x_")
        vals = " ".join(f"(x_{i} true)" for i in range(n))
        return _Result(stdout=f"sat\n(({vals}))")


class _NoZ3:
    def available(self, name: str) -> bool:
        return False

    def run(self, argv, cwd, timeout=600):
        raise AssertionError("must not be reached")


def test_pipeline_always_runs_stage_5_and_gates_netlist(monkeypatch):
    compiled = _compile(LATCH)
    calls: dict[str, int] = {}

    def fake_verify_netlist(self, netlist, cell_functions, comp, runner, config):
        calls["verify"] = calls.get("verify", 0) + 1
        return _failed_report()

    monkeypatch.setattr(AsynchronousVerify, "verify_netlist", fake_verify_netlist)

    result = run_async_pipeline(
        compiled, _FakeZ3(), workdir=".gpout", cell_functions={"INV": "!A"}
    )
    assert calls["verify"] == 1  # stage 5 ran as part of the pipeline
    assert result.hazard_passed is False
    with pytest.raises(HazardFailed, match="static-1"):
        result.netlist()


def test_pipeline_refuses_with_named_reason_when_z3_missing():
    compiled = _compile(LATCH)
    with pytest.raises(AsyncRefused, match="z3 not found"):
        run_async_pipeline(
            compiled, _NoZ3(), workdir=".gpout", cell_functions={"INV": "!A"}
        )
