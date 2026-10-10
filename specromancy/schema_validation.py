"""Definition and value validation for the supported JSON schema subset.

This module is independent of configuration loading and artifact validation.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any


SUPPORTED_SCHEMA_KEYWORDS = frozenset(
    {"type", "required", "properties", "items", "enum", "pattern", "additionalProperties"}
)
SUPPORTED_JSON_TYPES = frozenset(
    {"object", "array", "string", "number", "integer", "boolean", "null"}
)


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
