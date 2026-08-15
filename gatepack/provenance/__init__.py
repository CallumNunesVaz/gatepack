"""Provenance map (§15.1) — pre-map capture and forward-matching.

The mapped netlist carries provenance by two carriers
(docs/M0-FINDINGS.md §3–4): sequential cells keep their ``gp_src`` cell
attribute through ``dfflibmap``; combinational cells are traced through the
``gp_src`` attribute on the nets they drive (which survives ``abc``), with
structural cone-signature matching as the secondary signal for cells whose nets
were optimised away.

Public API:

* :func:`~gatepack.provenance.capture.parse_netlist_json` /
  :func:`~gatepack.provenance.capture.read_netlist_json` — parse ``write_json``.
* :func:`~gatepack.provenance.capture.capture_sources` — recover cell ``gp_src``
  refs (the sequential carrier).
* :func:`~gatepack.provenance.capture.capture_net_sources` — recover net
  ``gp_src`` refs (the combinational carrier).
* :func:`~gatepack.provenance.match.match_netlists` — forward-match + per-carrier
  coverage.
"""

from __future__ import annotations

from gatepack.provenance.verilog_attrs import net_provenance
from gatepack.provenance.capture import (
    PROVENANCE_ATTR,
    Cell,
    Netlist,
    PinRef,
    SourceRef,
    capture_net_sources,
    capture_sources,
    parse_netlist_json,
    read_netlist_json,
)
from gatepack.provenance.match import (
    CARRIERS,
    MAX_SUPPORT,
    Link,
    MatchResult,
    match_netlists,
)

__all__ = [
    "CARRIERS",
    "Cell",
    "Link",
    "MAX_SUPPORT",
    "MatchResult",
    "Netlist",
    "PROVENANCE_ATTR",
    "PinRef",
    "SourceRef",
    "capture_net_sources",
    "net_provenance",
    "capture_sources",
    "match_netlists",
    "parse_netlist_json",
    "read_netlist_json",
]
