"""Shared run persistence errors; re-exported by run_store."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .errors import SpecromancyError
from .exit_codes import ExitCode


class RunStoreError(SpecromancyError):
    """Base error for expected run-store failures."""

    def __init__(
        self,
        message: str,
        *,
        diagnostic_code: str,
        details: Mapping[str, Any] | None = None,
        code: ExitCode = ExitCode.INTERNAL_ERROR,
    ) -> None:
        values = {"error_code": diagnostic_code}
        if details:
            values.update(details)
        super().__init__(code, message, values)
        self.diagnostic_code = diagnostic_code


class RunNotFoundError(RunStoreError):
    def __init__(self, run_id: str) -> None:
        super().__init__(
            f"run not found: {run_id}",
            diagnostic_code="run-not-found",
            details={"run_id": run_id},
            code=ExitCode.NOT_FOUND,
        )


class RunCorruptionError(RunStoreError):
    def __init__(
        self, message: str, *, run_id: str, details: Mapping[str, Any] | None = None
    ) -> None:
        values: dict[str, Any] = {"run_id": run_id}
        if details:
            values.update(details)
        super().__init__(
            message,
            diagnostic_code="corrupt-run",
            details=values,
        )
