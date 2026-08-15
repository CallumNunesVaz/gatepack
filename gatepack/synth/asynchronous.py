"""AsynchronousBackend — refuses (§7.3).

v0.1.0 does not ship asynchronous synthesis.  Three problems are unsolved in
general (factoring a hazard-free cover, single-variable-change state assignment,
Espresso not emitting hazard-free covers), so an async netlist would be formally
equivalent and hazardous on the bench — the worst possible output.  This backend
exists so the strategy boundary is in place (R16) and so async is refused
cleanly rather than mis-synthesised.
"""

from __future__ import annotations

from gatepack.frontend.errors import AsyncRefused
from gatepack.synth.base import SynthConfig, SynthesisBackend


class AsynchronousBackend(SynthesisBackend):
    def generate_script(self, config: SynthConfig) -> str:
        raise AsyncRefused(
            "asynchronous synthesis is not shipped in v0.1.0 (§7.3); the "
            "AsynchronousBackend refuses rather than emit a hazard-prone netlist. "
            "Real async synthesis is a v0.2 research task (§23.3)."
        )
