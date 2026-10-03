"""Dependency-free validation for phase output artifacts.

The JSON validator intentionally implements only the project-supported subset:
``type``, ``required``, ``properties``, ``items``, ``enum``, ``pattern``, and
``additionalProperties``.  Pipeline loading rejects every other keyword.
"""

from __future__ import annotations

import json
import re
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .config import ValidatorConfig
from .hashing import sha256_file


SUPPORTED_SCHEMA_KEYWORDS = frozenset(
    {"type", "required", "properties", "items", "enum", "pattern", "additionalProperties"}
)
SUPPORTED_JSON_TYPES = frozenset(
    {"object", "array", "string", "number", "integer", "boolean", "null"}
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


class SchemaDefinitionError(ValueError):
    """A schema uses syntax outside the deliberately small supported subset."""

    def __init__(self, message: str, *, location: str = "$") -> None:
        super().__init__(message)
        self.location = location


def load_json_schema(path: Path) -> dict[str, Any]:
    """Load and validate a project-owned subset JSON schema."""

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"invalid JSON constant {value}")
            ),
        )
    except (OSError, UnicodeError, ValueError) as exc:
        raise SchemaDefinitionError(f"schema is not readable JSON: {exc}") from exc
    validate_schema_definition(value)
    return value


def validate_schema_definition(schema: Any, *, location: str = "$") -> None:
    """Reject unsupported or malformed schema definitions recursively."""

    if not isinstance(schema, Mapping):
        raise SchemaDefinitionError("schema must be an object", location=location)
    unknown = sorted(set(schema) - SUPPORTED_SCHEMA_KEYWORDS)
    if unknown:
        raise SchemaDefinitionError(
            f"unsupported schema keyword {unknown[0]!r}", location=location
        )
    schema_type = schema.get("type")
    if schema_type is not None and schema_type not in SUPPORTED_JSON_TYPES:
        raise SchemaDefinitionError(
            f"unsupported schema type {schema_type!r}", location=f"{location}.type"
        )
    required = schema.get("required")
    if required is not None and (
        not isinstance(required, list)
        or any(not isinstance(item, str) or not item for item in required)
        or len(set(required)) != len(required)
    ):
        raise SchemaDefinitionError(
            "required must be a unique list of non-empty strings",
            location=f"{location}.required",
        )
    properties = schema.get("properties")
    if properties is not None:
        if not isinstance(properties, Mapping) or any(
            not isinstance(name, str) for name in properties
        ):
            raise SchemaDefinitionError(
                "properties must be an object", location=f"{location}.properties"
            )
        for name, child in properties.items():
            validate_schema_definition(child, location=f"{location}.properties.{name}")
    if "items" in schema:
        validate_schema_definition(schema["items"], location=f"{location}.items")
    enum = schema.get("enum")
    if enum is not None:
        if not isinstance(enum, list) or not enum:
            raise SchemaDefinitionError(
                "enum must be a non-empty array", location=f"{location}.enum"
            )
        try:
            json.dumps(enum, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise SchemaDefinitionError(
                "enum values must be JSON values", location=f"{location}.enum"
            ) from exc
    pattern = schema.get("pattern")
    if pattern is not None:
        if not isinstance(pattern, str):
            raise SchemaDefinitionError(
                "pattern must be a string", location=f"{location}.pattern"
            )
        try:
            re.compile(pattern)
        except re.error as exc:
            raise SchemaDefinitionError(
                f"pattern is invalid: {exc}", location=f"{location}.pattern"
            ) from exc
    additional = schema.get("additionalProperties")
    if additional is not None and not isinstance(additional, bool):
        if not isinstance(additional, Mapping):
            raise SchemaDefinitionError(
                "additionalProperties must be a boolean or schema",
                location=f"{location}.additionalProperties",
            )
        validate_schema_definition(
            additional, location=f"{location}.additionalProperties"
        )


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


def _validate_json_value(
    value: Any,
    schema: Mapping[str, Any],
    location: str,
    errors: list[dict[str, str]],
) -> None:
    expected = schema.get("type")
    if expected is not None and not _matches_type(value, expected):
        errors.append({"path": location, "message": f"expected {expected}"})
        return
    if "enum" in schema and not any(
        type(value) is type(item) and value == item for item in schema["enum"]
    ):
        errors.append({"path": location, "message": "value is not in enum"})
    if "pattern" in schema and isinstance(value, str) and re.search(schema["pattern"], value) is None:
        errors.append({"path": location, "message": "string does not match pattern"})
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                errors.append(
                    {"path": location, "message": f"missing required property {name!r}"}
                )
        additional = schema.get("additionalProperties", True)
        extra_names = sorted(set(value) - set(properties))
        if additional is False:
            for name in extra_names:
                errors.append(
                    {"path": f"{location}.{name}", "message": "additional property is not allowed"}
                )
        elif isinstance(additional, Mapping):
            for name in extra_names:
                _validate_json_value(
                    value[name], additional, f"{location}.{name}", errors
                )
        for name, child_schema in properties.items():
            if name in value:
                _validate_json_value(value[name], child_schema, f"{location}.{name}", errors)
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            _validate_json_value(item, schema["items"], f"{location}[{index}]", errors)


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return False
