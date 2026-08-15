"""C3 SynchronousBackend (§12 C3).

The emitted script follows the corrected §12 C3 exactly: the shared common front
end (§C3) runs first and stops before ``dfflegalize``/``dfflibmap``/``abc``, with
``setundef -zero`` *before* the split ([R4-12]), no bare ``fsm`` ([R4-5]),
explicit ``dfflegalize`` ([R4-2]), the ``$mem`` assertion ([R4-13]) and the latch
ban (§9.2).  The ``dfflegalize`` flavour string is a documented best-effort
mapping to be confirmed against the pinned Yosys at M0 (see BUILD-NOTES).
"""

from __future__ import annotations

from gatepack import yosys
from gatepack.synth.base import SynthConfig, SynthesisBackend

# F-cell -> (Yosys DFF type, dfflegalize flavour string).  The flavour strings
# are the design's example values (§12 C3) and MUST be confirmed against the
# pinned Yosys version at M0; Yosys is not installed in this environment.
FLOP_TYPE_MAP: dict[str, tuple[tuple[str, str], ...]] = {
    "DFF": (("$_DFF_P_", "01"),),
    "DFF_R": (("$_DFF_PN0_", "01"),),
    "DFF_S": (("$_DFF_PN1_", "01"),),
    "DFF_SR": (("$_DFFSR_PNN_", "01"),),
}


class SynchronousBackend(SynthesisBackend):
    """One-hot/binary/gray FSM synthesis through ``dfflibmap`` -> ``abc``."""

    def generate_script(self, config: SynthConfig) -> str:
        front = yosys.common_frontend(
            top=config.top,
            generated_v=config.generated_v,
            premap_json=config.premap_json,
        )
        return front + "\n" + self._backend_script(config)

    @staticmethod
    def dfflegalize_args(flop_cells: tuple[str, ...]) -> str:
        """Build the explicit ``dfflegalize`` cell list from the library's F-cells."""
        args: list[str] = []
        for cell in sorted(flop_cells):
            for dtype, flavour in FLOP_TYPE_MAP.get(cell, ()):
                args.append(f"-cell {dtype} {flavour}")
        return " ".join(args)

    def _backend_script(self, config: SynthConfig) -> str:
        legalize = self.dfflegalize_args(config.flop_cells)
        return "\n".join(
            [
                "# --- synchronous backend ---",
                (
                    f"dfflegalize {legalize}    # [R4-2] explicit; flavours from "
                    f"cells.lib"
                ),
                f"dfflibmap -liberty {config.cells_lib}",
                f"abc -liberty {config.cells_lib}",
                "clean",
                f"stat -liberty {config.cells_lib}",
                f"write_json {config.mapped_json}",
                f"write_verilog -noattr {config.mapped_v}      # [R4-17] for Icarus (§C4.3)",
            ]
        )
