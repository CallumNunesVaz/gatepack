"""Tie-off handling (§9.7).

Every unconnected input must be tied in the emitted netlist:

* spare-gate inputs tie to a rail (a global power reference),
* unused inputs of *used* gates tie to the function's **identity value** — the
  value that lets the gate still implement its reduced function (e.g. a NAND
  with one input tied high becomes an inverter).

This module computes that identity value for each input of a ``parts.csv``
boolean function; C6 (emitters, M10) applies it.  It is a pure function so it is
unit-testable without Yosys.
"""

from __future__ import annotations

from gatepack.liberty import boolean


def identity_value(func: str, inputs: int, pin_index: int) -> int | None:
    """Return the tie-off value for ``pin_index`` that neutralises it, or ``None``.

    A value ``v`` neutralises ``pin_index`` when fixing that pin to ``v`` leaves
    a non-constant function of the remaining inputs (the gate still does useful
    work).  When both ``0`` and ``1`` do (the XOR/XNOR family), the algebraic
    identity is chosen — the value that leaves the gate as a buffer on the
    remaining input (``0`` for XOR, ``1`` for XNOR).
    """
    pins = boolean.pin_names(inputs)
    if not (0 <= pin_index < inputs):
        raise IndexError(pin_index)
    pin = pins[pin_index]
    rest = [p for p in pins if p != pin]

    def outputs_for(value: int) -> set[bool]:
        outs: set[bool] = set()
        for code in range(1 << len(rest)):
            env = {
                p: bool(code & (1 << (len(rest) - 1 - i))) for i, p in enumerate(rest)
            }
            env[pin] = bool(value)
            outs.add(boolean.evaluate(func, inputs, env))
        return outs

    zero = outputs_for(0)
    one = outputs_for(1)
    zero_nonconst = len(zero) > 1
    one_nonconst = len(one) > 1

    if zero_nonconst and not one_nonconst:
        return 0
    if one_nonconst and not zero_nonconst:
        return 1
    if zero_nonconst and one_nonconst:
        # both neutralise the pin (XOR/XNOR): pick the buffer identity
        if len(rest) == 1 and _is_buffer(func, inputs, pin, 0, rest[0]):
            return 0
        return 1
    # fixing the pin to either value yields a constant -> no spare-input identity
    return None


def _is_buffer(func: str, inputs: int, pin: str, value: int, other: str) -> bool:
    """True if fixing ``pin=value`` makes ``func`` equal ``other`` (a buffer)."""
    for bit in (False, True):
        env = {other: bit, pin: bool(value)}
        if boolean.evaluate(func, inputs, env) != bit:
            return False
    return True


def identity_values(func: str, inputs: int) -> dict[str, int]:
    """Map each input pin name to its identity value (omitted when there is none)."""
    pins = boolean.pin_names(inputs)
    out: dict[str, int] = {}
    for index, pin in enumerate(pins):
        value = identity_value(func, inputs, index)
        if value is not None:
            out[pin] = value
    return out
