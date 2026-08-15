"""Front-end error types."""

from __future__ import annotations


class CompileError(ValueError):
    """The design is invalid (semantic or structural) and cannot be compiled."""


class AsyncRefused(ValueError):
    """The design is asynchronous; v0.1.0 refuses to synthesise it (§7.3).

    Distinct from :class:`CompileError` so the CLI can report a clear "refused"
    verdict with its own exit code rather than a generic validation failure.
    """
