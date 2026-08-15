"""AsynchronousVerify — refuses (§7.3).

v0.1.0 does not ship asynchronous synthesis, so there is nothing to verify: an
async netlist is refused at the front-end before a verification strategy could
ever see it.  This strategy exists to keep the boundary in place (R16) and to
refuse cleanly if it is ever reached.
"""

from __future__ import annotations

from gatepack.frontend.errors import AsyncRefused
from gatepack.verify.base import VerificationStrategy


class AsynchronousVerify(VerificationStrategy):
    def verify(self, config, compiled, runner, lib_text, sim_text):
        raise AsyncRefused(
            "asynchronous verification is not shipped in v0.1.0 (§7.3); there is "
            "no async netlist to verify. Real async verification is a v0.2 "
            "research task (§23.3)."
        )
