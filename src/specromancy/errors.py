"""Stable application errors and process exit codes."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Mapping


class ExitCode(IntEnum):
    """Process codes reserved by the version 1 contract."""

    SUCCESS = 0
    INVALID_INPUT = 2
    INVALID_TRANSITION = 3
    VALIDATION_FAILED = 4
    APPROVAL_REQUIRED = 5
    EXTERNAL_COMMAND_FAILED = 6
    SAFETY_REJECTED = 7
    CONCURRENCY_CONFLICT = 8


@dataclass(eq=False)
class SpecromancyError(Exception):
    """An expected failure safe to render to a user or JSON consumer."""

    message: str
    code: str = "SPECROMANCY_ERROR"
    exit_code: ExitCode = ExitCode.VALIDATION_FAILED
    hint: str | None = None
    path: str | None = None
    retryable: bool = False
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__init__(self.message)

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "hint": self.hint,
            "path": self.path,
            "retryable": self.retryable,
            "details": dict(self.details),
        }


class InvalidInputError(SpecromancyError):
    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            code="INVALID_INPUT",
            exit_code=ExitCode.INVALID_INPUT,
            **kwargs,
        )


class InvalidTransitionError(SpecromancyError):
    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            code="INVALID_TRANSITION",
            exit_code=ExitCode.INVALID_TRANSITION,
            **kwargs,
        )


class ValidationError(SpecromancyError):
    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            code="VALIDATION_FAILED",
            exit_code=ExitCode.VALIDATION_FAILED,
            **kwargs,
        )


class ApprovalRequiredError(SpecromancyError):
    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            code="APPROVAL_REQUIRED",
            exit_code=ExitCode.APPROVAL_REQUIRED,
            **kwargs,
        )


class ExternalCommandError(SpecromancyError):
    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("retryable", True)
        super().__init__(
            message,
            code="EXTERNAL_COMMAND_FAILED",
            exit_code=ExitCode.EXTERNAL_COMMAND_FAILED,
            **kwargs,
        )


class SafetyError(SpecromancyError):
    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            code="SAFETY_REJECTED",
            exit_code=ExitCode.SAFETY_REJECTED,
            **kwargs,
        )


class ConcurrencyError(SpecromancyError):
    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("retryable", True)
        super().__init__(
            message,
            code="CONCURRENCY_CONFLICT",
            exit_code=ExitCode.CONCURRENCY_CONFLICT,
            **kwargs,
        )


def normalize_exception(exc: BaseException) -> SpecromancyError:
    """Map unexpected operational failures to one stable application error."""

    if isinstance(exc, SpecromancyError):
        return exc
    if isinstance(exc, (OSError, UnicodeError)):
        return ValidationError(f"File operation failed: {exc}")
    return ValidationError("An unexpected validation failure occurred.")

