"""Expected, user-facing failures raised by the Specromancy engine."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .exit_codes import ExitCode


class SpecromancyError(Exception):
    """A failure with a stable exit code and serializable diagnostics."""

    def __init__(
        self,
        code: ExitCode | int,
        message: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = ExitCode(code)
        self.message = message
        self.details = dict(details) if details is not None else None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": int(self.code),
            "message": self.message,
        }
        if self.details is not None:
            payload["details"] = self.details
        return payload


class UsageError(SpecromancyError):
    """Invalid command-line input."""

    def __init__(
        self, message: str, details: Mapping[str, Any] | None = None
    ) -> None:
        super().__init__(ExitCode.USAGE_ERROR, message, details)

