"""Tests for the §6 viability verdict logic (gatepack.estimate).

The verdict is a pure function; these tests need no Yosys.
"""

from __future__ import annotations

import pytest

from gatepack.estimate import Thresholds, VccIncompatibleError, assess, run_estimate

from .helpers import sync_design


def test_green_when_all_within_band():
    v = assess(package_count=10, flop_count=4, clock_fanout=4, depth=3)
    assert v.overall == "green"
    assert v.binding is None


def test_red_on_package_count():
    v = assess(package_count=60, flop_count=4, clock_fanout=4, depth=3)
    assert v.overall == "red"
    assert v.binding == "package count"
    assert "CPLD" in v.message or "PLD" in v.message


def test_red_on_flop_count_even_if_gates_ok():
    # §6: flop count and clock fanout are independent of gate count.
    v = assess(package_count=10, flop_count=20, clock_fanout=20, depth=3)
    assert v.overall == "red"
    assert v.binding == "flop count"


def test_amber_band():
    v = assess(package_count=30, flop_count=4, clock_fanout=4, depth=3)
    assert v.overall == "amber"
    assert v.binding == "package count"


def test_unknown_metrics_do_not_drive_red():
    v = assess(package_count=None, flop_count=4, clock_fanout=4, depth=None)
    assert v.overall == "green"
    assert v.metrics["package count"].status == "unknown"


def test_boundaries():
    assert assess(25, 8, 8, 6).overall == "green"
    assert assess(26, 9, 9, 7).overall == "amber"
    assert assess(51, 16, 16, 11).overall == "red"


def test_thresholds_override():
    t = Thresholds(package_green=100, package_amber=200)
    assert assess(60, 4, 4, 3, thresholds=t).overall == "green"


def test_estimate_writes_files_without_yosys(tmp_path):
    design = tmp_path / "d.yaml"
    design.write_text(sync_design())
    library = tmp_path / "parts.csv"
    library.write_text(
        "cell,tier,family,part_suffix,equivalents,function,inputs,gates_per_pkg,"
        "package,mfrs,vcc_min,vcc_max,area,tpd_ns,iq_ua\n"
        'INV,G,AUP,1G04,,!A,1,1,SOT-353,"TI;Nexperia",0.8,3.6,1.0,4.6,0.9\n'
        'DFF,F,AUP,1G79,,,2,1,SOT-353,"TI;Nexperia",0.8,3.6,1.0,7.2,0.9\n'
    )
    result = run_estimate(design, library, build_dir=tmp_path / "build")
    assert result.yosys_ran is False
    assert (tmp_path / "build" / "generated.v").exists()
    assert (tmp_path / "build" / "properties.sv").exists()
    assert (tmp_path / "build" / "cells.lib").exists()
    assert (tmp_path / "build" / "cells_sim.v").exists()
    assert (tmp_path / "build" / "yosys.ys").exists()
    assert (tmp_path / "build" / "manifest.json").exists()


def test_manifest_is_deterministic_and_has_no_timestamp(tmp_path):
    design = tmp_path / "d.yaml"
    design.write_text(sync_design())
    library = tmp_path / "parts.csv"
    library.write_text(
        "cell,tier,family,part_suffix,equivalents,function,inputs,gates_per_pkg,"
        "package,mfrs,vcc_min,vcc_max,area,tpd_ns,iq_ua\n"
        'INV,G,AUP,1G04,,!A,1,1,SOT-353,"TI;Nexperia",0.8,3.6,1.0,4.6,0.9\n'
    )
    r1 = run_estimate(design, library, build_dir=tmp_path / "b1")
    r2 = run_estimate(design, library, build_dir=tmp_path / "b2")
    assert r1.manifest == r2.manifest
    assert "timestamp" not in r1.manifest
    assert "verdict" in r1.manifest
    assert r1.manifest["yosys"] == "unavailable"

    # the *written* payload has sorted keys (deterministic, §C6)
    import json

    data = json.loads((tmp_path / "b1" / "manifest.json").read_text())
    assert list(data.keys()) == sorted(data.keys())


def test_vcc_incompatible_macro_rejected(tmp_path):
    yaml = sync_design()
    yaml += "macros:\n  - {instance: dwell, cell: CNT4, clock: clk, enable: \"state == A\"}\n"
    design = tmp_path / "d.yaml"
    design.write_text(yaml)
    library = tmp_path / "parts.csv"
    library.write_text(
        "cell,tier,family,part_suffix,equivalents,function,inputs,gates_per_pkg,"
        "package,mfrs,vcc_min,vcc_max,area,tpd_ns,iq_ua\n"
        'INV,G,AUP,1G04,,!A,1,1,SOT-353,"TI;Nexperia",0.8,3.6,1.0,4.6,0.9\n'
        'CNT4,M,HC,HC161,,,3,1,SO-16,"TI;Nexperia",2.0,6.0,8.0,,4.0\n'
    )
    # constraints.vcc defaults to 3.3; CNT4 (HC) is 2.0..6.0 -> actually OK.
    # Force VCC below 2.0 via a custom constraints block.
    yaml_low = yaml.replace("reset: {signal: rst_n, active: low, source: SUPERVISOR}",
                            "reset: {signal: rst_n, active: low, source: SUPERVISOR}\nconstraints: {vcc: 1.8}\n")
    design.write_text(yaml_low)
    with pytest.raises(VccIncompatibleError, match="CNT4"):
        run_estimate(design, library, build_dir=tmp_path / "build")
