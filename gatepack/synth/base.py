"""Synthesis backend interface (§7).

The strategy boundary is designed in from M4 so asynchronous synthesis can be
refused cleanly (R16: async constraints never leak into the synchronous path).
v0.1.0 ships only :class:`~gatepack.synth.synchronous.SynchronousBackend`;
the asynchronous backend detects and refuses (§7.3).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class SynthConfig:
    """Paths and names a synthesis backend needs."""

    top: str
    generated_v: str = "build/generated.v"
    cells_lib: str = "build/cells.lib"
    premap_json: str = "build/premap.json"
    mapped_json: str = "build/mapped.json"
    mapped_v: str = "build/mapped.v"
    flop_cells: tuple[str, ...] = ()


class SynthesisBackend(ABC):
    """Produces the Yosys script for a timing model."""

    @abstractmethod
    def generate_script(self, config: SynthConfig) -> str:
        """Return the full Yosys script text."""
