"""C8 report generator — assembles C7 output into ``report.md``."""

from gatepack.report.report import (
    AsyncReportInputs,
    ReportInputs,
    emit_async_report,
    emit_report,
)

__all__ = [
    "AsyncReportInputs",
    "ReportInputs",
    "emit_async_report",
    "emit_report",
]
