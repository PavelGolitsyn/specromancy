"""Stable pipeline diagnostics and JSON-safe diagnostic values."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..errors import SpecromancyError
from ..exit_codes import ExitCode


_MISSING = object()


class PipelineConfigError(SpecromancyError):
    """An expected pipeline error with a stable diagnostic code."""

    def __init__(
        self,
        diagnostic_code: str,
        message: str,
        *,
        path: Path,
        phase: str | None = None,
        field: str | None = None,
        value: Any = _MISSING,
        remediation: str,
    ) -> None:
        details: dict[str, Any] = {
            "error_code": diagnostic_code,
            "path": str(path),
            "remediation": remediation,
        }
        if phase is not None:
            details["phase"] = phase
        if field is not None:
            details["field"] = field
        if value is not _MISSING:
            details["value"] = _json_value(value)
        super().__init__(ExitCode.INVALID_PIPELINE, message, details)
        self.diagnostic_code = diagnostic_code


def _json_value(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_value(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return isoformat()
    return repr(value)
