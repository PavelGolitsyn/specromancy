"""Expected engine rejections, independent of command orchestration."""

from __future__ import annotations

from typing import Any

from ..errors import SpecromancyError
from ..exit_codes import ExitCode


class EngineError(SpecromancyError):
    """An expected state-machine rejection with a stable diagnostic."""

    def __init__(
        self,
        code: ExitCode,
        message: str,
        diagnostic_code: str,
        **details: Any,
    ) -> None:
        super().__init__(code, message, {"error_code": diagnostic_code, **details})
        self.diagnostic_code = diagnostic_code
