"""Machine-readable diagnostics (§C14, app/shared/api.ts).

A :class:`Diagnostic` is the single shape used both inside the ``--json``
envelope (as ``error``/``warnings``) and inside analysis payloads
(``AnalysisSummary.cpldBlockers``).  It is anchored, where possible, to a
location in the source specification: ``path`` relative to the project root,
``line``/``column``, and ``pointer`` — the §15.1 provenance token
(``design.yaml:12:transitions[3]``) that makes a diagnostic selectable into the
FSM graph.

``code`` is a stable, machine-readable string.  The scheme is documented here so
the GUI can key on it without ever parsing ``message``:

    GP1000  internal / unexpected error
    GP1001  compile / design-validation error (C1)
    GP1002  asynchronous synthesis refused (§7.3)
    GP1003  I/O error (missing / unreadable file)
    GP1004  cell-library error (parts.csv / Liberty, C2)
    GP1005  VCC incompatibility (§9.4 [R4-8])
    GP1006  synthesis unavailable — a required tool is missing (§C3)
    GP1007  verification failed (a check produced a counterexample)
    GP1008  verification not run — a required tool is missing (§14)
    GP1009  CPLD-hostile construct (§24.1)
    GP1010  property vacuity / cover failure (a pass would be vacuous, §11)
"""

from __future__ import annotations

from dataclasses import dataclass

GP_INTERNAL = "GP1000"
GP_COMPILE = "GP1001"
GP_ASYNC_REFUSED = "GP1002"
GP_IO = "GP1003"
GP_LIBRARY = "GP1004"
GP_VCC = "GP1005"
GP_SYNTH_UNAVAILABLE = "GP1006"
GP_VERIFY_FAILED = "GP1007"
GP_TOOL_MISSING = "GP1008"
GP_CPLD_BLOCKER = "GP1009"
GP_PROPERTY_VACUOUS = "GP1010"


@dataclass(frozen=True)
class Diagnostic:
    """A machine-readable diagnostic, anchored where possible to the source.

    ``severity`` is one of ``error``, ``warning``, ``info``.  ``pointer`` is the
    §15.1 provenance token (``design.yaml:12:transitions[3]``) when the emitting
    code has that information; it is what lets the GUI select a diagnostic into
    the FSM graph (§15.2).
    """

    severity: str
    code: str
    message: str
    path: str | None = None
    line: int | None = None
    column: int | None = None
    pointer: str | None = None

    def to_dict(self) -> dict:
        out: dict = {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }
        if self.path is not None:
            out["path"] = self.path
        if self.line is not None:
            out["line"] = self.line
        if self.column is not None:
            out["column"] = self.column
        if self.pointer is not None:
            out["pointer"] = self.pointer
        return out


def error(code: str, message: str, **anchor) -> Diagnostic:
    return Diagnostic("error", code, message, **anchor)


def warning(code: str, message: str, **anchor) -> Diagnostic:
    return Diagnostic("warning", code, message, **anchor)


def info(code: str, message: str, **anchor) -> Diagnostic:
    return Diagnostic("info", code, message, **anchor)


__all__ = [
    "Diagnostic",
    "error",
    "info",
    "warning",
    "GP_INTERNAL",
    "GP_COMPILE",
    "GP_ASYNC_REFUSED",
    "GP_IO",
    "GP_LIBRARY",
    "GP_VCC",
    "GP_SYNTH_UNAVAILABLE",
    "GP_VERIFY_FAILED",
    "GP_TOOL_MISSING",
    "GP_CPLD_BLOCKER",
    "GP_PROPERTY_VACUOUS",
]
