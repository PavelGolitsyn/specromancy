"""Dependency-free validation for phase output artifacts.

The JSON validator intentionally implements only the project-supported subset:
``type``, ``required``, ``properties``, ``items``, ``enum``, ``pattern``, and
``additionalProperties``.  Pipeline loading rejects every other keyword.
"""

from __future__ import annotations

import json
import re
import stat
from pathlib import Path
from typing import Any

from ._config.config_models import ValidatorConfig
from .hashing import sha256_file
from .schema_validation import (
    SUPPORTED_JSON_TYPES,
    SUPPORTED_SCHEMA_KEYWORDS,
    SchemaDefinitionError,
    _matches_type,
    _validate_json_value,
    load_json_schema,
    validate_schema_definition,
)


TEMPLATE_MARKER = re.compile(
    r"\{\{[^{}\n]+\}\}|\{%[^%\n]+%\}|<<[^<>\n]+>>"
)


class ValidationFailure(ValueError):
    """A deterministic artifact validation failure."""

    def __init__(
        self, diagnostic_code: str, message: str, **details: Any
    ) -> None:
        super().__init__(message)
        self.diagnostic_code = diagnostic_code
        self.message = message
        self.details = details


def validate_artifact(
    run_directory: Path,
    relative_path: str,
    validator: ValidatorConfig,
    *,
    template_path: Path | None = None,
) -> dict[str, Any]:
    """Validate one run-relative output and return a manifest-safe check."""

    path = _resolve_regular_file(run_directory, relative_path)
    try:
        content = path.read_bytes()
    except (OSError, PermissionError) as exc:
        raise ValidationFailure(
            "unreadable-output",
            f"output artifact is unreadable: {relative_path}",
            path=relative_path,
            error=str(exc),
        ) from exc
    if not content.strip():
        raise ValidationFailure(
            "empty-output",
            f"output artifact is empty: {relative_path}",
            path=relative_path,
        )
    digest = sha256_file(path)
    if template_path is not None:
        try:
            template_digest = sha256_file(template_path)
        except OSError as exc:
            raise ValidationFailure(
                "unreadable-template",
                "output template is unreadable",
                path=str(template_path),
                error=str(exc),
            ) from exc
        if digest == template_digest:
            raise ValidationFailure(
                "unchanged-template",
                "output artifact is unchanged from its template",
                path=relative_path,
            )

    text: str | None = None
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        if validator.type in {"markdown", "json"}:
            raise ValidationFailure(
                "invalid-utf8",
                "text output is not valid UTF-8",
                path=relative_path,
            ) from exc
    if text is not None:
        marker = TEMPLATE_MARKER.search(text)
        if marker is not None:
            raise ValidationFailure(
                "unresolved-template-marker",
                "output contains an unresolved template marker",
                path=relative_path,
                marker=marker.group(0),
            )

    details: dict[str, Any] = {
        "type": validator.type,
        "status": "passed",
        "path": relative_path,
        "sha256": digest,
        "size_bytes": len(content),
    }
    if validator.type == "markdown":
        assert text is not None
        heading_counts = markdown_heading_counts(text)
        missing: list[str] = []
        duplicated: list[str] = []
        for heading in validator.required_headings:
            count = heading_counts.get(heading, 0)
            if count == 0:
                missing.append(heading)
            elif validator.heading_occurrence == "exactly-once" and count != 1:
                duplicated.append(heading)
        if missing or duplicated:
            raise ValidationFailure(
                "invalid-markdown-headings",
                "markdown output does not satisfy its required headings",
                path=relative_path,
                missing=missing,
                duplicated=duplicated,
                occurrence=validator.heading_occurrence,
            )
        details["headings"] = {
            heading: heading_counts.get(heading, 0)
            for heading in validator.required_headings
        }
    elif validator.type == "json":
        assert text is not None
        try:
            value = json.loads(
                text,
                parse_constant=lambda value: (_ for _ in ()).throw(
                    ValueError(f"invalid JSON constant {value}")
                ),
            )
        except (json.JSONDecodeError, ValueError) as exc:
            message = exc.msg if isinstance(exc, json.JSONDecodeError) else str(exc)
            raise ValidationFailure(
                "malformed-json",
                f"JSON output is malformed: {message}",
                path=relative_path,
                line=getattr(exc, "lineno", None),
                column=getattr(exc, "colno", None),
            ) from exc
        if validator.json_schema is not None:
            errors: list[dict[str, str]] = []
            _validate_json_value(value, validator.json_schema, "$", errors)
            if errors:
                raise ValidationFailure(
                    "json-schema-failed",
                    "JSON output does not match its configured schema",
                    path=relative_path,
                    errors=errors,
                )
    return details


def markdown_heading_counts(content: str) -> dict[str, int]:
    """Count ATX and Setext headings while ignoring fenced code blocks."""

    counts: dict[str, int] = {}
    lines = content.splitlines()
    in_fence = False
    fence_character = ""
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.lstrip()
        fence = re.match(r"(`{3,}|~{3,})", stripped)
        if fence:
            marker = fence.group(1)
            if not in_fence:
                in_fence = True
                fence_character = marker[0]
            elif marker[0] == fence_character:
                in_fence = False
            index += 1
            continue
        if in_fence:
            index += 1
            continue
        atx = re.match(r"^ {0,3}#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*$", line)
        if atx:
            heading = atx.group(1).strip()
            counts[heading] = counts.get(heading, 0) + 1
            index += 1
            continue
        if index + 1 < len(lines) and line.strip():
            underline = lines[index + 1]
            if re.match(r"^ {0,3}(?:=+|-+)[ \t]*$", underline):
                heading = line.strip()
                counts[heading] = counts.get(heading, 0) + 1
                index += 2
                continue
        index += 1
    return counts


def _resolve_regular_file(run_directory: Path, relative_path: str) -> Path:
    try:
        root = run_directory.resolve(strict=True)
        candidate = root / relative_path
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValidationFailure(
            "missing-output",
            f"output artifact does not exist: {relative_path}",
            path=relative_path,
        ) from exc
    if not resolved.is_relative_to(root):
        raise ValidationFailure(
            "unsafe-output-path",
            "output artifact resolves outside the run directory",
            path=relative_path,
        )
    try:
        stat_result = candidate.lstat()
    except OSError as exc:
        raise ValidationFailure(
            "unreadable-output", "output artifact cannot be inspected", path=relative_path
        ) from exc
    if not stat.S_ISREG(stat_result.st_mode):
        raise ValidationFailure(
            "invalid-output-type",
            "output artifact is not a regular file",
            path=relative_path,
        )
    return candidate
