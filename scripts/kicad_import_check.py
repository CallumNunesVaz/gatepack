#!/usr/bin/env python3
"""Drive KiCad's *own* netlist reader over an emitted ``netlist.net`` — or prove
it cannot be driven.

The descoped M10-1 criterion ("KiCad import clean, including power symbols and
no-connects") was removed from v0.1.0 on the premise that no automated check can
close it, because it needs a human with KiCad.  This script attacks that
premise: KiCad ships a Python module (``pcbnew``), so if that module exposes the
netlist reader that "Update PCB from Schematic" uses, the check is automatable.

**It does not.**  Measured in KiCad 9.0.9 and 10.0.5: ``pcbnew`` exposes no
netlist reader (``NETLIST_READER`` / ``PCB_NETLIST`` /
``LoadFootprintsFromNetlist`` are all absent from the Python API), and
``kicad-cli`` has no netlist-import command.  This script therefore does the
honest thing: it *probes* for the reader and, finding none, reports that it is
blocked and exits ``2``.  It never substitutes a hand-written parser and calls
it an import check — a parser that agrees with the emitter is circular and
would close the criterion falsely.

Exit codes:

``0``  a headless netlist reader exists and the import check ran and passed
``1``  a headless netlist reader exists and the import check ran and *failed*
``2``  blocked: this KiCad build exposes no headless netlist reader
``3``  precondition error (``pcbnew`` not importable, netlist missing, ...)

If a future KiCad exposes the reader, the "would do" section at the bottom is
where the real import goes; until then this script exists to keep the *absence*
measured and pinned rather than assumed.
"""

from __future__ import annotations

import sys

#: Symbols that would indicate ``pcbnew`` exposes the netlist reader.  Checked
#: one by one so the report names exactly which are present/absent.
READER_SYMBOLS = (
    "NETLIST_READER",
    "PCB_NETLIST",
    "KICAD_NETLIST_READER",
    "LEGACY_NETLIST_READER",
    "COMPONENT",
    "LoadFootprintsFromNetlist",
)

EXIT_OK = 0
EXIT_IMPORT_FAILED = 1
EXIT_BLOCKED = 2
EXIT_PRECONDITION = 3


def probe_reader() -> dict:
    """Report what ``pcbnew`` exposes and whether a netlist reader is drivable.

    Returns a dict of evidence; ``reader_available`` is ``False`` for every
    KiCad version this has been run against so far.
    """
    try:
        import pcbnew
    except Exception as exc:  # pragma: no cover - image layout change
        return {"pcbnew_importable": False, "error": repr(exc)}

    pcbnew_attrs = set(dir(pcbnew))
    present = {name: (name in pcbnew_attrs) for name in READER_SYMBOLS}

    try:
        source = open(pcbnew.__file__).read()
        netlist_mentions = source.count("NETLIST")
    except OSError:
        netlist_mentions = -1

    return {
        "pcbnew_importable": True,
        "version": pcbnew.GetBuildVersion(),
        "symbols": present,
        "netlist_mentions_in_pcbnew_py": netlist_mentions,
        "reader_available": any(present.values()),
    }


def _format_blocked_report(evidence: dict) -> str:
    version = evidence.get("version", "unknown")
    symbols = evidence["symbols"]
    absent = [name for name, present in symbols.items() if not present]
    lines = [
        f"pcbnew {version}: no headless netlist reader is exposed.",
        "",
        "This is the exact thing that blocks the M10-1 criterion:",
    ]
    for name in READER_SYMBOLS:
        status = "present" if symbols[name] else "absent"
        lines.append(f"  pcbnew.{name}: {status}")
    lines.append(
        f"  NETLIST mentions in pcbnew.py: {evidence['netlist_mentions_in_pcbnew_py']}"
    )
    lines.append("")
    lines.append("No netlist was imported. This check did not run.")
    lines.append(
        "KiCad ships no scriptable netlist reader in this version, so a real "
        "import check cannot be produced; a hand-written parser is NOT a "
        "substitute (see docs/BUILD-NOTES-kicad.md)."
    )
    lines.append(
        f"Symbols to look for next time (all absent here): {', '.join(sorted(absent))}"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: kicad_import_check.py NETLIST.net", file=sys.stderr)
        return EXIT_PRECONDITION

    netlist_path = args[0]
    evidence = probe_reader()

    if not evidence.get("pcbnew_importable"):
        print(
            f"pcbnew could not be imported: {evidence.get('error')}", file=sys.stderr
        )
        return EXIT_PRECONDITION

    if not evidence["reader_available"]:
        print(_format_blocked_report(evidence))
        return EXIT_BLOCKED

    # ------------------------------------------------------------------
    # A reader is exposed.  This branch has never run against a real KiCad
    # (no version exposes one), so the import below is written but unverified.
    # It is the *only* place a real import may be implemented: assert the
    # three criteria with KiCad's own reader, never with a hand-rolled parser.
    # ------------------------------------------------------------------
    print(
        f"pcbnew {evidence['version']} exposes a netlist reader; "
        "the real import check is not yet implemented (see docs/BUILD-NOTES-kicad.md).",
        file=sys.stderr,
    )
    return EXIT_IMPORT_FAILED


if __name__ == "__main__":
    sys.exit(main())
