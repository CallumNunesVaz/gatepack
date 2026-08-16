"""The unverified-gates_per_pkg gate must have a reachable escape hatch.

`run_build` refuses a library whose multi-gate parts carry placeholder
`gates_per_pkg`, because that value decides which gates share a die and a wrong
one yields a netlist that cannot physically be built. The refusal message tells
the reader to "pass an explicit acknowledgement" — and for a while there was no
way to pass one from the CLI, so the showcase could not be built at all and the
message named an action the user could not take.

An escape hatch nobody exercises is how this breaks again quietly.
"""

from __future__ import annotations

import inspect

from gatepack.build import run_build
from gatepack.cli import _build_parser


def _build_action(flag: str):
    parser = _build_parser()
    # argparse exposes subparsers through the private choices map; the public
    # surface has no accessor, and reaching for it here is cheaper than
    # re-deriving the whole parser tree.
    sub = next(
        a for a in parser._actions if getattr(a, "choices", None) and "build" in a.choices
    )
    build = sub.choices["build"]
    return next((a for a in build._actions if flag in a.option_strings), None)


def test_cli_exposes_the_acknowledgement_flag():
    action = _build_action("--allow-unverified-gates-per-pkg")
    assert action is not None, (
        "run_build's gate names an acknowledgement the CLI cannot supply; the "
        "refusal message would tell the user to do something impossible"
    )
    assert action.dest == "allow_unverified_gates_per_pkg"


def test_flag_name_matches_the_run_build_parameter():
    # If either side is renamed without the other, the flag parses and is then
    # silently dropped — the build would refuse with the flag set.
    action = _build_action("--allow-unverified-gates-per-pkg")
    params = inspect.signature(run_build).parameters
    assert action.dest in params


def test_the_gate_defaults_to_refusing():
    params = inspect.signature(run_build).parameters
    assert params["allow_unverified_gates_per_pkg"].default is False, (
        "unverified packaging data must be refused by default; an opt-out "
        "default would make the gate decorative"
    )
