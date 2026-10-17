"""Field diagnostics and repository-contained resource resolution for configuration."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, NoReturn

from .config_errors import PipelineConfigError, _MISSING


IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class FieldContext:
    """Source and repository authority shared by configuration parsers."""

    def __init__(self, path: Path, repository_root: Path) -> None:
        self.path = path
        self.repository_root = repository_root

    def fail(
        self,
        diagnostic_code: str,
        message: str,
        *,
        phase: str | None = None,
        field: str | None = None,
        value: Any = _MISSING,
        remediation: str,
    ) -> NoReturn:
        raise PipelineConfigError(
            diagnostic_code,
            message,
            path=self.path,
            phase=phase,
            field=field,
            value=value,
            remediation=remediation,
        )

    def require_mapping(
        self, value: Any, field: str, *, phase: str | None = None
    ) -> Mapping[str, Any]:
        if not isinstance(value, Mapping):
            self.fail(
                "invalid-field-type",
                f"{field} must be a table",
                phase=phase,
                field=field,
                value=value,
                remediation="replace it with a TOML table",
            )
        return value

    def require_string(
        self, value: Any, field: str, *, phase: str | None = None
    ) -> str:
        if not isinstance(value, str) or not value.strip():
            self.fail(
                "invalid-field-type",
                f"{field} must be a non-empty string",
                phase=phase,
                field=field,
                value=value,
                remediation="provide a non-empty string",
            )
        return value

    def require_identifier(
        self, value: Any, field: str, *, phase: str | None = None
    ) -> str:
        identifier = self.require_string(value, field, phase=phase)
        if not IDENTIFIER_PATTERN.fullmatch(identifier):
            self.fail(
                "invalid-identifier",
                f"{field} has invalid identifier {identifier!r}",
                phase=phase,
                field=field,
                value=identifier,
                remediation="use lowercase words separated by single hyphens",
            )
        return identifier

    def require_integer(
        self,
        value: Any,
        field: str,
        *,
        phase: str | None = None,
        minimum: int | None = None,
    ) -> int:
        if not isinstance(value, int) or isinstance(value, bool):
            self.fail(
                "invalid-field-type",
                f"{field} must be an integer",
                phase=phase,
                field=field,
                value=value,
                remediation="provide an integer value",
            )
        if minimum is not None and value < minimum:
            self.fail(
                "invalid-bound",
                f"{field} must be at least {minimum}",
                phase=phase,
                field=field,
                value=value,
                remediation=f"set {field} to {minimum} or greater",
            )
        return value

    def string_list(
        self,
        value: Any,
        field: str,
        *,
        phase: str | None = None,
        allow_empty: bool = True,
        identifiers: bool = False,
    ) -> tuple[str, ...]:
        if not isinstance(value, list):
            self.fail(
                "invalid-field-type",
                f"{field} must be a list of strings",
                phase=phase,
                field=field,
                value=value,
                remediation="provide a TOML array of strings",
            )
        parsed: list[str] = []
        for item in value:
            parsed.append(
                self.require_identifier(item, field, phase=phase)
                if identifiers
                else self.require_string(item, field, phase=phase)
            )
        if not parsed and not allow_empty:
            self.fail(
                "empty-field",
                f"{field} must contain at least one value",
                phase=phase,
                field=field,
                value=[],
                remediation="add at least one entry",
            )
        if len(set(parsed)) != len(parsed):
            self.fail(
                "duplicate-value",
                f"{field} contains duplicate values",
                phase=phase,
                field=field,
                value=parsed,
                remediation="remove duplicate entries",
            )
        return tuple(parsed)

    def existing_path(
        self,
        declared: str,
        field: str,
        *,
        phase: str | None = None,
        base: Path | None = None,
    ) -> Path:
        if not _safe_declared_path(declared, allow_parent=True):
            self.fail(
                "unsafe-path",
                f"{field} must be a safe repository-relative path",
                phase=phase,
                field=field,
                value=declared,
                remediation="use a relative path that resolves inside the repository",
            )
        candidate = ((base or self.path.parent) / declared).resolve()
        if not candidate.is_relative_to(self.repository_root):
            self.fail(
                "unsafe-path",
                f"{field} resolves outside the repository",
                phase=phase,
                field=field,
                value=declared,
                remediation="choose a file inside the repository",
            )
        if not candidate.is_file():
            self.fail(
                "missing-file",
                f"referenced file does not exist: {declared}",
                phase=phase,
                field=field,
                value=declared,
                remediation="create the referenced file or correct the path",
            )
        return candidate

    def check_unknown(
        self,
        raw: Mapping[str, Any],
        allowed: set[str],
        *,
        phase: str | None = None,
    ) -> None:
        unknown = sorted(set(raw) - allowed)
        if unknown:
            self.fail(
                "unknown-field",
                f"unknown configuration field: {unknown[0]}",
                phase=phase,
                field=unknown[0],
                value=raw[unknown[0]],
                remediation="remove the field or use a supported field name",
            )


def _safe_declared_path(
    value: str, *, allow_glob: bool = False, allow_parent: bool = False
) -> bool:
    if not value or "\\" in value or value.startswith("/"):
        return False
    if re.match(r"^[A-Za-z]:", value):
        return False
    parts = Path(value).parts
    if (".." in parts and not allow_parent) or "." in parts:
        return False
    if not allow_glob and any(character in value for character in "*?["):
        return False
    return True
