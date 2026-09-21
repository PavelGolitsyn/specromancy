"""Restricted scalar frontmatter used by every Specromancy artifact.

This is deliberately not a YAML parser.  The tiny accepted language is the one
defined by ``artifact.schema.json`` and cannot acquire YAML's executable or
surprising features by accident.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Mapping

from ..errors import ValidationError
from ..io import normalized_text


FRONTMATTER_KEYS: Final = (
    "schema-version",
    "run-id",
    "stage",
    "status",
    "created-at",
)
STAGES: Final = {"request", "research", "plan", "implementation", "review"}
STATUSES_BY_STAGE: Final = {
    "request": {"draft", "ready"},
    "research": {"draft", "ready"},
    "plan": {"draft", "ready"},
    "implementation": {"draft", "ready"},
    "review": {"draft", "passed", "changes_requested", "blocked"},
}
_RUN_ID: Final = re.compile(r"^[a-z0-9][a-z0-9-]{1,78}[a-z0-9]$")
_SCALAR_LINE: Final = re.compile(r'^([a-z][a-z-]*): "([^"\\]*)"$')
_TIMESTAMP: Final = re.compile(
    r"^[0-9]{4}-(0[1-9]|1[0-2])-([0-2][0-9]|3[01])T"
    r"([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z$"
)


@dataclass(frozen=True)
class ArtifactDocument:
    """One parsed artifact with validated metadata and normalized body text."""

    metadata: Mapping[str, str]
    body: str


def _invalid(message: str, remediation: str) -> ValidationError:
    return ValidationError(message, hint=remediation)


def parse_frontmatter(
    text: str,
    *,
    expected_run_id: str | None = None,
    expected_stage: str | None = None,
    expected_status: str | None = None,
) -> ArtifactDocument:
    """Parse and validate version 1 restricted scalar frontmatter."""

    if text.startswith("\ufeff"):
        raise _invalid(
            "Artifact frontmatter must begin at byte zero without a byte-order mark.",
            "Remove the byte-order mark so the first three bytes are ---.",
        )
    content = normalized_text(text)
    lines = content.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\n") != "---":
        raise _invalid(
            "Artifact frontmatter is missing its opening delimiter.",
            "Put --- on the first line of the artifact.",
        )

    closing_index: int | None = None
    for index, line in enumerate(lines[1:], start=1):
        if line.rstrip("\n") == "---":
            closing_index = index
            break
    if closing_index is None:
        raise _invalid(
            "Artifact frontmatter is missing its closing delimiter.",
            "Add a line containing only --- after the five metadata fields.",
        )

    metadata_lines = [line.rstrip("\n") for line in lines[1:closing_index]]
    if len(metadata_lines) != len(FRONTMATTER_KEYS):
        raise _invalid(
            "Artifact frontmatter must contain exactly five metadata fields.",
            "Use schema-version, run-id, stage, status, and created-at once each.",
        )

    metadata: dict[str, str] = {}
    observed_order: list[str] = []
    for line in metadata_lines:
        match = _SCALAR_LINE.fullmatch(line)
        if match is None:
            raise _invalid(
                "Artifact frontmatter contains unsupported scalar syntax.",
                'Write each field as key: "value" with no comments or escapes.',
            )
        key, value = match.groups()
        if key in metadata:
            raise _invalid(
                f"Artifact frontmatter repeats the '{key}' field.",
                f"Keep exactly one '{key}' metadata line.",
            )
        if key not in FRONTMATTER_KEYS:
            raise _invalid(
                f"Artifact frontmatter contains unknown field '{key}'.",
                "Remove unknown metadata; version 1 permits only the five defined fields.",
            )
        metadata[key] = value
        observed_order.append(key)

    if tuple(observed_order) != FRONTMATTER_KEYS:
        raise _invalid(
            "Artifact frontmatter fields are not in the version 1 order.",
            "Order fields as schema-version, run-id, stage, status, created-at.",
        )
    if metadata["schema-version"] != "1":
        raise _invalid(
            "Artifact schema version is not supported.",
            'Set schema-version to "1" or use a compatible Specromancy release.',
        )
    if _RUN_ID.fullmatch(metadata["run-id"]) is None:
        raise _invalid(
            "Artifact run ID is malformed.",
            "Use the lowercase run ID from the containing run directory.",
        )
    if expected_run_id is not None and metadata["run-id"] != expected_run_id:
        raise _invalid(
            "Artifact run ID does not match the active run.",
            f'Set run-id to "{expected_run_id}".',
        )
    stage = metadata["stage"]
    if stage not in STAGES:
        raise _invalid(
            f"Artifact stage '{stage}' is unknown.",
            "Use request, research, plan, implementation, or review.",
        )
    if expected_stage is not None and stage != expected_stage:
        raise _invalid(
            f"Artifact stage is '{stage}', not '{expected_stage}'.",
            f'Set stage to "{expected_stage}" for this artifact.',
        )
    status = metadata["status"]
    if status not in STATUSES_BY_STAGE[stage]:
        raise _invalid(
            f"Artifact status '{status}' is invalid for stage '{stage}'.",
            f"Use one of: {', '.join(sorted(STATUSES_BY_STAGE[stage]))}.",
        )
    if expected_status is not None and status != expected_status:
        raise _invalid(
            f"Artifact status is '{status}', not '{expected_status}'.",
            f'Set status to "{expected_status}" after the artifact is complete.',
        )
    timestamp = metadata["created-at"]
    if _TIMESTAMP.fullmatch(timestamp) is None:
        raise _invalid(
            "Artifact created-at value is not a UTC version 1 timestamp.",
            'Use second precision in the form "YYYY-MM-DDTHH:MM:SSZ".',
        )
    try:
        datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise _invalid(
            "Artifact created-at value is not a real calendar timestamp.",
            "Correct the date and retain UTC second precision with a trailing Z.",
        ) from exc

    body = "".join(lines[closing_index + 1 :])
    return ArtifactDocument(metadata=metadata, body=body)


def render_frontmatter(metadata: Mapping[str, str], body: str) -> str:
    """Render known-safe metadata in canonical order."""

    missing = [key for key in FRONTMATTER_KEYS if key not in metadata]
    if missing:
        raise _invalid(
            "Cannot render incomplete artifact frontmatter.",
            f"Provide the missing fields: {', '.join(missing)}.",
        )
    values = {key: str(metadata[key]) for key in FRONTMATTER_KEYS}
    for key, value in values.items():
        if '"' in value or "\\" in value or "\n" in value or "\r" in value:
            raise _invalid(
                f"Cannot render unsupported characters in '{key}'.",
                "Use a single-line scalar with no quote or backslash characters.",
            )
    prefix = ["---", *(f'{key}: "{values[key]}"' for key in FRONTMATTER_KEYS), "---"]
    candidate = "\n".join(prefix) + "\n" + body.lstrip("\n")
    parse_frontmatter(candidate)
    return candidate
